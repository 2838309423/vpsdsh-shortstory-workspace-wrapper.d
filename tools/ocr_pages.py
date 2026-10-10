#!/usr/bin/env python3
"""批量 OCR（阿里云百炼 兼容模式 qwen3-vl-flash，图片先降分辨率再提交）。

用法：
  python3 ocr_pages.py --indir DIR [--glob '*.jpg'] [--limit N] [--out OUT.tsv]
                       [--model qwen3-vl-flash] [--thinking 0] [--workers 4]
                       [--resize 0|700]     # 0=用原图；>0=提交前用 ffmpeg 缩到该宽度
                       [--prompt FILE] [--dry-run]

输出 TSV：file<TAB>width<TAB>prompt_tokens<TAB>completion_tokens<TAB>sec<TAB>text(B64)
  文本用 base64 存一列，避免正文里的制表/换行破坏 TSV。另有 --out-dir 存单页 txt。
末行：__OCR_DONE__ <成功> <失败> <总prompt_tokens> <总completion_tokens> <总秒>
"""
import argparse
import base64
import concurrent.futures as cf
import glob as globmod
import json
import os
import re
import subprocess
import sys
import time

import requests

FF = os.environ.get("FFMPEG", "/tmp/vidtool/bin/ffmpeg")
KEYFILE = os.environ.get("BAILIAN_KEYFILE", "/home/longxia/.config/aliyun-bailian/api-key.txt")

DEFAULT_PROMPT = (
    "这是一页中文小说的正文截图。请**只输出图中可见的正文文字**：\n"
    "1) 按阅读顺序逐字输出，保留自然段（段与段之间空一行）；\n"
    "2) 不要输出任何解释、标题、页码、markdown 记号、代码块或引号包裹；\n"
    "3) 图中被裁断或缺字的地方用 ⟨?⟩ 占位，不要猜测补全；\n"
    "4) 不要合并或拆分原有段落。"
)


def load_key():
    raw = open(KEYFILE).read()
    key = re.search(r"api_key:\s*(\S+)", raw).group(1)
    host = re.search(r"http api host:\s*(\S+)", raw).group(1)
    return key, f"https://{host}/compatible-mode/v1/chat/completions"


def prep(img, resize, tmpdir):
    """按需降分辨率，返回 (路径, 宽, 高)。"""
    if not resize:
        return img, 0, 0
    out = os.path.join(tmpdir, os.path.basename(img).rsplit(".", 1)[0] + f".s{resize}.jpg")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(img):
        r = subprocess.run([FF, "-v", "error", "-y", "-i", img,
                            "-vf", f"scale={resize}:-2", "-q:v", "4", out],
                           capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"缩放失败 {img}: {r.stderr.decode()[:200]}")
    return out, 0, 0


def one(img, url, key, prompt, model, thinking, max_tokens, timeout, resize, tmpdir):
    t0 = time.time()
    try:
        path, _, _ = prep(img, resize, tmpdir)
        b = base64.b64encode(open(path, "rb").read()).decode()
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}},
                {"type": "text", "text": prompt},
            ]}],
            "temperature": 0.01,
            "max_tokens": max_tokens,
        }
        if thinking is not None:
            body["enable_thinking"] = bool(thinking)
        r = requests.post(url, headers={"Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json"},
                          data=json.dumps(body), timeout=timeout)
        dt = time.time() - t0
        if r.status_code != 200:
            return dict(file=img, ok=0, err=f"HTTP {r.status_code} {r.text[:200]}", sec=dt)
        j = r.json()
        u = j.get("usage") or {}
        txt = (j["choices"][0]["message"].get("content") or "").strip()
        return dict(file=img, ok=1, pt=u.get("prompt_tokens", 0),
                    ct=u.get("completion_tokens", 0), sec=dt, text=txt)
    except Exception as e:
        return dict(file=img, ok=0, err=f"{type(e).__name__}: {e}"[:200],
                    sec=time.time() - t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--glob", default="*.jpg")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--model", default="qwen3-vl-flash")
    ap.add_argument("--thinking", type=int, default=0, help="-1=不带该参数")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resize", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--prompt", default="")
    args = ap.parse_args()

    prompt = open(args.prompt).read() if args.prompt else DEFAULT_PROMPT
    key, url = load_key()
    tmpdir = "/tmp/ca24/work/resized"
    os.makedirs(tmpdir, exist_ok=True)
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)

    imgs = sorted(globmod.glob(os.path.join(args.indir, args.glob)))
    if args.limit:
        imgs = imgs[:args.limit]
    if not imgs:
        print("没有匹配的图片", file=sys.stderr)
        return 2
    print(f"# {len(imgs)} 张 -> {args.model} resize={args.resize or '原图'} "
          f"workers={args.workers}", file=sys.stderr)

    out = args.out or os.path.join(args.indir, "ocr.tsv")
    res = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, im, url, key, prompt, args.model,
                          None if args.thinking < 0 else args.thinking,
                          args.max_tokens, args.timeout, args.resize, tmpdir): im
                for im in imgs}
        for k, f in enumerate(cf.as_completed(futs), 1):
            r = f.result()
            res.append(r)
            tag = "OK " if r["ok"] else "ERR"
            print(f"# [{k}/{len(imgs)}] {tag} {os.path.basename(r['file'])} "
                  f"{r.get('sec',0):.1f}s pt={r.get('pt','-')} ct={r.get('ct','-')} "
                  f"{r.get('err','')}", file=sys.stderr)

    res.sort(key=lambda r: r["file"])
    with open(out, "w") as f:
        f.write("file\tok\tprompt_tokens\tcompletion_tokens\tsec\ttext_b64\terror\n")
        for r in res:
            tb = base64.b64encode((r.get("text") or "").encode()).decode()
            f.write(f"{r['file']}\t{r['ok']}\t{r.get('pt','')}\t{r.get('ct','')}\t"
                    f"{r.get('sec',0):.2f}\t{tb}\t{r.get('err','')}\n")
    if args.out_dir:
        for r in res:
            if r["ok"]:
                p = os.path.join(args.out_dir, os.path.basename(r["file"]).rsplit(".", 1)[0] + ".txt")
                open(p, "w").write(r.get("text", ""))
    ok = sum(r["ok"] for r in res)
    print(f"__OCR_DONE__ {ok} {len(res)-ok} "
          f"{sum(r.get('pt',0) for r in res)} {sum(r.get('ct',0) for r in res)} "
          f"{sum(r.get('sec',0) for r in res):.1f}")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())

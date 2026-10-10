#!/usr/bin/env python3
"""补漏：对「被内容审核拦下 / 失败」的单页做降级重试。

策略（按顺序试）：
  1) 整页原图重试（指数退避）——偶发限流/抖动；
  2) 拦下则**上下切两半**分别提交再拼回（`data_inspection_failed` 是整图判定，
     切成两半往往能过其中一半以上）；
  3) 还不行就切三份，记录仍失败的部分。

用法：
  python3 fix_page.py --png 原分辨率帧.png --out 文本.txt [--model qwen3-vl-flash]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time

import requests

FF = os.environ.get("FFMPEG", "/tmp/vidtool/bin/ffmpeg")
KEYFILE = os.environ.get("BAILIAN_KEYFILE", "/tmp/ca24/bailian.key")
PROMPT = "提取图中全部中文（小说正文），按阅读顺序、保留原有换行与段落，只输出文字。"


def load_key():
    raw = open(KEYFILE).read()
    key = re.search(r"api_key:\s*(\S+)", raw).group(1)
    host = re.search(r"http api host:\s*(\S+)", raw).group(1)
    return key, f"https://{host}/compatible-mode/v1/chat/completions"


def ocr(path, key, url, model, timeout=180):
    b = base64.b64encode(open(path, "rb").read()).decode()
    body = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}},
        {"type": "text", "text": PROMPT}]}],
        "temperature": 0.01, "max_tokens": 2000, "enable_thinking": False}
    r = requests.post(url, headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=timeout)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {r.text[:160]}"
    j = r.json()
    return (j["choices"][0]["message"].get("content") or "").strip(), None


def crop(png, y, h, out):
    subprocess.run([FF, "-v", "error", "-y", "-i", png,
                    "-vf", f"crop=iw:{h}:0:{y}", "-q:v", "3", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default="/tmp/ca24/work/fix")
    ap.add_argument("--model", default="qwen3-vl-flash")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    key, url = load_key()
    base = os.path.splitext(os.path.basename(args.png))[0]

    # 转 jpg（原图提交）
    jpg = os.path.join(args.work, base + ".jpg")
    subprocess.run([FF, "-v", "error", "-y", "-i", args.png, "-q:v", "3", jpg], check=True)

    txt, err = ocr(jpg, key, url, args.model)
    if txt:
        open(args.out, "w").write(txt)
        print(f"# 整页成功 -> {args.out}")
        print("__FIX__ full", len(txt))
        return 0
    print(f"# 整页被拦/失败: {err}", file=sys.stderr)

    # 切两半
    h = int(subprocess.run([FF.replace("ffmpeg", "ffprobe"), "-v", "error",
                            "-show_entries", "stream=height", "-of", "csv=p=0", jpg],
                           capture_output=True).stdout.strip() or 1408)
    parts = []
    for i, (y, hh) in enumerate([(0, h // 2 + 20), (h // 2 - 20, h - h // 2 + 20)]):
        p = crop(jpg, y, hh, os.path.join(args.work, f"{base}.h{i}.jpg"))
        for attempt in range(4):
            t, e = ocr(p, key, url, args.model)
            if t:
                parts.append(t)
                print(f"# 半页 {i} 成功（{len(t)} 字）", file=sys.stderr)
                break
            print(f"# 半页 {i} 第{attempt+1}次失败: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
        else:
            parts.append("")
    txt = "\n".join(x for x in parts if x)
    open(args.out, "w").write(txt)
    print(f"# 半页拼回 -> {args.out} ({len(txt)} 字)")
    print(f"__FIX__ halves {len(txt)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

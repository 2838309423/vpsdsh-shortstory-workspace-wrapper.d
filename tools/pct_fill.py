#!/usr/bin/env python3
"""百分数补录：只把「右下角翻页百分数」那一条窄带单独裁出来再 OCR。

为什么需要（2026-10-10 深夜，S59~S76 那轮实测）：
  * 主模型 `qwen-vl-ocr` 是**纯 OCR** 引擎，对「正文后另起一行输出 PCT:xx.xx%」这种
    指令性格式**不服从**——实测 1117 页里有 197 页（17.6%）干脆不吐 PCT 行，
    连底栏的裸百分数也不吐。正文本身没问题（这正是它作为主模型的价值），
    但百分数标尺缺了 197 页，`NO-PCT` 不为 0。
  * 整页重跑一遍太贵，而且会把正文换成另一个模型的版本（引入不一致）。
  * 正确做法：**只裁底栏窄带**（存档帧 980×1486 里 y≈1428~1457，取 `crop=iw:110:0:1376`），
    一次调用的图像 token 只有整页的 1/8 左右，且**完全不碰正文**。

做法：
  1. `--pct-list` 里 flag ∈ 需要补的集合（默认 {NO-PCT}）⇒ 补录并**写回**；
  2. `--check-flag` 里的页（如 GAP? / REPEAT）⇒ 只**复核**（打印已有值 vs 窄带读数），
     只有 `--overwrite` 才写回；
  3. 写回方式：给该页的 `text_b64` 末尾追加一行 `PCT:xx.xx%`，
     同时改**分段 ocr.tsv**（真值）与合并表 all_ocr.tsv，
     这样重跑 `pct_parse.py` 就能拿到完整标尺，且流程仍然幂等。

用法（以 shortstory 身份跑，需 FFMPEG 与 BAILIAN_KEYFILE 可读）：
  python3 pct_fill.py --frames-root /tmp/ca31/out2/frames --pct-list /tmp/ca31/out2/pct清单.tsv
      --ocr-tsv /tmp/ca31/out2/all_ocr.tsv --report /tmp/ca31/out2/pct补录.tsv
      [--model qwen-vl-ocr] [--workers 8] [--dry-run] [--overwrite]
末行：__PCTFILL__ <候选页数> <窄带读到的页数> <写回的页数> <仍缺的页数>
"""
import argparse
import base64
import concurrent.futures as cf
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_pages  # 复用 one()/load_key()，保证与批量 OCR 同一条路

FF = os.environ.get("FFMPEG", "/tmp/vidtool/bin/ffmpeg")
RE_PCT = re.compile(r"(\d{1,3}(?:[.,]\d{1,3})?)\s*%")
RE_PCT_BARE = re.compile(r"^\s*(\d{1,3}(?:[.,]\d{1,3})?)\s*$")

STRIP_PROMPT = (
    "这是手机阅读器截图底部的一条窄带。它左边可能有电量/时间，右边可能有翻页进度百分数。\n"
    "只输出你在这条窄带里看到的**全部文字与数字**，用单个空格分隔，按从左到右的顺序；\n"
    "不要解释，不要加任何标记，不要补全你没看到的内容；如果整条窄带没有任何文字，只输出 NONE。"
)


def seg_page(path):
    b = os.path.basename(path)
    parts = b.split(".")
    return parts[0], (parts[1] if len(parts) >= 2 else "")


def read_tsv(path):
    rows = {}
    hdr = None
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == len(hdr):
                rows[os.path.normpath(p[0])] = p
    return hdr, rows


def crop_strip(img, outdir, crop):
    out = os.path.join(outdir, os.path.basename(img).rsplit(".", 1)[0] + ".strip.jpg")
    r = subprocess.run([FF, "-v", "error", "-y", "-i", img, "-vf", f"crop={crop}",
                        "-q:v", "3", out], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"裁窄带失败 {img}: {r.stderr.decode()[:200]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-root", required=True)
    ap.add_argument("--pct-list", required=True)
    ap.add_argument("--ocr-tsv", required=True, help="合并表 all_ocr.tsv（会被写回）")
    ap.add_argument("--report", required=True)
    ap.add_argument("--model", default="qwen-vl-ocr")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--strip-crop", default="iw:110:0:1376")
    ap.add_argument("--fill-flag", action="append", default=["NO-PCT"])
    ap.add_argument("--check-flag", action="append", default=["GAP?", "REPEAT"])
    ap.add_argument("--new-mark", default="", help="只处理段名含此标记的段（默认全部）")
    ap.add_argument("--overwrite", action="store_true", help="复核页也用窄带读数覆盖旧值")
    ap.add_argument("--thinking", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1) 选出候选页
    fill_flags, check_flags = set(args.fill_flag), set(args.check_flag)
    want = {}
    with open(args.pct_list) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            d = dict(zip(hdr, p))
            if args.new_mark and args.new_mark not in d["segment"]:
                continue
            if d["flag"] in fill_flags:
                want[d["file"]] = ("fill", d["pct"])
            elif d["flag"] in check_flags:
                want[d["file"]] = ("check", d["pct"])
    print(f"# 候选 {len(want)} 页（补 {sum(1 for v in want.values() if v[0]=='fill')} / "
          f"复核 {sum(1 for v in want.values() if v[0]=='check')}）")
    if args.dry_run:
        print(f"__PCTFILL__ {len(want)} 0 0 {len(want)}")
        return 0

    key, url = ocr_pages.load_key()
    tmpdir = tempfile.mkdtemp(prefix="pctfill.")
    prompt = STRIP_PROMPT

    def work(item):
        name, (mode, old) = item
        seg, _ = seg_page(name)
        img = os.path.join(args.frames_root, seg, "pages", name)
        if not os.path.exists(img):
            return name, mode, old, "", "缺帧图"
        try:
            strip = crop_strip(img, tmpdir, args.strip_crop)
        except Exception as e:
            return name, mode, old, "", f"裁剪异常 {e}"[:120]
        r = ocr_pages.one(strip, url, key, prompt, args.model,
                          None if args.thinking < 0 else args.thinking,
                          args.max_tokens, args.timeout, 0, tmpdir)
        if not r["ok"]:
            return name, mode, old, "", r.get("err", "OCR 失败")[:120]
        raw = (r.get("text") or "").strip()
        m = RE_PCT.search(raw)
        if not m:
            m = RE_PCT_BARE.match(raw)
        new = (m.group(1).replace(",", ".") if m else "")
        return name, mode, old, new, raw[:80]

    items = sorted(want.items())
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(work, items):
            results.append(res)

    # 2) 写回
    hdr_all, rows = read_tsv(args.ocr_tsv)
    per_seg = {}
    n_read = n_write = 0
    rep = ["file\tmode\told_pct\tstrip_pct\twrite\tstrip_text"]
    for name, mode, old, new, note in results:
        write = "Y" if (new and (mode == "fill" or args.overwrite)) else ""
        rep.append(f"{name}\t{mode}\t{old}\t{new}\t{write}\t{note}")
    with open(args.report, "w") as f:
        f.write("\n".join(rep) + "\n")

    # 按段归并写回
    patch = {}
    for name, mode, old, new, note in results:
        if new:
            n_read += 1
            if mode == "fill" or args.overwrite:
                n_write += 1
                patch[name] = new

    def patch_tsv(path, hdr):
        changed = 0
        with open(path) as f:
            lines = f.readlines()
        out = [lines[0]]
        for line in lines[1:]:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                out.append(line)
                continue
            b = os.path.basename(p[0])
            if b in patch:
                txt = base64.b64decode(p[5]).decode()
                txt = re.sub(r"(?im)^\s*PCT\s*[:：].*$", "", txt).rstrip()
                txt = f"{txt}\nPCT:{patch[b]}%"
                p[5] = base64.b64encode(txt.encode()).decode()
                changed += 1
            out.append("\t".join(p) + "\n")
        with open(path, "w") as f:
            f.writelines(out)
        return changed

    if patch:
        c1 = patch_tsv(args.ocr_tsv, hdr_all)
        print(f"# 写回合并表 {args.ocr_tsv}：{c1} 页")
        for seg in sorted({seg_page(n)[0] for n in patch}):
            p = os.path.join(args.frames_root, seg, "ocr.tsv")
            if os.path.exists(p):
                h2, _ = read_tsv(p)
                c2 = patch_tsv(p, h2)
                per_seg[seg] = c2
        print(f"# 写回分段 ocr.tsv：{len(per_seg)} 段，共 {sum(per_seg.values())} 页")

    still = sum(1 for name, mode, old, new, note in results if mode == "fill" and not new)
    no_read = sum(1 for name, mode, old, new, note in results if not new)
    print(f"# 窄带读到百分数 {n_read}/{len(results)}；写回 {n_write} 页；仍读不到 {no_read} 页")
    print(f"__PCTFILL__ {len(results)} {n_read} {n_write} {still}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

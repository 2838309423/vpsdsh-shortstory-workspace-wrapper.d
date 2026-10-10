#!/usr/bin/env python3
"""增量补 OCR：**只提交「缺失页 / 上次失败页」**，绝不重跑整段，绝不从 s01 重扫。

来历（2026-10-10 甲方点名批评）：
  旧流程的 ocr 步骤是「有 ocr.tsv 就整段 SKIP」，于是出现过两种浪费：
    ① 某段只失败 1 页，却要整段 63 页重跑；
    ② 每次补新录的段，循环都从 s01 开始扫一遍（虽然 SKIP，但一旦判定口径变化就会全量重跑）。
  本工具按**页**判：读出现有 ocr.tsv，把 ok != 1 的页取出来重新提交，结果按 file 归并回原表。
  幂等：全成功的段直接 SKIP，零调用。

用法（以能读帧图与密钥的身份跑，例如 shortstory）：
  python3 ocr_fill.py --frames-root /tmp/ca31/out2/frames [--model qwen3-vl-plus]
      [--workers 8] [--prompt /tmp/ca31/prompt_pct.txt]
      [--new-first]                 # 新录批次（文件名含 142457）优先处理
      [--seg s32 --seg s33 ...]     # 只处理指定段；不给就处理全部缺失段
      [--dry-run]
末行：__FILL__ <检查段数> <缺页段数> <补跑页数> <仍失败页数> <总prompt_tokens> <总completion_tokens>
"""
import argparse
import base64
import concurrent.futures as cf
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_pages  # 复用它的 one()/load_key()/prep()，保证与批量 OCR 完全同一条路

HDR = "file\tok\tprompt_tokens\tcompletion_tokens\tsec\ttext_b64\terror\n"


def read_tsv(path):
    """读 ocr.tsv，键用 os.path.normpath 归一（历史文件里有 `frames/<seg>//pages/` 双斜杠）。"""
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == len(hdr):
                p[0] = os.path.normpath(p[0])
                rows[p[0]] = p
    return rows


def fmt(r):
    tb = base64.b64encode((r.get("text") or "").encode()).decode()
    return [r["file"], str(r["ok"]), str(r.get("pt", "")), str(r.get("ct", "")),
            f"{r.get('sec', 0):.2f}", tb, r.get("err", "")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-root", required=True)
    ap.add_argument("--model", default="qwen3-vl-flash")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--thinking", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--resize", type=int, default=0)
    ap.add_argument("--new-first", action="store_true",
                    help="文件名含 142457 的新录批次优先")
    ap.add_argument("--seg", action="append", default=[],
                    help="只处理这些段（可重复；用段名后缀匹配，如 s32）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prompt = open(args.prompt).read() if args.prompt else ocr_pages.DEFAULT_PROMPT
    key, url = ocr_pages.load_key()
    tmpdir = "/tmp/ca24/work/resized"
    os.makedirs(tmpdir, exist_ok=True)

    dirs = [d for d in sorted(glob.glob(os.path.join(args.frames_root, "*")))
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "pages.tsv"))]
    if args.new_first:
        dirs.sort(key=lambda d: (0 if "142457" in os.path.basename(d) else 1,
                                 os.path.basename(d)))
    if args.seg:
        dirs = [d for d in dirs
                if any(os.path.basename(d).endswith(s) or s in os.path.basename(d)
                       for s in args.seg)]

    n_seg = n_gap_seg = n_page = n_fail = 0
    tot_p = tot_c = 0
    for d in dirs:
        base = os.path.basename(d)
        n_seg += 1
        pages = sorted(os.path.normpath(p) for p in glob.glob(os.path.join(d, "pages", "*.jpg")))
        tsv = os.path.join(d, "ocr.tsv")
        old = read_tsv(tsv)
        missing = [p for p in pages
                   if p not in old or old[p][1] != "1"]
        if not missing:
            print(f"SKIP {base}（{len(pages)} 页全成功）")
            continue
        n_gap_seg += 1
        n_page += len(missing)
        print(f"补 {base}：{len(missing)}/{len(pages)} 页"
              + ("（dry-run）" if args.dry_run else ""))
        if args.dry_run:
            continue
        t0 = time.time()
        res = []
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(ocr_pages.one, p, url, key, prompt, args.model,
                              None if args.thinking < 0 else args.thinking,
                              args.max_tokens, args.timeout, args.resize, tmpdir)
                    for p in missing]
            for f in cf.as_completed(futs):
                res.append(f.result())
        for r in res:
            tot_p += r.get("pt", 0) or 0
            tot_c += r.get("ct", 0) or 0
            if not r["ok"]:
                n_fail += 1
        for r in res:
            old[r["file"]] = fmt(r)
        tmp = tsv + ".tmp"
        with open(tmp, "w") as f:
            f.write(HDR)
            for k in sorted(old):
                f.write("\t".join(old[k]) + "\n")
        os.replace(tmp, tsv)
        ok_n = sum(1 for k in old if old[k][1] == "1")
        print(f"  {base} 完成 {len(res)} 页，用时 {time.time()-t0:.0f}s，"
              f"该段累计 ok={ok_n}/{len(pages)}")

    print(f"__FILL__ {n_seg} {n_gap_seg} {n_page} {n_fail} {tot_p} {tot_c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

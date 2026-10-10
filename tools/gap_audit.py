#!/usr/bin/env python3
"""页间隙审计：漏页的**硬指标**不是整屏像素差，而是相邻稳定窗之间的时间间隙。

实测口径（2026-10-10）：
  * 正常翻页：相邻稳定窗间隙 ≈ 0.5 s；
  * 漏掉一页：间隙 ≈ 2.8 s（少抓了一个静止窗）；
  * 阈值取 1.2 s：>1.2 s 即高度可疑，应在间隙中点补一帧（页名用 p0315 这种
    能按字符串排进正确位置的小数 idx），补完重跑本审计。

用法：
  python3 gap_audit.py --frames-root /tmp/ca31/out2/frames [--glob '*171536*']
      [--out 页间隙审计.tsv] [--th 1.2] [--fixed-tsv 上一轮已补页的审计.tsv]

输出 TSV：segment<TAB>idx_prev<TAB>idx_next<TAB>gap_s<TAB>mid_s<TAB>判定
末行：__GAP__ <检查段数> <检查间隙数> <超阈间隙数>
"""
import argparse
import glob
import os
import sys

HDR = "segment\tidx_prev\tidx_next\tgap_s\tmid_s\t判定\n"


def read_pages(path):
    rows = []
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            d = dict(zip(hdr, p))
            rows.append((d["idx"], float(d["start_s"]), float(d["end_s"])))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-root", required=True)
    ap.add_argument("--glob", default="*", help="只审计段名含此子串的段（默认全部）")
    ap.add_argument("--out", default="")
    ap.add_argument("--th", type=float, default=1.2)
    ap.add_argument("--all", action="store_true",
                    help="连正常间隙也写进 TSV（默认只写超阈的可疑间隙）")
    args = ap.parse_args()

    dirs = sorted(d for d in glob.glob(os.path.join(args.frames_root, "*"))
                  if os.path.isdir(d) and os.path.exists(os.path.join(d, "pages.tsv")))
    if args.glob != "*":
        dirs = [d for d in dirs if args.glob.strip("*") in os.path.basename(d)]

    n_seg = n_gap = n_bad = 0
    lines = []
    for d in dirs:
        seg = os.path.basename(d)
        n_seg += 1
        rows = read_pages(os.path.join(d, "pages.tsv"))
        for (i0, s0, e0), (i1, s1, e1) in zip(rows, rows[1:]):
            n_gap += 1
            gap = s1 - e0
            if gap > args.th:
                n_bad += 1
                mid = (e0 + s1) / 2
                lines.append((seg, i0, i1, f"{gap:.2f}", f"{mid:.2f}",
                              f"疑似漏页（> {args.th}s），建议在 {mid:.1f}s 补帧"))
                print(f"间隙 {seg} {i0}->{i1} {gap:.2f}s mid={mid:.2f}s")
            else:
                if args.all:
                    lines.append((seg, i0, i1, f"{gap:.2f}", "", "正常"))

    if args.out:
        with open(args.out, "w") as f:
            f.write(HDR)
            for r in lines:
                f.write("\t".join(map(str, r)) + "\n")
        print(f"# 写出 {args.out}")
    print(f"__GAP__ {n_seg} {n_gap} {n_bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""生成页清单：页序 ↔ 段/时刻 ↔ 帧文件 ↔ 字数 ↔ 右下滑动进度百分数 ↔ OCR 状态。

用法：
  python3 make_manifest.py <all_ocr.tsv 或 pages_clean.tsv> <out.tsv> \
      [--frames-root /tmp/ca31/out/frames]

2026-10-10 起：输入可直接给 pct_parse.py 产出的 pages_clean.tsv（多一列 pct），
于是清单里多了「翻页进度百分数」一列；frames 根目录也不再写死 /tmp/ca24。
"""
import argparse
import base64
import glob
import os
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return "".join(c for c in s if not c.isspace())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", help="all_ocr.tsv 或 pages_clean.tsv")
    ap.add_argument("out")
    ap.add_argument("--frames-root", default="/tmp/ca31/out/frames")
    args = ap.parse_args()

    meta = {}
    for f in glob.glob(os.path.join(args.frames_root, "*", "pages.tsv")):
        with open(f) as fh:
            fh.readline()
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 7:
                    meta[os.path.normpath(p[6])] = p

    rows = []
    with open(args.tsv) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            rows.append(dict(zip(hdr, p)))
    rows.sort(key=lambda d: d["file"])

    E = ""
    with open(args.out, "w") as f:
        f.write("n\tsegment\tidx\tstart_s\tend_s\tmid_s\tpct\tocr_chars\tok\tframe\n")
        for i, d in enumerate(rows, 1):
            m = meta.get(os.path.normpath(d["file"]), [E] * 7)
            t = base64.b64decode(d["text_b64"]).decode() if d.get("text_b64") else E
            seg = os.path.basename(d["file"]).split(".")[0]
            f.write("\t".join([str(i), seg, m[1] if len(m) > 1 else E,
                               m[2] if len(m) > 2 else E, m[3] if len(m) > 3 else E,
                               m[4] if len(m) > 4 else E, d.get("pct", E),
                               str(len(norm(t))), str(d.get("ok")), d["file"]]) + "\n")
    print("manifest:", args.out, len(rows), "页")
    return 0


if __name__ == "__main__":
    sys.exit(main())

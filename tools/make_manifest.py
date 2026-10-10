#!/usr/bin/env python3
"""生成 pages_manifest.tsv：页序 ↔ 段/时刻 ↔ 帧文件 ↔ 字数 ↔ OCR 状态。"""
import base64
import glob
import os
import sys
import unicodedata

TSV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ca24/out/all_ocr.tsv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ca24/out/pages_manifest.tsv"


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return "".join(c for c in s if not c.isspace())


meta = {}
for f in glob.glob("/tmp/ca24/out/frames/*/pages.tsv"):
    with open(f) as fh:
        fh.readline()
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 7:
                meta[os.path.normpath(p[6])] = p

rows = []
with open(TSV) as f:
    hdr = f.readline().rstrip("\n").split("\t")
    for line in f:
        p = line.rstrip("\n").split("\t")
        if len(p) != len(hdr):
            continue
        rows.append(dict(zip(hdr, p)))
rows.sort(key=lambda d: d["file"])

E = ""
with open(OUT, "w") as f:
    f.write("n\tsegment\tidx\tstart_s\tend_s\tmid_s\tocr_chars\tok\tframe\n")
    for i, d in enumerate(rows, 1):
        m = meta.get(os.path.normpath(d["file"]), [E] * 7)
        t = base64.b64decode(d["text_b64"]).decode() if d.get("text_b64") else E
        seg = os.path.basename(d["file"]).split(".")[0]
        f.write("\t".join([str(i), seg, m[1] if len(m) > 1 else E,
                           m[2] if len(m) > 2 else E, m[3] if len(m) > 3 else E,
                           m[4] if len(m) > 4 else E, str(len(norm(t))),
                           str(d.get("ok")), d["file"]]) + "\n")
print("manifest:", OUT, len(rows), "页")

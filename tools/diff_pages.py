#!/usr/bin/env python3
"""把两个模型在同一页上的差异**逐段列出来**，便于人工判谁对。
用法: python3 diff_pages.py 主.tsv 对照.tsv [页名片段...]
"""
import base64
import difflib
import os
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return "".join(c for c in s if not c.isspace())


def load(tsv):
    out = {}
    with open(tsv) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            d = dict(zip(hdr, p))
            if d.get("ok") == "1":
                out[os.path.basename(d["file"])] = norm(
                    base64.b64decode(d["text_b64"]).decode())
    return out


a, b = load(sys.argv[1]), load(sys.argv[2])
want = sys.argv[3:]
for k in sorted(set(a) & set(b)):
    if want and not any(w in k for w in want):
        continue
    x, y = a[k], b[k]
    if x == y:
        continue
    print(f"\n### {k}")
    sm = difflib.SequenceMatcher(None, x, y, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        ctx_l = x[max(0, i1 - 8):i1]
        ctx_r = x[i2:i2 + 8]
        print(f"  [{tag}] 上下文 …{ctx_l}【A:{x[i1:i2]} | B:{y[j1:j2]}】{ctx_r}…")

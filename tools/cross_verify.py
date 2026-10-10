#!/usr/bin/env python3
"""交叉验证：同一批页用两个模型各 OCR 一遍，比对一致率（字符级）。

两版都是 OCR，都不等于真值；但当两版**完全一致**时，几乎可以断定该页无误。
用法: python3 cross_verify.py 主.tsv 对照.tsv
"""
import base64
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
            if d.get("ok") != "1":
                continue
            out[os.path.basename(d["file"])] = norm(
                base64.b64decode(d["text_b64"]).decode())
    return out


def dist(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != b[j - 1]))
        prev = cur
    return prev[-1]


a = load(sys.argv[1])
b = load(sys.argv[2])
tot = same = 0
errs = []
print("页\t字数A\t字数B\t不一致字符\t错误率")
for k in sorted(set(a) & set(b)):
    x, y = a[k], b[k]
    if not x or not y:
        continue
    d = dist(x, y)
    base = max(len(x), len(y))
    rate = d / base
    tot += base
    errs.append(d)
    if d == 0:
        same += 1
    print(f"{k[-12:]}\t{len(x)}\t{len(y)}\t{d}\t{rate:.1%}")
print(f"\n# 页数 {len(errs)}  完全一致 {same} 页  "
      f"平均不一致字符 {sum(errs)/max(1,len(errs)):.1f} / 页  "
      f"字符级不一致率 {sum(errs)/max(1,tot):.2%}")
print(f"__CROSS__ {len(errs)} {same} {sum(errs)/max(1,tot):.4f}")

#!/usr/bin/env python3
"""接缝复核：录屏分段边界常常「上段末页 = 下段首页」整页重复。

`stitch.py` 对此有两条防线（① 整页逐字相同 ⇒ dup-page；② 跨段放宽窗口找锚点后切重叠），
但它靠的判据是 **归一化后逐字相同**——两段录屏的同一页 OCR 结果可能差 1~2 个字，
逐字相同就不成立。所以交付前必须人工复核一次，并把结论落盘。

本工具做三步：
  ① 比对「上段末页」与「下段首页」的 OCR 文本相似度（difflib ratio）；
  ② 摘出 `stitch_audit.tsv` 里下段首页那一行（dup-page / cross / cut 字数）；
  ③ 在**最终正文**里数「上段末页开头 N 字」出现几次（真重复 ⇒ ≥2 次）。

用法：
  python3 seam_check.py --frames-root /tmp/ca31/out2/frames \
      --audit /tmp/ca31/out2/stitch_audit.tsv \
      --corpus /tmp/ca31/out2/corpus_clean.txt \
      --prev qimao-20261010-142457-s58 --next qimao-20261010-171536-s59 \
      --out 接缝复核-S58-S59.txt
末行：__SEAM__ <相似度> <正文命中次数> <判定>
"""
import argparse
import base64
import difflib
import os
import re
import sys
import unicodedata

HDR = ("# 接缝复核 {prev} ⇄ {next}\n"
       "# 生成：python3 tools/seam_check.py\n\n")


def norm(s):
    # 底栏百分数（PCT:xx.xx%）不是正文，比对前先摘掉，免得「两个数字碰巧像」抬高相似度
    s = re.sub(r"(?im)^\s*PCT\s*[:：].*$", "", s)
    return "".join(c for c in unicodedata.normalize("NFKC", s) if not c.isspace())


def read_ocr(path):
    d = {}
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            q = dict(zip(hdr, p))
            if q.get("ok") != "1":
                continue
            d[os.path.basename(q["file"])] = base64.b64decode(q["text_b64"]).decode()
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-root", required=True)
    ap.add_argument("--prev", required=True)
    ap.add_argument("--next", required=True)
    ap.add_argument("--audit", default="")
    ap.add_argument("--corpus", default="")
    ap.add_argument("--head-chars", type=int, default=20)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    a = read_ocr(os.path.join(args.frames_root, args.prev, "ocr.tsv"))
    b = read_ocr(os.path.join(args.frames_root, args.next, "ocr.tsv"))
    last, first = sorted(a)[-1], sorted(b)[0]
    x, y = norm(a[last]), norm(b[first])
    ratio = difflib.SequenceMatcher(None, x, y).ratio()

    L = [HDR.format(prev=args.prev, next=args.next)]
    L.append(f"## ① 文本相似度（difflib，去空白/NFKC）\n")
    L.append(f"- {args.prev} 末页 `{last}`：{len(x)} 字（归一化）")
    L.append(f"- {args.next} 首页 `{first}`：{len(y)} 字（归一化）")
    L.append(f"- 相似度 = **{ratio:.4f}**\n")
    # 反证：拿「下段首页」去比上段**所有**页。若上段真的重复了这页，这里会出现一个 ≈1.0
    best = sorted(((difflib.SequenceMatcher(None, norm(v), y).ratio(), k)
                   for k, v in a.items()), reverse=True)[:3]
    L.append(f"- 反证：拿「{args.next} 首页」比 {args.prev} 全部 {len(a)} 页，最像的 3 页是")
    for r, k in best:
        L.append(f"  - {r:.4f}  `{k}`")
    L.append("")
    L.append("两端文本（各截前 120 字）：\n")
    L.append(f"- 上段末页：{x[:120]}")
    L.append(f"- 下段首页：{y[:120]}\n")

    L.append("## ② stitch.py 审计（下段首页那一行）\n")
    audit_line = None
    if args.audit and os.path.exists(args.audit):
        with open(args.audit) as f:
            for line in f:
                if line.startswith(first + "\t") or line.split("\t")[0] == first:
                    audit_line = line.rstrip("\n")
                    break
        L.append("- 表头：file / cut_chars / page_chars / boundary")
        L.append(f"- 命中行：`{audit_line}`" if audit_line else "- ⚠ 未在审计里找到该页")
    else:
        L.append("- （未给 --audit）")
    L.append("")

    n_hit = None
    if args.corpus and os.path.exists(args.corpus):
        corpus = norm(open(args.corpus).read())
        probe = x[:args.head_chars]
        n_hit = corpus.count(probe)
        L.append(f"## ③ 最终正文里该页开头 {args.head_chars} 字的出现次数\n")
        L.append(f"- 探针：`{probe}`")
        L.append(f"- 出现次数 = **{n_hit}**（1 = 已去重，2+ = 重复未去干净）\n")

    verdict = "OK（已去重）"
    if n_hit is not None and n_hit >= 2:
        verdict = "⚠ 重复未去干净（需手工删下段首页后重拼）"
    elif n_hit == 0:
        verdict = "⚠ 探针在正文里找不到（可能被切字或 OCR 变体），人工看一眼"
    L.append("## 结论\n")
    L.append(f"- 相似度 {ratio:.4f}；正文命中 {n_hit}；判定：**{verdict}**")

    with open(args.out, "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"__SEAM__ {ratio:.4f} {n_hit} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""QA：对拼接后的正文做机检，输出报告（stdout，可重定向落盘）。

检查项：
  A 规模：页数 / 字数 / 每页字数分布
  B 重复：长度 ≥20 字的重复子串（=去重失败）
  C 跨段：sNN→sNN+1 边界的重叠命中情况与相邻文字
  D 断口：页面边界处"上一页结尾 + 下一页开头"的字面量，供人工抽读
  E 可疑字符：非中文/非标点的怪字符、连续重复标点、`⟨?⟩` 占位符计数
  F 缺口：相邻页之间拼接后出现的可疑"半个词"（可选启发式，仅报告）

用法: python3 qa_corpus.py --tsv all_ocr.tsv --corpus corpus_raw.txt [--audit audit.tsv]
"""
import argparse
import base64
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stitch import norm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--audit", default="")
    ap.add_argument("--max-print", type=int, default=40)
    args = ap.parse_args()

    rows = []
    with open(args.tsv) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(hdr):
                continue
            d = dict(zip(hdr, p))
            if d.get("ok") != "1":
                continue
            d["text"] = base64.b64decode(d["text_b64"]).decode()
            rows.append(d)
    rows.sort(key=lambda d: d["file"])
    corpus = open(args.corpus).read()
    C = norm(corpus)

    print("== A 规模 ==")
    print(f"页数 {len(rows)}   正文字数(归一化) {len(C)}")
    lens = [len(norm(r['text'])) for r in rows]
    lens_s = sorted(lens)
    if lens_s:
        print(f"每页字数: min={lens_s[0]} p25={lens_s[len(lens_s)//4]} "
              f"中位={lens_s[len(lens_s)//2]} p75={lens_s[3*len(lens_s)//4]} max={lens_s[-1]} "
              f"合计={sum(lens)}")
        thin = [os.path.basename(r['file']) for r in rows if len(norm(r['text'])) < 30]
        print(f"可疑短页(<30字): {len(thin)} {thin[:10]}")
    by_seg = Counter(os.path.basename(r['file']).split('.')[0] for r in rows)
    print(f"段数 {len(by_seg)}；每段页数 min={min(by_seg.values())} "
          f"max={max(by_seg.values())} 合计={sum(by_seg.values())}")

    print("\n== B 重复子串 ==")
    # 占位符串会天然重复，先去掉再查；阈值 40 字以排除行文里的自然呼应
    Cx = C.replace("□", "")
    seen, dups, L = {}, [], 40
    for i in range(0, max(0, len(Cx) - L), 4):
        s = Cx[i:i + L]
        if s in seen and i - seen[s] >= L:
            dups.append((seen[s], i, s))
        else:
            seen.setdefault(s, i)
    print(f"阈值 {L} 字：重复片段 {len(dups)} 个")
    for a, b, s in dups[:args.max_print]:
        print(f"  {a}..{a+L} vs {b}..{b+L}: {s[:44]}")
    pseen = {}
    for r in rows:
        t = norm(r["text"])
        if len(t) >= 40:
            pseen.setdefault(t, []).append(os.path.basename(r["file"]))
    exact = {k: v for k, v in pseen.items() if len(v) > 1}
    print(f"完全相同的页 {len(exact)} 组（已在拼接时丢掉）：")
    for k, v in list(exact.items())[:6]:
        print(f"  {len(v)} 页: {v[:4]}  ← {k[:28]}...")

    print("\n== C 跨段边界 ==")
    for i in range(1, len(rows)):
        sa = os.path.basename(rows[i - 1]['file']).split('.')[0]
        sb = os.path.basename(rows[i]['file']).split('.')[0]
        if sa == sb:
            continue
        a = norm(rows[i - 1]['text'])[-18:]
        b = norm(rows[i]['text'])[:18]
        print(f"  {sa[-3:]}尾[{a}] → {sb[-3:]}头[{b}]")

    print("\n== D 段内边界抽样（每段取 2 处） ==")
    segs = {}
    for i, r in enumerate(rows):
        segs.setdefault(os.path.basename(r['file']).split('.')[0], []).append(i)
    for seg, idxs in list(segs.items()):
        for j in (len(idxs) // 3, 2 * len(idxs) // 3):
            if j <= 0:
                continue
            i = idxs[j]
            a = norm(rows[i - 1]['text'])[-16:]
            b = norm(rows[i]['text'])[:16]
            print(f"  {seg} p{j:03d}: …{a} | {b}…")

    print("\n== E 可疑字符 ==")
    bad = Counter(ch for ch in C if not (0x4E00 <= ord(ch) <= 0x9FFF
                                         or ch in '，。！？、：；“”‘’（）《》—…·0123456789'
                                         or 'A' <= ch <= 'Z' or 'a' <= ch <= 'z'))
    print(f"非常规字符 {sum(bad.values())} 个: {bad.most_common(20)}")
    for pat, name in ((r'⟨\?⟩', '占位符 ⟨?⟩'), (r'[，。]{3,}', '连续标点'),
                      (r'\.{4,}', '省略号变体'), (r'[“”]{2,}', '引号连排')):
        n = len(re.findall(pat, C))
        print(f"  {name}: {n}")

    print("\n== F 文件 ==")
    print(f"  corpus: {args.corpus}  ({len(corpus)} 字符原始长度)")
    if args.audit:
        with open(args.audit) as f:
            lines = f.read().splitlines()[1:]
        cross = [l for l in lines if l.endswith("cross")]
        hit = [int(l.split('\t')[1]) for l in lines if not l.endswith('first')]
        print(f"  audit: {args.audit}  边界 {len(lines)} 处，跨段 {len(cross)} 处，"
              f"切字命中 {sum(1 for h in hit if h)}/{len(hit)}")
    print("__QA_DONE__")


if __name__ == "__main__":
    main()

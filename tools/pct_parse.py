#!/usr/bin/env python3
"""把 OCR 原始结果里的「正文」与「右下角翻页进度百分数」分开，并做连续性审计。

背景（2026-10-10 甲方要求）：
  * 截屏矩形加高后，页面截图里多了阅读器底栏：左边「电量 + 时间(14:25)」、
    右边「翻页进度百分数(40.19%)」；
  * 百分数**不能进正文**，但它是判断「不同批次录屏是重叠了还是断片差剧情了」的
    相对标尺（甲方说它是哄 AI 的假数，绝对值不可信，**相对连续性可信**）；
  * 所以 OCR 提示词让它正文之后另起一行输出 `PCT:40.19%`，这里把它摘出来。

输入 TSV：file ok prompt_tokens completion_tokens sec text_b64 error
输出：
  --out        pages_clean.tsv：file ok pct chars text_b64   （正文，已剔除 UI/百分数）
  --pct-list   pct清单.tsv：n segment idx file pct delta_prev flag note
               flag ∈ ok | REPEAT(重叠/重复页) | GAP?(疑似缺页) | NO-PCT | NONMONO
  末行：__PCT__ <页数> <无百分数> <异常页数>
"""
import argparse
import base64
import os
import re
import statistics
import sys

# 底栏 UI：整行只有时间或百分数
RE_TIME_LINE = re.compile(r"^\s*\d{1,2}:\d{2}\s*$")
RE_PCT_LINE = re.compile(r"^\s*\d{1,3}(?:\.\d{1,3})?\s*%\s*$")
# 行首/行尾粘上的 UI token（只在行边缘剔，正文里不会出现这种串）
RE_EDGE = re.compile(r"^(?:\d{1,3}\.\d{1,2}%|\d{1,2}:\d{2})\s*|\s*(?:\d{1,3}\.\d{1,2}%|\d{1,2}:\d{2})$")
RE_PCT_TAG = re.compile(r"(?im)^\s*PCT\s*[:：]\s*(?:([\d]{1,3}(?:\.\d{1,3})?)\s*%?|[-—]+)\s*$")
RE_PCT_TAG_INLINE = re.compile(r"(?i)PCT\s*[:：]\s*([\d]{1,3}(?:\.\d{1,3})?)\s*%?")


def split_pct(text):
    """摘出 PCT 标记，返回 (正文, pct 字符串或 '')。"""
    pct = ""
    m = RE_PCT_TAG.search(text)
    if m:
        pct = m.group(1) or ""
        text = RE_PCT_TAG.sub("", text)
    if not pct:
        m = RE_PCT_TAG_INLINE.search(text)
        if m:
            pct = m.group(1)
            text = RE_PCT_TAG_INLINE.sub("", text)
    return text, pct


def strip_ui(text):
    """剔除混进正文的底栏 UI（时间/百分数），返回 (正文, 命中数)。"""
    hits = 0
    out = []
    for line in text.split("\n"):
        if RE_TIME_LINE.match(line) or RE_PCT_LINE.match(line):
            hits += 1
            continue
        new = RE_EDGE.sub("", line.strip())
        # 一行里可能两头各粘一个（"40.19% 14:25"）
        new2 = RE_EDGE.sub("", new.strip())
        if new2 != line.strip():
            hits += 1
        out.append(new2)
    return "\n".join(out), hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pct-list", default="")
    ap.add_argument("--gap-factor", type=float, default=3.0,
                    help="段内相邻页百分数增量的中位数倍数，超过即疑似缺页")
    ap.add_argument("--gap-abs", type=float, default=0.6,
                    help="绝对下限：增量小于它不算缺页（假数抖动）")
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
            raw = base64.b64decode(d["text_b64"]).decode()
            body, pct = split_pct(raw)
            body, ui_hits = strip_ui(body)
            body = re.sub(r"\n{3,}", "\n\n", body).strip()
            rows.append(dict(file=d["file"], pct=pct, text=body, ui_hits=ui_hits,
                             raw_chars=len(re.sub(r"\s", "", raw)),
                             chars=len(re.sub(r"\s", "", body))))
    rows.sort(key=lambda r: r["file"])

    # 段内增量中位数（只取同一段相邻页都为数字、且未回退的增量）
    deltas = []
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        if seg_of(a["file"]) != seg_of(b["file"]):
            continue
        try:
            x, y = float(a["pct"]), float(b["pct"])
        except ValueError:
            continue
        if y > x:
            deltas.append(y - x)
    med = statistics.median(deltas) if deltas else 0.0

    flags, pctrows = [], []
    for i, r in enumerate(rows):
        seg, idx = seg_of(r["file"]), page_of(r["file"])
        prev = rows[i - 1] if i else None
        d = None
        if prev is not None and prev["pct"] and r["pct"]:
            d = round(float(r["pct"]) - float(prev["pct"]), 4)
        flag, note = "ok", ""
        if not r["pct"]:
            flag, note = "NO-PCT", "OCR 未给出百分数"
        elif d is not None:
            if d < 0:
                flag, note = "REPEAT", f"回退({d:+.2f}%) 页面重复（重叠）"
            elif d == 0:
                # 显示只到 0.01%，而每页约涨 0.018% ⇒ 相邻页显示不变是**正常量化**，
                # 不是重复页（实测约占 4%）。真正的重复页要看正文是否整页相同。
                flag, note = "SAME", "显示未变（0.01% 量化，正常）"
            elif d > max(args.gap_abs, args.gap_factor * med):
                flag, note = ("GAP?", f"超前({d:+.2f}%) 约 {d / med:.0f} 页，疑似缺页"
                              if med else "增量异常大")
        if prev is not None and seg != seg_of(prev["file"]) and flag == "ok":
            note = "跨批次/跨段边界"
        flags.append(flag)
        pctrows.append((i + 1, seg, idx, os.path.basename(r["file"]), r["pct"],
                        "" if d is None else f"{d:+.3f}", flag, note,
                        r["ui_hits"], r["chars"]))

    with open(args.out, "w") as f:
        f.write("file\tok\tpct\tchars\ttext_b64\n")
        for r in rows:
            tb = base64.b64encode(r["text"].encode()).decode()
            f.write(f"{r['file']}\t1\t{r['pct']}\t{r['chars']}\t{tb}\n")

    if args.pct_list:
        with open(args.pct_list, "w") as f:
            f.write("n\tsegment\tidx\tfile\tpct\tdelta_prev\tflag\tnote\tui_hits\tchars\n")
            for t in pctrows:
                f.write("\t".join(str(x) for x in t) + "\n")

    # 段汇总
    segs = {}
    for r in rows:
        segs.setdefault(seg_of(r["file"]), []).append(r)
    print(f"# 页数={len(rows)} 段数={len(segs)} 段内每页增量中位数={med:.3f}% "
          f"(中位页数≈{1 / med:.1f} 页/%)" if med else f"# 页数={len(rows)} 段数={len(segs)}")
    seg_firstlast = {s: (v[0]["pct"], v[-1]["pct"], len(v)) for s, v in sorted(segs.items())}
    print("# 段  首页%→末页%  (页数)")
    prev = None
    for s, (a, b, n) in seg_firstlast.items():
        print(f"# {s[-3:]}  {a or '-'} → {b or '-'}  ({n} 页)")
    print("# 相邻段边界（上段末页% → 下段首页%）：")
    keys = sorted(seg_firstlast)
    for i in range(1, len(keys)):
        a = seg_firstlast[keys[i - 1]][1]
        b = seg_firstlast[keys[i]][0]
        note = ""
        try:
            d = float(b) - float(a)
            note = f"Δ={d:+.2f}% ≈ {d / med:.1f} 页" if med else f"Δ={d:+.2f}%"
            if d < -0.05:
                note += "  ← 回退（重叠/重复录）"
            elif d > max(args.gap_abs, args.gap_factor * med):
                note += "  ← 疑断片缺页"
        except ValueError:
            note = "百分数缺失"
        print(f"#   {keys[i - 1][-3:]}→{keys[i][-3:]}: {a or '-'} → {b or '-'}  {note}")
    bad = [(t[3], t[6], t[7]) for t in pctrows if t[6] != "ok"]
    print(f"# UI 串被剔出正文的页数={sum(1 for r in rows if r['ui_hits'])}"
          f"（共剔 {sum(r['ui_hits'] for r in rows)} 处）")
    print(f"# 异常页 {len(bad)}：")
    for b in bad[:40]:
        print(f"#   {b[0]} {b[1]} {b[2]}")
    print(f"__PCT__ {len(rows)} {sum(1 for r in rows if not r['pct'])} {len(bad)}")
    return 0


def seg_of(path):
    return os.path.basename(path).split(".")[0]


def page_of(path):
    b = os.path.basename(path)
    return b.split(".")[1] if b.count(".") >= 2 else ""


if __name__ == "__main__":
    sys.exit(main())

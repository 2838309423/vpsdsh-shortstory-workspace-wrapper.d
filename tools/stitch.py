#!/usr/bin/env python3
"""把「稳定窗口帧」的 OCR 逐页结果拼成连续正文（v2）。

设计（基于实测）：
  * 阅读器每次翻页屏幕前进约一屏（约 10 行），相邻稳定页在文字上**几乎不重叠**，
    只有 0~2 个字被切在页边界；
  * 所以用 difflib 的「最长匹配块」找锚点（逐字编辑距离测不出这种小重叠）；
  * 锚点必须靠近上一页结尾（slack 内）且落在下一页开头才算真重叠；
  * 录屏分段边界常常整页重复 ⇒ 单独走"整页重复"与"放宽窗口/slack"两条路；
  * 阅读器章末 UI（"本章说/去写章评"）：整页丢、页尾削掉。

用法：
  python3 stitch.py --tsv ocr.tsv [--out corpus.txt] [--audit audit.tsv]
      [--tail-window 130] [--head-window 130] [--min-anchor 8] [--slack 25]
"""
import argparse
import base64
import difflib
import os
import re
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in s if not ch.isspace())


def norm_map(s):
    """返回 (norm_str, 每个 norm 字符在 s 中的下标)。"""
    out, idx = [], []
    for i, ch in enumerate(unicodedata.normalize("NFKC", s)):
        if not ch.isspace():
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


# 阅读器自己的 UI 尾巴（章末"本章说 / 去写章评"），不是正文
UI_TAIL = re.compile(r"\s*本章说\s*去写章评\s*>?\s*$")


def strip_ui(text):
    """去掉正文尾部的阅读器 UI 文字；返回 (正文, 是否整页都是 UI)。"""
    t = UI_TAIL.sub("", text).strip()
    if not t or len(re.sub(r"[\s本章说去写章评>·、,，。.!！?？]+", "", t)) == 0:
        return "", True
    return t, False


def find_cut(prev, cur, tail_w, head_w, min_anchor, slack):
    """在 prev 尾部 / cur 头部之间找锚点，返回 cur 需要切掉的归一化字符数。"""
    pn_all = norm(prev)
    cn_all = norm(cur)
    pn = pn_all[-tail_w:]
    cn = cn_all[:head_w]
    if len(pn) < min_anchor or len(cn) < min_anchor:
        return 0
    p_off = max(0, len(pn_all) - tail_w)
    sm = difflib.SequenceMatcher(None, pn, cn, autojunk=False)
    best = 0
    for a, b, size in sm.get_matching_blocks():
        if size < min_anchor:
            continue
        p_end = p_off + a + size                    # 锚点在 prev 里的终点
        if len(pn_all) - p_end > slack:             # 必须贴近 prev 结尾
            continue
        if b > slack:                               # 必须贴近 cur 开头
            continue
        if b + size > best:
            best = b + size                         # 重复长度
    return best


def cut_head(cur, n_norm_chars):
    _, idx = norm_map(cur)
    if n_norm_chars <= 0:
        return cur
    if n_norm_chars >= len(idx):
        return ""
    return cur[idx[n_norm_chars]:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--audit", default="")
    ap.add_argument("--tail-window", type=int, default=130)
    ap.add_argument("--head-window", type=int, default=130)
    ap.add_argument("--min-anchor", type=int, default=8)
    ap.add_argument("--slack", type=int, default=25)
    ap.add_argument("--sep", default="\n\n", help="页间连接符")
    ap.add_argument("--max-hit", type=int, default=0)
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
    if args.max_hit:
        rows = rows[:args.max_hit]

    parts, audit = [], []
    seen_recent = []                    # 最近几页的归一化文本，用于整页去重
    last_text = ""                      # 上一张**未被整页丢掉**的页
    last_seg = ""
    for i, d in enumerate(rows):
        t, ui_only = strip_ui(d["text"].strip())
        tn = norm(t)
        seg_b = os.path.basename(d["file"]).split(".")[0]
        if ui_only:
            parts.append("")
            audit.append((os.path.basename(d["file"]), 0, 0, "ui-page"))
            continue
        if i == 0:
            parts.append(t)
            audit.append((os.path.basename(d["file"]), 0, len(tn), "first"))
            seen_recent.append(tn)
            last_text, last_seg = t, seg_b
            continue
        # 整页重复（录屏分段常在边界重复整整一页）
        if len(tn) >= 40 and tn in seen_recent[-4:]:
            parts.append("")
            audit.append((os.path.basename(d["file"]), len(tn), len(tn), "dup-page"))
            continue
        seen_recent.append(tn)
        cross = last_seg != seg_b       # 跨片段边界：录屏分段会整页重复，放宽
        cut = find_cut(last_text, t,
                       args.tail_window if not cross else max(args.tail_window, 500),
                       args.head_window if not cross else max(args.head_window, 500),
                       args.min_anchor if not cross else max(10, args.min_anchor),
                       args.slack if not cross else max(args.slack, 150))
        if cut > (0.8 if not cross else 1.0) * len(tn):
            cut = 0                     # 安全阀（跨段允许整页被切）
        parts.append(cut_head(t, cut))
        audit.append((os.path.basename(d["file"]), cut, len(tn),
                      "cross" if cross else "same"))
        last_text, last_seg = t, seg_b

    full = args.sep.join(p.strip() for p in parts if p.strip())
    out = args.out or os.path.splitext(args.tsv)[0] + ".corpus.txt"
    with open(out, "w") as f:
        f.write(full + "\n")
    au = args.audit or os.path.splitext(args.tsv)[0] + ".audit.tsv"
    with open(au, "w") as f:
        f.write("file\tcut_chars\tpage_chars\tboundary\n")
        for r in audit:
            f.write("\t".join(map(str, r)) + "\n")

    cuts = [a[1] for a in audit[1:]]
    hit = [c for c in cuts if c]
    cross_hit = [a for a in audit[1:] if a[3] == "cross"]
    print(f"# 页数={len(rows)} 正文字数={len(norm(full))}")
    print(f"# 重叠命中 {len(hit)}/{len(cuts)}  中位切字="
          f"{sorted(hit)[len(hit)//2] if hit else 0} 最大={max(hit) if hit else 0}")
    print(f"# 跨片段边界 {len(cross_hit)} 处，其中命中重叠 "
          f"{sum(1 for a in cross_hit if a[1])} 处")
    print(f"# 正文: {out}")
    print(f"# 审计: {au}")
    print(f"__STITCH__ {len(rows)} {len(norm(full))} {len(hit)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

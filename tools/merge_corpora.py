#!/usr/bin/env python3
"""把「新批次拼接稿」接到「旧正文」后面，跨批次重叠只留一份，并落审计。

背景（2026-10-10）：S01~S30 的正文已经成稿，末尾停在「……场面登时大乱。」；
S31 开头又重复录了这段（甲方指出重叠区域截至「场面登时大乱」）。直接 cat 会在
接缝处留一段重复正文，所以这里用 difflib 最长匹配块找锚点，把新稿开头重复的部分
切掉，并在段落边界对齐。

用法：
  python3 merge_corpora.py --old 旧正文.txt --new 新拼接稿.txt --out 合并.txt \
      [--report 接缝审计.tsv] [--tail 800] [--head 4000] [--min-anchor 30] [--slack 40]
末行：__MERGE__ <匹配长度> <切掉字数> <合并后字数>
"""
import argparse
import difflib
import re
import sys
import unicodedata


def norm_map(s):
    out, idx = [], []
    for i, ch in enumerate(unicodedata.normalize("NFKC", s)):
        if not ch.isspace():
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--tail", type=int, default=800)
    ap.add_argument("--head", type=int, default=4000)
    ap.add_argument("--min-anchor", type=int, default=30)
    ap.add_argument("--slack", type=int, default=40,
                    help="锚点终点离旧文末尾允许差多少字")
    args = ap.parse_args()

    old = open(args.old).read()
    new = open(args.new).read()
    ON, oidx = norm_map(old)
    NN, nidx = norm_map(new)
    tail = ON[-args.tail:]
    head = NN[:args.head]
    t_off = max(0, len(ON) - args.tail)

    sm = difflib.SequenceMatcher(None, tail, head, autojunk=False)
    best = None
    for a, b, size in sm.get_matching_blocks():
        if size < args.min_anchor:
            continue
        t_end = t_off + a + size          # 锚点在旧文里的终点
        if len(ON) - t_end > args.slack:  # 必须贴近旧文末尾
            continue
        if best is None or size > best[2]:
            best = (a, b, size)
    if best is None:
        print(f"!! 没找到 ≥{args.min_anchor} 字的跨批次锚点：旧文与新稿可能不重叠"
              f"（或中间断片缺页），请人工核对。", file=sys.stderr)
        merged = old.rstrip() + "\n\n" + new.lstrip()
        drop_note = "NO-ANCHOR"
        raw_cut = 0
        mtxt = ""
        seam_mode = "para"
        old_slack = 0
    else:
        a, b, size = best
        t_end = t_off + a + size
        old_slack = len(ON) - t_end          # 旧文末尾多出、锚点没覆盖到的字数
        mtxt = tail[a:a + size]
        # 锚点在**新稿**里的终点就是接缝：这里绝不往后跳到下一个段落起点——
        # 旧文可能停在段中，跳段会把真实的新内容当重复删掉（2026-10-10 踩过）。
        raw_cut = nidx[b + size] if (b + size) < len(nidx) else len(new)
        pre = new[:raw_cut]
        breaks = list(re.finditer(r"\n\s*\n", pre))
        if breaks:
            at_para_start = pre[breaks[-1].end():].strip() == ""
        else:
            at_para_start = pre.strip() == ""
        tail_new = new[raw_cut:]
        if at_para_start:
            merged = old.rstrip() + "\n\n" + tail_new.lstrip()
            seam_mode = "para"
        else:
            merged = old.rstrip() + tail_new      # 段中续写，不加空行
            seam_mode = "inline"
        raw_cut = len(re.sub(r"\s", "", pre))
        drop_note = "ok" if old_slack <= args.slack else "old-tail-extra"

    if args.report:
        nospace = re.compile(r"\s")
        anchor_pos = merged.find(mtxt[:20]) if mtxt else -1
        join_at = len(old.rstrip())
        ctx = merged[max(0, join_at - 70):join_at + 70].replace("\n", "⏎")
        with open(args.report, "w") as f:
            f.write("item\tvalue\n")
            f.write(f"old_chars\t{len(nospace.sub('', old))}\n")
            f.write(f"new_chars\t{len(NN)}\n")
            f.write(f"anchor_len\t{len(mtxt)}\n")
            f.write(f"anchor_in_old_pos\t{anchor_pos}\n")
            f.write(f"old_tail_not_covered\t{old_slack}\n")
            f.write(f"dropped_chars_at_seam\t{raw_cut}\n")
            f.write(f"seam_mode\t{seam_mode}\n")
            f.write(f"status\t{drop_note}\n")
            f.write(f"anchor_head\t{mtxt[:60]}\n")
            f.write(f"anchor_tail\t{mtxt[-60:]}\n")
            f.write(f"seam_context\t{ctx}\n")
            f.write(f"merged_chars\t{len(nospace.sub('', merged))}\n")

    with open(args.out, "w") as f:
        f.write(merged.rstrip() + "\n")
    mchars = len(re.sub(r"\s", "", merged))
    print(f"# 锚点长度={len(mtxt)} 接缝切掉={raw_cut} 字 接缝方式={seam_mode} 状态={drop_note}")
    print(f"# 锚点尾: …{mtxt[-40:]}")
    print(f"# 旧文末尾未被锚点覆盖的字数={old_slack}")
    print(f"# 合并后: {args.out}")
    print(f"__MERGE__ {len(mtxt)} {raw_cut} {mchars}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""两份正文互查：旧稿有多少能在新稿里找到、新稿比旧稿多出哪些段落。

用途（2026-10-10）：第一遍取页把「单帧压缩噪声劈开的静止窗」整页丢了（约 9%），
修 stable_pages2.py 后重抽。要回答两件事：
  1) 新稿是否**完全包含**旧稿（不能因为重抽反而丢内容）——用 40 字滑窗命中率衡量；
  2) 新稿多出来的那部分**是不是正文**、长什么样——把未命中的窗拼成片段打印/落盘。

做法：归一化（NFKC + 去空白）后，把新稿切成 40 字窗建立集合；旧稿同样切窗查命中。
片段用 difflib 对齐输出（左右各留 40 字上下文），便于人工一眼判「是补回的正文」。

用法：
  python3 compare_corpora.py --old 旧.txt --new 新.txt [--win 40] [--step 20]
      [--report 差异片段.tsv] [--max-print 20]
末行：__CMP__ <旧窗数> <旧窗命中数> <新窗数> <新独有窗数>
"""
import argparse
import re
import sys
import unicodedata


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKC", s) if not c.isspace())


def windows(s, win, step):
    return [s[i:i + win] for i in range(0, max(0, len(s) - win), step)]


def grams(s, win):
    """字符串里**所有** win 字连续子串（用作精确子串查找的集合）。

    注意：不能用「隔 step 取样」的窗去互相查——两份正文只要有 1 个字的插入，
    后面所有窗的相位就错开了，取样窗命中率会假性崩到 3%（2026-10-10 踩过）。
    """
    return {s[i:i + win] for i in range(max(0, len(s) - win + 1))}


def merge_spans(idx_list, win, step):
    """把命中失败的窗下标并成连续片段区间。"""
    spans = []
    for i in sorted(idx_list):
        a, b = i, i + win
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--win", type=int, default=40)
    ap.add_argument("--step", type=int, default=20)
    ap.add_argument("--report", default="")
    ap.add_argument("--max-print", type=int, default=20)
    args = ap.parse_args()

    O = norm(open(args.old).read())
    N = norm(open(args.new).read())
    owin = windows(O, args.win, args.step)
    nset = grams(N, args.win)          # 精确子串集合（全相位）
    miss = [i for i, w in enumerate(owin) if w not in nset]
    hit = len(owin) - len(miss)

    nwin = windows(N, args.win, args.step)
    oset = grams(O, args.win)
    extra = [i for i, w in enumerate(nwin) if w not in oset]
    spans = merge_spans([i * args.step for i in extra], args.win, args.step)

    print(f"# 旧稿 {len(O)} 字 → 滑窗 {len(owin)}（{args.win}字/{args.step}字步长）"
          f"命中新稿 {hit} （{hit / max(1, len(owin)):.2%}）")
    print(f"# 新稿 {len(N)} 字（比旧稿 {len(N) - len(O):+d} 字），"
          f"新稿独有窗 {len(extra)} ⇒ 并成 {len(spans)} 段")
    if miss:
        mspans = merge_spans([i * args.step for i in miss], args.win, args.step)
        print(f"# !! 旧稿有 {len(miss)} 个窗在新稿里找不到，并成 {len(mspans)} 段"
              f"（重抽丢内容？逐段列前几段）")
        for a, b in mspans[:args.max_print]:
            print(f"#   旧[{a}:{b}] …{O[a:b + 20]}")
    print(f"# 新稿独有片段（应全是补回的正文，逐段给上下文）：")
    for a, b in spans[:args.max_print]:
        ctx0 = max(0, a - 40)
        ctx1 = min(len(N), b + 40)
        print(f"#   [{a}:{b}] {b - a}字  前文…{N[ctx0:a]}  片段【{N[a:b]}】  后文{N[b:ctx1]}…")
    if args.report:
        with open(args.report, "w") as f:
            f.write("kind\tstart\tend\tchars\tbefore(40)\tfragment\tafter(40)\n")
            for a, b in merge_spans([i * args.step for i in miss], args.win, args.step):
                f.write(f"old-missing-in-new\t{a}\t{b}\t{b - a}\t\t{O[a:b]}\t\n")
            for a, b in spans:
                f.write("new-extra\t{}\t{}\t{}\t{}\t{}\t{}\n".format(
                    a, b, b - a, N[max(0, a - 40):a], N[a:b], N[b:b + 40]))
        print(f"# 明细: {args.report}")
    print(f"__CMP__ {len(owin)} {hit} {len(nwin)} {len(extra)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

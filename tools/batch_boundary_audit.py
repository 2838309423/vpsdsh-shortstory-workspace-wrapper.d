#!/usr/bin/env python3
"""批次边界对账：每个 S(N)→S(N+1) 接缝到底是「重叠了」还是「断片差剧情了」。

两路证据合用（甲方 2026-10-10 要求：百分数只当相对标尺）：
  A) **正文重复**：stitch.py 的审计里，跨段边界被切掉 ≥30 字 = 上一段末尾在下一段开头
     又录了一遍（重叠）；整页重复记为 dup-page。
  B) **右下角百分数**：段末页% → 下段首页%。本批实测每页只涨约 0.018%（显示 2 位小数，
     量化步长 0.01% ≈ 0.5 页）⇒ 只能可靠发现 ≥4 页的缺口，判不了单页重复；
     所以 A 为主、B 为辅。

用法：
  python3 batch_boundary_audit.py --pct-list pct清单.tsv --audit stitch_audit.tsv \
      --out 批次边界对账.tsv [--seg-out 段汇总.tsv]
末行：__BOUNDARY__ <接缝数> <重叠> <整页重复> <疑似断片> <连续>
"""
import argparse
import collections
import os
import statistics
import sys


def seg_of(f):
    return os.path.basename(f).split(".")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct-list", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seg-out", default="")
    ap.add_argument("--gap-pages", type=float, default=4.0,
                    help="百分数折算缺口达到这么多页才报疑似断片")
    args = ap.parse_args()

    pct = []
    with open(args.pct_list) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == len(hdr):
                pct.append(dict(zip(hdr, p)))
    aud = {}
    with open(args.audit) as f:
        h = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) == len(h):
                d = dict(zip(h, p))
                aud[os.path.basename(d["file"])] = d

    # 段内每页增量中位数（相对标尺的刻度）
    per = []
    for i in range(1, len(pct)):
        a, b = pct[i - 1], pct[i]
        if seg_of(a["file"]) != seg_of(b["file"]):
            continue
        try:
            x, y = float(a["pct"]), float(b["pct"])
        except ValueError:
            continue
        if y > x:
            per.append(y - x)
    med = statistics.median(per) if per else 0.0

    segs = collections.OrderedDict()
    for r in pct:
        segs.setdefault(seg_of(r["file"]), []).append(r)

    rows, n_overlap, n_dup, n_gap, n_ok = [], 0, 0, 0, 0
    keys = list(segs)
    for i in range(1, len(keys)):
        sp, sn = keys[i - 1], keys[i]
        pl = segs[sp][-1]
        nf = segs[sn][0]
        d = aud.get(os.path.basename(pl["file"]), {})
        btype = d.get("boundary", "?")
        cut = int(d.get("cut_chars", 0) or 0)
        try:
            delta = round(float(nf["pct"]) - float(pl["pct"]), 4)
            est = round(delta / med, 2) if med else ""
        except ValueError:
            delta, est = "", ""
        if btype == "dup-page":
            verdict = "重叠(整页重复)"
            n_dup += 1
        elif cut >= 30:
            verdict = f"重叠(切掉 {cut} 字)"
            n_overlap += 1
        elif isinstance(est, float) and est >= args.gap_pages:
            verdict = f"疑似断片(约 {est:.0f} 页)"
            n_gap += 1
        else:
            verdict = "连续(无重叠/无缺口)"
            n_ok += 1
        rows.append([sp, sn, pl["pct"], nf["pct"], f"{delta:+}" if delta != "" else "",
                     est, pl["chars"], nf["chars"], btype, cut, verdict])

    with open(args.out, "w") as f:
        f.write("seg_prev\tseg_next\tprev_last_pct\tnext_first_pct\tpct_delta\t"
                "est_pages_delta\tprev_last_chars\tnext_first_chars\t"
                "stitch_boundary\tstitch_cut_chars\tverdict\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    if args.seg_out:
        with open(args.seg_out, "w") as f:
            f.write("segment\tpages\tfirst_pct\tlast_pct\tpct_span\t"
                    "est_pages_by_pct\tchars\tflags\n")
            for s, v in segs.items():
                try:
                    span = round(float(v[-1]["pct"]) - float(v[0]["pct"]), 3)
                    est = round(span / med, 1) if med else ""
                except ValueError:
                    span, est = "", ""
                fl = ",".join(sorted({r["flag"] for r in v if r["flag"] != "ok"}))
                f.write(f"{s}\t{len(v)}\t{v[0]['pct']}\t{v[-1]['pct']}\t{span}\t{est}\t"
                        f"{sum(int(r['chars']) for r in v)}\t{fl}\n")

    if med:
        print(f"# 每页增量中位数={med:.4f}%  ⇒ 1 页≈{med:.4f}% ，"
              f"百分数 0.01% 的步长≈{0.01 / med:.1f} 页")
    else:
        print("# 无可用增量（百分数全缺）")
    print(f"# 接缝 {len(rows)} 处：重叠 {n_overlap}、整页重复 {n_dup}、"
          f"疑似断片 {n_gap}、连续 {n_ok}")
    for r in rows:
        if r[10] != "连续(无重叠/无缺口)":
            print(f"#   {r[0][-3:]}→{r[1][-3:]}: {r[2]}%→{r[3]}% Δ={r[4]} "
                  f"(≈{r[5]} 页) {r[10]}")
    print(f"# 明细: {args.out}")
    print(f"__BOUNDARY__ {len(rows)} {n_overlap} {n_dup} {n_gap} {n_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

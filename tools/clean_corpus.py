#!/usr/bin/env python3
"""清理 OCR 正文里的「占位符噪声」，并给出修补清单。

背景：qwen3-vl-flash 在"看不清"时会输出 `⟨?⟩`（提示词让它这么做）。
实测有两类：
  * **噪声**：一个可辨认的汉字被标成 ⟨?⟩（例如"彻底搜⟨?⟩"里其实是"索"）；
  * **真缺口**：图片边缘被裁掉半个字（例如"东侧⟨?⟩"后确实缺一个字）。

做法（保守，不猜字）：
  * 把连续的 `⟨?⟩` 串压成**单个** `□`；
  * 单独一个 `⟨?⟩` 也换成 `□`（保留"这里有问题"的定位信息）；
  * `--strip-all` 则全部删掉（要干净正文时用）；
  * 输出 `--report` 清单：每个 □ 的前后 12 字 + 所在页文件，供人工核对。
"""
import argparse
import os
import re
import sys

PLACE = re.compile(r"(?:⟨\?⟩|<\?>|〔\?〕)+")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--strip-all", action="store_true",
                    help="连 □ 都不留，直接删掉")
    args = ap.parse_args()

    txt = open(args.inp).read()
    hits = []
    for m in PLACE.finditer(txt):
        a = max(0, m.start() - 12)
        b = min(len(txt), m.end() + 12)
        hits.append((txt[a:m.start()].replace("\n", " "),
                     txt[m.end():b].replace("\n", " ")))
    out = PLACE.sub("" if args.strip_all else "□", txt)
    # 段内多余的空白/空段落整理
    out = re.sub(r"[ \t]+", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    with open(args.out, "w") as f:
        f.write(out)

    if args.report:
        with open(args.report, "w") as f:
            f.write("no\tbefore(12字)\tafter(12字)\n")
            for i, (a, b) in enumerate(hits, 1):
                f.write(f"{i}\t{a}\t{b}\n")
    n_run = len(re.findall(PLACE, txt))
    n_char = sum(len(m.group(0)) for m in PLACE.finditer(txt))
    print(f"# 占位符串 {n_run} 处（原始 {n_char} 字符）")
    print(f"# 清理后正文: {args.out}  ({len(out)} 字符)")
    if args.report:
        print(f"# 修补清单: {args.report}")
    print(f"__CLEAN__ {n_run} {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

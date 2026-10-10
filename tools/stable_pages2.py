#!/usr/bin/env python3
"""稳定页检测 v2 —— 专治「左右滑动式翻页」。

实测机制（七猫阅读器 + 安卓录屏）：
  * 翻页是**左右滑动动画**：旧页从左侧滑出、新页从右侧滑入，
    滑动中屏幕上有两页并存（左页残余 + 右页新生），持续约 0.4s；
  * 因此只判「整屏像素不动」会把滑动中的静止瞬间误判成稳定页。

做法：
  1) 每帧只取**整幅**灰度小图 196x282（源 980x1408 约 1/5）；
  2) 把宽度切成若干条带，逐条带算「垂直变化量」；
     滑动进行时，右侧条带会出现"新页"，左中条带也可能变化；
  3) 判据：**所有条带**的垂直变化量都 < --vth，且持续 >= --min-sec；
  4) 稳定窗口中点取**原分辨率**帧作为该页代表帧。

用法（以能读源视频的身份跑）：
  python3 stable_pages2.py --video X.mp4 --outdir DIR [--crop W:H:X:Y]
      [--out-crop W:H:X:Y]   # 判稳用 --crop，存代表帧用 --out-crop（缺省同 --crop）
      [--fps 10] [--vth 1.2] [--min-sec 1.2] [--scale 0] [--save-frames]

--out-crop 的来历（2026-10-10）：全屏录屏 1080x2400 里阅读器正文区是
crop=980:1408:50:224，但右下角「翻页进度百分数」在 y≈1600~1690，只存 1408 高
会把百分数切掉一半。判稳继续用 980x1408（与 S01~S30 那批取页结果保持一致），
存档帧改成 980x1486（y 224~1710，含完整的「电量/时间 + 百分数」底栏）。
"""
import argparse
import os
import subprocess
import sys

FF = os.environ.get("FFMPEG", "/tmp/vidtool/bin/ffmpeg")
SW, SH = 196, 282
BANDS = 4          # 横向切 4 条带


def band_diffs(prev, cur, sw, sh, bands):
    """逐条带的行墨迹 L1 差（条带内先按行求和）。"""
    bw = sw // bands
    out = []
    for bi in range(bands):
        x0 = bi * bw
        s = 0.0
        for y in range(sh):
            base = y * sw + x0
            pa = sum(255 - v for v in prev[base:base + bw])
            pb = sum(255 - v for v in cur[base:base + bw])
            s += abs(pa - pb)
        out.append(s / (bw * sh))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--crop", default="")
    ap.add_argument("--out-crop", default="", help="存代表帧用的 crop W:H:X:Y（缺省同 --crop）")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--vth", type=float, default=1.2)
    ap.add_argument("--bridge-th", type=float, default=0.5,
                    help="成段判据（抗压缩噪声）；取帧仍取最长严格静止子段的中点")
    ap.add_argument("--min-sec", type=float, default=1.2)
    ap.add_argument("--scale", type=int, default=0)
    ap.add_argument("--quality", type=int, default=4)
    ap.add_argument("--save-frames", action="store_true")
    ap.add_argument("--dump-diff", default="")
    args = ap.parse_args()

    name = os.path.splitext(os.path.basename(args.video))[0]
    # 注意：crop 参数是 W:H:X:Y（冒号分隔），不能再把冒号换成逗号——
    # 逗号在 filtergraph 里是「下一个滤镜」的分隔符（S01~S30 那批没传 --crop，
    # 所以这个坑一直没踩到；2026-10-10 处理全屏录屏时暴露，已修）。
    crop = args.crop
    vf = [f"fps={args.fps}"]
    if crop:
        vf.append(f"crop={crop}")
    vf.append(f"scale={SW}:{SH}")
    p = subprocess.run([FF, "-v", "error", "-i", args.video, "-vf", ",".join(vf),
                        "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True)
    buf = p.stdout
    fsz = SW * SH
    n = len(buf) // fsz
    log = lambda *a: print(*a, file=sys.stderr, flush=True)

    frames = [buf[k * fsz:(k + 1) * fsz] for k in range(n)]
    flags = [False] * n
    df = open(args.dump_diff, "w") if args.dump_diff else None
    if df:
        df.write("idx\tt_s\t" + "\t".join(f"band{i}" for i in range(BANDS)) + "\tmaxband\n")
    mx_of = [0.0] * n
    for k in range(1, n):
        bd = band_diffs(frames[k - 1], frames[k], SW, SH, BANDS)
        mx = max(bd)
        mx_of[k] = mx
        flags[k] = mx < args.vth
        if df:
            df.write(f"{k}\t{k/args.fps:.2f}\t" +
                     "\t".join(f"{x:.3f}" for x in bd) + f"\t{mx:.3f}\n")
    if df:
        df.close()

    # —— 抗噪：单个压缩噪声帧会把一个静止窗口劈成两半，两半都短于 min_sec 就被整页丢掉
    #    （2026-10-10 实测：s34 在 17.4~19.2s 的静止窗被 17.8s 那个 0.068 的噪声帧劈开，
    #     两个子段 0.4s / 1.3s 都不达标 ⇒ 整页漏掉，正文出现约 100 字断口）。
    #    办法：**成段判据放宽到 bridge_th**（噪声级 0.5），但**取帧时刻仍取最长"严格静止"
    #    子段的中点**，保证代表帧不会落在翻页动画里（动画帧的 maxband 通常 3~30）。
    usable = [mx_of[k] < args.bridge_th for k in range(n)]
    runs, s0 = [], None
    for k in range(n):
        if usable[k]:
            if s0 is None:
                s0 = k
        else:
            if s0 is not None:
                runs.append((s0, k - 1))
                s0 = None
    if s0 is not None:
        runs.append((s0, n - 1))
    allruns = runs
    runs = [(a, b) for a, b in allruns if (b - a + 1) / args.fps >= args.min_sec]

    def pick_time(a, b):
        """在 [a,b] 里挑最长严格静止子段的中点（没有就退回整段中点）。"""
        best, s = (0, a, b), None
        for k in range(a, b + 2):
            ok = k <= b and flags[k]
            if ok and s is None:
                s = k
            elif not ok and s is not None:
                if k - s > best[0]:
                    best = (k - s, s, k - 1)
                s = None
        _, pa, pb = best
        return (pa + pb) / 2.0 / args.fps, (pb - pa + 1) / args.fps

    log(f"# {name}: 帧={n} 严格静止帧占比={sum(flags)/n:.1%} "
        f"抗噪可用帧占比={sum(usable)/n:.1%} "
        f"原始段={len(allruns)} 达标窗口={len(runs)} "
        f"(min_sec={args.min_sec}, vth={args.vth}, bridge_th={args.bridge_th})")

    if args.save_frames:
        pdir = os.path.join(args.outdir, "pages")
        os.makedirs(pdir, exist_ok=True)
        outcrop = args.out_crop or args.crop
        vfo = []
        if outcrop:
            vfo.append(f"crop={outcrop}")
        if args.scale:
            vfo.append(f"scale={args.scale}:-2")
        rows = []
        for i, (a, b) in enumerate(runs):
            mid, strict_dur = pick_time(a, b)
            out = os.path.join(pdir, f"{name}.p{i:03d}.jpg")
            cmd = [FF, "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", args.video,
                   "-frames:v", "1"]
            if vfo:
                cmd += ["-vf", ",".join(vfo)]
            cmd += ["-q:v", str(args.quality), out]
            subprocess.run(cmd, capture_output=True)
            rows.append((i, a / args.fps, b / args.fps, (b - a + 1) / args.fps, mid, out))
        tsv = os.path.join(args.outdir, "pages.tsv")
        with open(tsv, "w") as f:
            f.write("video\tidx\tstart_s\tend_s\tdur_s\tmid_s\tfile\n")
            for r in rows:
                f.write(f"{name}\t{r[0]}\t{r[1]:.2f}\t{r[2]:.2f}\t{r[3]:.2f}\t"
                        f"{r[4]:.3f}\t{r[5]}\n")
        log(f"# 代表帧 {len(rows)} 张 -> {pdir}\n# 清单 {tsv}")

    print(f"__STABLE_V2__ {n} {len(runs)} {len(allruns)} {sum(flags)/n:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

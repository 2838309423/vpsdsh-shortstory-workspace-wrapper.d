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
      [--fps 10] [--vth 1.2] [--min-sec 1.2] [--scale 0] [--save-frames]
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
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--vth", type=float, default=1.2)
    ap.add_argument("--min-sec", type=float, default=1.2)
    ap.add_argument("--scale", type=int, default=0)
    ap.add_argument("--quality", type=int, default=4)
    ap.add_argument("--save-frames", action="store_true")
    ap.add_argument("--dump-diff", default="")
    args = ap.parse_args()

    name = os.path.splitext(os.path.basename(args.video))[0]
    crop = args.crop.replace(":", ",") if args.crop else ""
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
    for k in range(1, n):
        bd = band_diffs(frames[k - 1], frames[k], SW, SH, BANDS)
        mx = max(bd)
        flags[k] = mx < args.vth
        if df:
            df.write(f"{k}\t{k/args.fps:.2f}\t" +
                     "\t".join(f"{x:.3f}" for x in bd) + f"\t{mx:.3f}\n")
    if df:
        df.close()

    runs, s0 = [], None
    for k in range(n):
        if flags[k]:
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
    log(f"# {name}: 帧={n} 静止帧占比={sum(flags)/n:.1%} "
        f"原始段={len(allruns)} 达标窗口={len(runs)} "
        f"(min_sec={args.min_sec}, vth={args.vth})")

    if args.save_frames:
        pdir = os.path.join(args.outdir, "pages")
        os.makedirs(pdir, exist_ok=True)
        vfo = []
        if crop:
            vfo.append(f"crop={crop}")
        if args.scale:
            vfo.append(f"scale={args.scale}:-2")
        rows = []
        for i, (a, b) in enumerate(runs):
            mid = (a + b) / 2.0 / args.fps
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

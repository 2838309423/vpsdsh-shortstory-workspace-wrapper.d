#!/usr/bin/env bash
# crop-android-novelvideo.sh —— 手机录屏「小说文本区」取帧定坐标 + 裁剪
#
# 用法：
#   bin/crop-android-novelvideo.sh probe    # 取帧 + 打印元数据（用于人工/视觉定矩形）
#   RECT=W:H:X:Y bin/crop-android-novelvideo.sh crop   # 按矩形裁剪输出
#
# 环境变量：
#   SRC_DIR   源目录（默认甲方给的录屏目录）
#   OUT_DIR   输出目录
#   WORK_DIR  取帧与元数据的落地目录（默认 state/video-crop）
#   RECT      crop 模式必填，格式 宽:高:X:Y（X/Y 为左上角坐标）
#   JOBS      并行编码条数（默认 4）
#   FFMPEG/FFPROBE  默认用 $HOME 自装静态版
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FFMPEG="${FFMPEG:-$HOME/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/ffmpeg}"
FFPROBE="${FFPROBE:-$HOME/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/ffprobe}"

SRC_DIR="${SRC_DIR:-/data/home/shortstory/长安二十四时辰/non-cuttedvideo-from-androidphone.d}"
OUT_DIR="${OUT_DIR:-/data/home/shortstory/长安二十四时辰/hasbeen-cut-video-from-androidphone.d}"
WORK_DIR="${WORK_DIR:-$REPO_ROOT/state/video-crop}"
RECT="${RECT:-}"

MODE="${1:-}"

die() { echo "ERROR: $*" >&2; exit 2; }

[[ -x "$FFMPEG"  ]] || die "ffmpeg 不可执行: $FFMPEG"
[[ -x "$FFPROBE" ]] || die "ffprobe 不可执行: $FFPROBE"

# —— 前置可达性检查：把「权限不足」和「真的没文件」区分开 ——
if [[ ! -d "$SRC_DIR" ]]; then
  if [[ -e "$SRC_DIR" ]]; then
    die "源目录存在但不可进入（权限）: $SRC_DIR  —— 先跑: sudo setfacl -m u:$(id -un):x /data/home/shortstory && sudo setfacl -R -m u:$(id -un):rwX \"/data/home/shortstory/长安二十四时辰\""
  fi
  # 逐级回溯，指出第一段不可达的路径
  p="$SRC_DIR"
  while [[ ! -e "$p" && "$p" != "/" ]]; do p="$(dirname "$p")"; done
  die "源路径不可达，卡在: $p  （$(ls -ld "$p" 2>&1)）"
fi

shopt -s nullglob
mapfile -t VIDEOS < <(printf '%s\n' "$SRC_DIR"/*.mp4 | sort)
[[ ${#VIDEOS[@]} -gt 0 ]] || die "源目录里没有 *.mp4: $SRC_DIR"

mkdir -p "$WORK_DIR" || die "无法创建 WORK_DIR: $WORK_DIR"

echo "== 源目录: $SRC_DIR"
echo "== 视频数: ${#VIDEOS[@]}"
echo "== work  : $WORK_DIR"

# ---------------- probe ----------------
do_probe() {
  local meta="$WORK_DIR/probe.tsv"
  : > "$meta"
  printf 'file\tw\th\tdur_s\tvcodec\trotate\n' >> "$meta"

  local v base info w h dur vcodec rot
  for v in "${VIDEOS[@]}"; do
    base="$(basename "$v" .mp4)"
    info="$($FFPROBE -v error -select_streams v:0 \
              -show_entries stream=width,height,codec_name \
              -show_entries stream_side_data=rotation \
              -show_entries format=duration \
              -of default=nw=1 "$v" 2>/dev/null)"
    w=$(sed -n 's/^width=//p'      <<<"$info" | head -1)
    h=$(sed -n 's/^height=//p'     <<<"$info" | head -1)
    dur=$(sed -n 's/^duration=//p' <<<"$info" | head -1)
    vcodec=$(sed -n 's/^codec_name=//p' <<<"$info" | head -1)
    rot=$(sed -n 's/^rotation=//p'  <<<"$info" | head -1)

    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$base" "${w:-?}" "${h:-?}" "${dur:-?}" "${vcodec:-?}" "${rot:-0}" >> "$meta"

    # 每条视频抽 3 帧：5% / 50% / 95% —— 覆盖开头/中间/结尾的 UI 状态，确保矩形对所有帧都"安全"
    local frac tag ts
    for frac in 0.05 0.50 0.95; do
      tag="$(awk -v f="$frac" 'BEGIN{printf "%02d", f*100}')"
      ts="$(awk -v d="${dur:-0}" -v f="$frac" 'BEGIN{printf "%.3f", d*f}')"
      "$FFMPEG" -v error -y -ss "$ts" -i "$v" -frames:v 1 \
        "$WORK_DIR/${base}.p${tag}.png" 2>/dev/null
    done
  done

  echo "== 元数据: $meta"
  column -t -s $'\t' "$meta" 2>/dev/null || cat "$meta"
  echo "== 帧:"
  ls -1 "$WORK_DIR"/*.png 2>/dev/null | sed 's/^/   /'
}

# ---------------- crop ----------------
do_crop() {
  [[ -n "$RECT" ]] || die "crop 模式需要 RECT=W:H:X:Y"
  local W H X Y
  IFS=: read -r W H X Y <<<"$RECT"
  [[ "$W" =~ ^[0-9]+$ && "$H" =~ ^[0-9]+$ && "$X" =~ ^[0-9]+$ && "$Y" =~ ^[0-9]+$ ]] \
    || die "RECT 格式不对（要 宽:高:X:Y 四个非负整数）: $RECT"
  # yuv420p/H.264 要求偶数宽高
  (( W % 2 == 0 )) || { W=$((W-1)); echo "WARN: 宽取偶 -> $W" >&2; }
  (( H % 2 == 0 )) || { H=$((H-1)); echo "WARN: 高取偶 -> $H" >&2; }

  mkdir -p "$OUT_DIR" || die "无法创建 OUT_DIR: $OUT_DIR （需要写权限）"

  local JOBS="${JOBS:-4}"
  echo "== RECT: ${W}:${H}:${X}:${Y}  ->  $OUT_DIR  (并行 $JOBS)"
  local rc=0
  # 只取视频轨 + 可选音轨：手机录屏常带一条 codec=unknown 的 data 轨，
  # 不显式 -map 会让 mp4 封装报 "Could not find tag for codec unknown"。
  export FFMPEG OUT_DIR CROP="${W}:${H}:${X}:${Y}"
  printf '%s\0' "${VIDEOS[@]}" | xargs -0 -P "$JOBS" -n1 bash -c '
    v="$1"; base="$(basename "$v" .mp4)"; out="$OUT_DIR/${base}.mp4"
    if "$FFMPEG" -v error -y -i "$v" \
         -map 0:v:0 -map 0:a? \
         -vf "crop=$CROP" \
         -c:v libx264 -crf 18 -preset veryfast -pix_fmt yuv420p \
         -c:a copy -movflags +faststart \
         "$out"; then
      echo "   OK  $(basename "$out")  $(du -h "$out" | cut -f1)"
    else
      echo "   FAIL $base" >&2; exit 1
    fi' _ || rc=1

  echo "== 输出:"
  ls -la "$OUT_DIR" 2>/dev/null | sed 's/^/   /'
  return $rc
}

case "$MODE" in
  probe) do_probe ;;
  crop)  do_crop ;;
  *) die "用法: $0 probe | RECT=W:H:X:Y $0 crop" ;;
esac

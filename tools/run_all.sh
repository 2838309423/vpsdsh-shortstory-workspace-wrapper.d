#!/usr/bin/env bash
# run_all.sh —— 30 段录屏 → 稳定页帧 → OCR → 拼接正文
# 必须以能读源视频的身份跑（shortstory）；需要 BAILIAN_KEYFILE 指向可读的密钥文件。
set -uo pipefail

SRC_DIR="${SRC_DIR:-/data/home/shortstory/长安二十四时辰/hasbeen-cut-video-from-androidphone.d}"
OUT="${OUT:-/tmp/ca24/out}"
TOOLS="${TOOLS:-/tmp/ca24}"
JOBS="${JOBS:-4}"
export BAILIAN_KEYFILE="${BAILIAN_KEYFILE:-/tmp/ca24/bailian.key}"
export FFMPEG="${FFMPEG:-/tmp/vidtool/bin/ffmpeg}"

mkdir -p "$OUT/frames" "$OUT/logs"

# ---------- 1) 稳定页取帧（每视频一个进程） ----------
extract_one() {
  v="$1"
  base="$(basename "$v" .mp4)"
  [ -f "$OUT/frames/$base/pages.tsv" ] && { echo "SKIP $base"; return 0; }
  mkdir -p "$OUT/frames/$base"
  python3 "$TOOLS/stable_pages2.py" --video "$v" --outdir "$OUT/frames/$base" \
      --fps 10 --vth 0.05 --min-sec 1.5 --scale 0 --save-frames \
      > "$OUT/logs/$base.extract.log" 2>&1
  rc=$?
  echo "$rc $base $(grep -o '__STABLE_V2__.*' "$OUT/logs/$base.extract.log" | tail -1)"
}
export -f extract_one
export OUT TOOLS

if [ "${1:-all}" = "extract" ] || [ "${1:-all}" = "all" ]; then
  echo "== 取帧：$(ls "$SRC_DIR"/*.mp4 | wc -l) 段，并行 $JOBS"
  ls "$SRC_DIR"/*.mp4 | xargs -P "$JOBS" -I{} bash -c 'extract_one "$@"' _ {}
fi

# ---------- 2) OCR ----------
if [ "${1:-all}" = "ocr" ] || [ "${1:-all}" = "all" ]; then
  for d in "$OUT"/frames/*/; do
    base="$(basename "$d")"
    [ -f "$d/ocr.tsv" ] && { echo "SKIP OCR $base"; continue; }
    python3 "$TOOLS/ocr_pages.py" --indir "$d/pages" --out "$d/ocr.tsv" \
        --out-dir "$d/txt" --workers 8 --model qwen3-vl-flash --resize 0 \
        --thinking 0 > "$OUT/logs/$base.ocr.log" 2>&1
    echo "$base rc=$? $(grep -o '__OCR_DONE__.*' "$OUT/logs/$base.ocr.log" | tail -1)"
  done
  # 汇总（表头只取一次）
  head -1 "$(ls "$OUT"/frames/*/ocr.tsv | head -1)" > "$OUT/all_ocr.tsv"
  for f in "$OUT"/frames/*/ocr.tsv; do tail -n +2 "$f" >> "$OUT/all_ocr.tsv"; done
  wc -l "$OUT/all_ocr.tsv"
fi

# ---------- 3) 拼接 ----------
if [ "${1:-all}" = "stitch" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/stitch.py" --tsv "$OUT/all_ocr.tsv" \
      --out "$OUT/corpus_raw.txt" --audit "$OUT/corpus_audit.tsv"
fi
echo "== DONE $1"

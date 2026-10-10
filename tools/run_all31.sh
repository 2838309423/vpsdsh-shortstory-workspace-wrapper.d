#!/usr/bin/env bash
# run_all31.sh —— 七猫全屏录屏（1080x2400）→ 稳定页帧（含右下角百分数）→ OCR
#                 → 摘百分数/剔 UI → 拼接正文 → 清理 → QA → 与旧正文合流
#
# 必须以能读源视频的身份跑（shortstory）；需要 BAILIAN_KEYFILE 指向可读的密钥文件。
# 用法： bash run_all31.sh [extract|ocr|parse|stitch|clean|qa|merge|all]
#   GLOB='*142457-s*.mp4'（默认，S31~S58）| GLOB='*.mp4'（全部 58 段，S01~S58）
set -uo pipefail

SRC_DIR="${SRC_DIR:-/data/home/shortstory/长安十二时辰/non-cuttedvideo-from-androidphone.d}"
GLOB="${GLOB:-*142457-s*.mp4}"                  # 142457 这批 = S31~S58
OUT="${OUT:-/tmp/ca31/out}"
TOOLS="${TOOLS:-/tmp/ca31}"
JOBS="${JOBS:-4}"
DETECT_CROP="${DETECT_CROP:-980:1408:50:224}"   # 判稳：与 S01~S30 那批同一矩形
SAVE_CROP="${SAVE_CROP:-980:1486:50:224}"       # 存帧：加高到含「电量/时间 + 百分数」底栏
VTH="${VTH:-0.05}"                              # 严格静止判据
BRIDGE_TH="${BRIDGE_TH:-0.5}"                   # 抗压缩噪声的成段判据（见 stable_pages2.py）
MIN_SEC="${MIN_SEC:-1.0}"                       # 静止窗口最短时长
OLD_CORPUS="${OLD_CORPUS:-/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/novels/chang-an-24/corpus/长安二十四时辰-正文-全量.txt}"
export BAILIAN_KEYFILE="${BAILIAN_KEYFILE:-/tmp/ca31/bailian.key}"
export FFMPEG="${FFMPEG:-/tmp/vidtool/bin/ffmpeg}"
PROMPT="${PROMPT:-$TOOLS/prompt_pct.txt}"

mkdir -p "$OUT/frames" "$OUT/logs"

# ---------- 1) 稳定页取帧 ----------
extract_one() {
  v="$1"
  base="$(basename "$v" .mp4)"
  [ -f "$OUT/frames/$base/pages.tsv" ] && { echo "SKIP $base"; return 0; }
  mkdir -p "$OUT/frames/$base"
  python3 "$TOOLS/stable_pages2.py" --video "$v" --outdir "$OUT/frames/$base" \
      --crop "$DETECT_CROP" --out-crop "$SAVE_CROP" \
      --fps 10 --vth "$VTH" --bridge-th "$BRIDGE_TH" --min-sec "$MIN_SEC" \
      --scale 0 --save-frames \
      > "$OUT/logs/$base.extract.log" 2>&1
  rc=$?
  echo "$rc $base $(grep -o '__STABLE_V2__.*' "$OUT/logs/$base.extract.log" | tail -1)"
}
export -f extract_one
export OUT TOOLS DETECT_CROP SAVE_CROP VTH BRIDGE_TH MIN_SEC

if [ "${1:-all}" = "extract" ] || [ "${1:-all}" = "all" ]; then
  echo "== 取帧：$(ls $SRC_DIR/$GLOB | wc -l) 段，并行 $JOBS（判稳 $DETECT_CROP / 存帧 $SAVE_CROP，vth=$VTH bridge=$BRIDGE_TH min_sec=$MIN_SEC）"
  ls "$SRC_DIR"/$GLOB | xargs -P "$JOBS" -I{} bash -c 'extract_one "$@"' _ {}
fi

# ---------- 2) OCR ----------
if [ "${1:-all}" = "ocr" ] || [ "${1:-all}" = "all" ]; then
  for d in "$OUT"/frames/*/; do
    base="$(basename "$d")"
    [ -f "$d/ocr.tsv" ] && { echo "SKIP OCR $base"; continue; }
    python3 "$TOOLS/ocr_pages.py" --indir "$d/pages" --out "$d/ocr.tsv" \
        --out-dir "$d/txt" --workers 8 --model qwen3-vl-flash --resize 0 \
        --thinking 0 --prompt "$PROMPT" > "$OUT/logs/$base.ocr.log" 2>&1
    echo "$base rc=$? $(grep -o '__OCR_DONE__.*' "$OUT/logs/$base.ocr.log" | tail -1)"
  done
  head -1 "$(ls "$OUT"/frames/*/ocr.tsv | head -1)" > "$OUT/all_ocr.tsv"
  for f in "$OUT"/frames/*/ocr.tsv; do tail -n +2 "$f" >> "$OUT/all_ocr.tsv"; done
  wc -l "$OUT/all_ocr.tsv"
fi

# ---------- 3) 摘百分数 / 剔 UI ----------
if [ "${1:-all}" = "parse" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/pct_parse.py" --tsv "$OUT/all_ocr.tsv" \
      --out "$OUT/pages_clean.tsv" --pct-list "$OUT/pct清单.tsv" \
      > "$OUT/logs/pct.log" 2>&1
  tail -40 "$OUT/logs/pct.log"
fi

# ---------- 4) 拼接 ----------
if [ "${1:-all}" = "stitch" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/stitch.py" --tsv "$OUT/pages_clean.tsv" \
      --out "$OUT/corpus_new_raw.txt" --audit "$OUT/stitch_audit.tsv"
fi

# ---------- 5) 占位符清理 ----------
if [ "${1:-all}" = "clean" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/clean_corpus.py" --in "$OUT/corpus_new_raw.txt" \
      --out "$OUT/corpus_new_clean.txt" --report "$OUT/占位符修补清单.tsv"
fi

# ---------- 6) QA ----------
if [ "${1:-all}" = "qa" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/qa_corpus.py" --tsv "$OUT/pages_clean.tsv" \
      --corpus "$OUT/corpus_new_clean.txt" --audit "$OUT/stitch_audit.tsv" \
      > "$OUT/QA_new.txt" 2>&1
  tail -5 "$OUT/QA_new.txt"
fi

# ---------- 7) 与旧正文合流 ----------
if [ "${1:-all}" = "merge" ] || [ "${1:-all}" = "all" ]; then
  python3 "$TOOLS/merge_corpora.py" --old "$OLD_CORPUS" \
      --new "$OUT/corpus_new_clean.txt" --out "$OUT/corpus_merged.txt" \
      --report "$OUT/接缝审计.tsv"
fi
echo "== DONE $1"

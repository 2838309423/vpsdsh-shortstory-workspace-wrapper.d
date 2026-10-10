#!/usr/bin/env bash
# 抽样双模型交叉验证：主模型（如 qwen-vl-ocr）全量跑完后，抽一批页用**对照模型**
# （如 qwen3-vl-plus）再 OCR 一遍，再做字符级比对（cross_verify.py）。
# 两版都是 OCR、都不等于真值，但**完全一致时几乎可以断定该页无误**。
#
# 抽样口径（2026-10-10 深夜定，S59~S76 那轮）：
#   * COVER_MARK（如 171536 = 本次新录批次）的**每一段**都抽 PAGES 指定的页；
#   * 其余段每 EVERY 段抽一次，同样抽 PAGES。
#   这样既做到「新批次每段都有覆盖」，又保留与上一轮可比的旧批次抽样。
#
# 用法：
#   OUT=/tmp/ca31/out2 COVER_MARK=171536 EVERY=3 PAGES=10,35 \
#     CROSS_MODEL=qwen3-vl-plus bash cross_sample.sh
# 产物：$S/{pages/,ocr_raw.tsv,pages_clean.tsv,pct清单.tsv,ocr.log}
#   随后：python3 cross_verify.py $OUT/pages_clean.tsv $S/pages_clean.tsv > 跨模型交叉验证.txt
set -uo pipefail
OUT="${OUT:-/tmp/ca31/out2}"
S="${S:-/tmp/ca31/sample}"
TOOLS="${TOOLS:-/tmp/ca31}"
CROSS_MODEL="${CROSS_MODEL:-qwen3-vl-plus}"
COVER_MARK="${COVER_MARK:-}"
EVERY="${EVERY:-3}"
PAGES="${PAGES:-10,35}"
WORKERS="${WORKERS:-8}"
export BAILIAN_KEYFILE="${BAILIAN_KEYFILE:-/tmp/ca31/bailian.key}"

rm -rf "$S"; mkdir -p "$S/pages"
i=0; n_new=0; n_old=0
sed_expr=""
for p in ${PAGES//,/ }; do sed_expr="${sed_expr}${p}p;"; done
for d in "$OUT"/frames/*/; do
  i=$((i+1))
  base="$(basename "$d")"
  take=0
  if [ -n "$COVER_MARK" ] && [[ "$base" == *"$COVER_MARK"* ]]; then
    take=1
  elif [ $((i % EVERY)) -eq 1 ]; then
    take=1
  fi
  [ "$take" = 1 ] || continue
  for p in $(ls "$d"/pages/*.jpg 2>/dev/null | sed -n "$sed_expr"); do
    cp "$p" "$S/pages/" || continue
    if [[ "$base" == *"$COVER_MARK"* ]]; then n_new=$((n_new+1)); else n_old=$((n_old+1)); fi
  done
done
echo "抽样 $((n_new+n_old)) 页（新批 $n_new 页 / 旧批 $n_old 页；共 $i 段，COVER_MARK='$COVER_MARK' EVERY=$EVERY PAGES=$PAGES）"

python3 "$TOOLS/ocr_pages.py" --indir "$S/pages" --out "$S/ocr_raw.tsv" \
    --out-dir "$S/txt" --workers "$WORKERS" --model "$CROSS_MODEL" --resize 0 \
    --thinking 0 --prompt "$TOOLS/prompt_pct.txt" > "$S/ocr.log" 2>&1
echo "ocr rc=$? $(grep -o '__OCR_DONE__.*' "$S/ocr.log" | tail -1)"

python3 "$TOOLS/pct_parse.py" --tsv "$S/ocr_raw.tsv" --out "$S/pages_clean.tsv" \
    --pct-list "$S/pct清单.tsv" > "$S/pct.log" 2>&1
echo "pct rc=$? $(grep -o '__PCT__.*' "$S/pct.log" | tail -1)"
echo "== CROSS-SAMPLE DONE =="

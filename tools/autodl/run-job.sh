#!/usr/bin/env bash
# run-job.sh -- render one job on the AutoDL instance (the only command a future video needs).
#
# Usage:
#   bash run-job.sh --blend /root/autodl-tmp/jobs/<job>/scene.blend \
#                   --out   /root/autodl-tmp/jobs/<job>/frames \
#                   --res 1080x1920 --samples 24 --device CUDA \
#                   [--scene SceneA --start 1 --end 408] \
#                   [--fps 24 --encode /root/autodl-tmp/jobs/<job>/out.mp4] \
#                   [--shutdown] [--log /root/autodl-tmp/jobs/<job>/render.log]
#
# Notes:
#   * frames ALWAYS land on the data disk (/root/autodl-tmp, 50 GB free, NOT part of the
#     saved image) -- never on the 30 GB system disk.
#   * --device CUDA fails loudly if the GPU is not visible (see render_job.py).
#   * --shutdown runs /usr/bin/shutdown at the end => billing stops by itself.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
BLEND=""; OUT=""; RES="1080x1920"; SAMPLES=24; DEVICE="CUDA"; SCENE=""
START=""; END=""; FPS=24; ENCODE=""; DO_SHUTDOWN=0; LOG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --blend) BLEND="${2:-}"; shift ;;
    --out) OUT="${2:-}"; shift ;;
    --res) RES="${2:-}"; shift ;;
    --samples) SAMPLES="${2:-}"; shift ;;
    --device) DEVICE="${2:-}"; shift ;;
    --scene) SCENE="${2:-}"; shift ;;
    --start) START="${2:-}"; shift ;;
    --end) END="${2:-}"; shift ;;
    --fps) FPS="${2:-}"; shift ;;
    --encode) ENCODE="${2:-}"; shift ;;
    --log) LOG="${2:-}"; shift ;;
    --shutdown) DO_SHUTDOWN=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -n "$BLEND" ] || { echo "FATAL: --blend is required" >&2; exit 2; }
[ -f "$BLEND" ] || { echo "FATAL: blend not found: $BLEND" >&2; exit 2; }
[ -n "$OUT" ] || { echo "FATAL: --out is required" >&2; exit 2; }
mkdir -p "$OUT"
[ -n "$LOG" ] || LOG="$(dirname "$OUT")/render.log"

EXTRA=()
[ -n "$SCENE" ] && EXTRA+=(--scene "$SCENE")
[ -n "$START" ] && [ -n "$END" ] && EXTRA+=(--start "$START" --end "$END")

{
  echo "=== run-job $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "blend=$BLEND res=$RES samples=$SAMPLES device=$DEVICE scene=${SCENE:--} frames=${START:--}..${END:--} out=$OUT"
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || echo "nvidia-smi: not available"
  echo "disk: $(df -h "$OUT" | tail -n 1)"
} | tee "$LOG"

blender --factory-startup -b "$BLEND" --python-exit-code 1 \
        --python "$HERE/render_job.py" -- \
        --out "$OUT" --device "$DEVICE" --res "$RES" --samples "$SAMPLES" \
        --report "$(dirname "$OUT")/render_report.json" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
LINE="$(grep -o '__RENDER__ .*' "$LOG" | tail -n 1)"
echo "BLENDER_EXIT=$RC  ${LINE:-<no __RENDER__ line>}" | tee -a "$LOG"

if [ -n "$ENCODE" ] && [ -d "$OUT" ]; then
  echo "--- ffmpeg encode -> $ENCODE ---" | tee -a "$LOG"
  ffmpeg -y -loglevel warning -framerate "$FPS" -start_number "${START:-1}" \
         -i "$OUT/frame_%04d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 "$ENCODE" 2>&1 | tee -a "$LOG"
  echo "encode_rc=${PIPESTATUS[0]} size=$(stat -c%s "$ENCODE" 2>/dev/null || echo 0)" | tee -a "$LOG"
fi

if [ "$DO_SHUTDOWN" = 1 ]; then
  echo "--- /usr/bin/shutdown (billing stops) ---" | tee -a "$LOG"
  sync
  /usr/bin/shutdown
fi
exit $RC

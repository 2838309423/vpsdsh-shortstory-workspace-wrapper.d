#!/usr/bin/env bash
# Tailscale 门面（TCP 转发器）的前台运行体：tmux 会话 dsh-proxy 里跑的就是它。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
mkdir -p "$ROOT/state"
echo "[proxy-run] $(date -Is) $DSH_WEB_PUBLIC:$DSH_WEB_PORT -> $DSH_WEB_BIND:$DSH_WEB_PORT"
exec python3 "$HERE/ts-proxy.py" \
  --listen-host "$DSH_WEB_PUBLIC" --listen-port "$DSH_WEB_PORT" \
  --target-host "$DSH_WEB_BIND" --target-port "$DSH_WEB_PORT"

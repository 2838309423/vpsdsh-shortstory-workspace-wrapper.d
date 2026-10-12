#!/usr/bin/env bash
# Tailscale 门面（入口鉴权门）的前台运行体：tmux 会话 dsh-proxy 里跑的就是它。
#
# 跑的是 bin/web-gate.py（bin/ts-proxy.py 是它的"纯直通"前身，保留作回滚/对照）。
# 模式写在 state/gate.conf（mode = off | tailnet | password），门每条连接现读 ⇒ 改完不用重启。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
mkdir -p "$ROOT/state"
MODE="$(grep -E '^[[:space:]]*mode[[:space:]]*=' "$ROOT/state/gate.conf" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d ' ')"
echo "[proxy-run] $(date -Is) $DSH_WEB_PUBLIC:$DSH_WEB_PORT -> $DSH_WEB_BIND:$DSH_WEB_PORT mode=${MODE:-tailnet(缺省)}"
exec python3 "$HERE/web-gate.py" \
  --listen-host "$DSH_WEB_PUBLIC" --listen-port "$DSH_WEB_PORT" \
  --target-host "$DSH_WEB_BIND" --target-port "$DSH_WEB_PORT" \
  --state-dir "$ROOT/state"

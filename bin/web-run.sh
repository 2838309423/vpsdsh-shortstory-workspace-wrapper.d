#!/usr/bin/env bash
# DSH 浏览器文本服务的前台运行体（tmux 会话 dsh-web 里跑的就是它）。
# 工作区根 = 本仓根目录（profile 的 sandbox-policy.workspaceRoot = process.cwd()）。
# 只绑回环：公网侧由 bin/ts-proxy.py 在 Tailscale 网卡上转发进来。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
mkdir -p "$ROOT/state"
cd "$ROOT"

args=(--host "$DSH_WEB_BIND" --port "$DSH_WEB_PORT" --no-open)
for h in $DSH_WEB_TRUSTED; do args+=(--trusted-host "$h"); done

echo "[web-run] $(date -Is) bind=$DSH_WEB_BIND:$DSH_WEB_PORT public=$DSH_WEB_PUBLIC trusted='$DSH_WEB_TRUSTED' profile=${DSH_PROFILE:-vps} cwd=$ROOT"
exec dsh --profile "${DSH_PROFILE:-vps}" "${args[@]}"

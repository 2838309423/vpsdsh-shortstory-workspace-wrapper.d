#!/usr/bin/env bash
# DSH 浏览器文本服务（小说写作入口）：start|stop|restart|ensure|status|logs|url
#
#   bash bin/web.sh start     起服务（两个 tmux 会话：dsh-web + dsh-proxy；socket dsh-vps 与既有两线隔离）
#   bash bin/web.sh status    进程 + 端口 + 入口 URL + 日志尾
#   bash bin/web.sh ensure    幂等：缺哪个起哪个（cron 看门狗用它）
#   bash bin/web.sh logs [N]  日志尾 N 行（缺省 60）
#
# 为什么是两个会话：dsh web 只肯绑 127.0.0.1/0.0.0.0 且自带无认证 ⇒ 由 bin/ts-proxy.py 在
# Tailscale 网卡上听同一端口转发进来（公网 IP 上零监听）。见 bin/env.sh 顶部三条口径。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
SOCK="${DSH_TMUX_SOCKET:-dsh-vps}"
S_WEB="${DSH_TMUX_SESSION:-dsh-web}"
S_PROXY="${DSH_TMUX_PROXY:-dsh-proxy}"
LOG="$ROOT/state/web.log"
PLOG="$ROOT/state/proxy.log"
URL_FILE="$ROOT/state/url.txt"

has() { tmux -L "$SOCK" has-session -t "$1" 2>/dev/null; }

# 入口 URL 带一次性令牌：`dsh web` 启动时往日志打 `dsh web: http://127.0.0.1:PORT/?token=…`，
# 每次启动都会换新令牌（实测 2026-10-08：重启后 token 不同）⇒ 从日志取，落到 state/url.txt（600）。
refresh_url() {
  local tok
  tok="$(grep -oP 'token=\K\S+' "$LOG" 2>/dev/null | tail -1)"
  if [ -n "$tok" ]; then
    umask 077
    printf '%s\n' "http://$DSH_WEB_PUBLIC:$DSH_WEB_PORT/?token=$tok" > "$URL_FILE"
    chmod 600 "$URL_FILE"
    echo "[web] 入口（含令牌，别外传）：$(cat "$URL_FILE")"
  else
    echo "[web] 日志里还没有令牌（$LOG）"
  fi
}

start_web() {
  if has "$S_WEB"; then echo "[web] dsh-web 已在跑";
  else
    : > "$LOG"
    tmux -L "$SOCK" new-session -d -s "$S_WEB" "bash '$HERE/web-run.sh' >>'$LOG' 2>&1"
    echo "[web] 已拉起 tmux -L $SOCK -t $S_WEB"
  fi
}

start_proxy() {
  if has "$S_PROXY"; then echo "[web] dsh-proxy 已在跑";
  else
    : > "$PLOG"
    tmux -L "$SOCK" new-session -d -s "$S_PROXY" "bash '$HERE/proxy-run.sh' >>'$PLOG' 2>&1"
    echo "[web] 已拉起 tmux -L $SOCK -t $S_PROXY"
  fi
}

do_start() {
  mkdir -p "$ROOT/state"
  start_web
  start_proxy
  sleep 4
  refresh_url
  do_status
}

do_stop() {
  for s in "$S_WEB" "$S_PROXY"; do
    if has "$s"; then tmux -L "$SOCK" kill-session -t "$s" && echo "[web] 已停 $s"; else echo "[web] $s 本来就没跑"; fi
  done
}

do_status() {
  echo "[web] profile=${DSH_PROFILE:-vps} cwd=$ROOT"
  echo "[web] dsh 监听 $DSH_WEB_BIND:$DSH_WEB_PORT ；门面监听 $DSH_WEB_PUBLIC:$DSH_WEB_PORT"
  echo -n "[web] tmux $SOCK:$S_WEB -> ";   has "$S_WEB"   && echo running || echo stopped
  echo -n "[web] tmux $SOCK:$S_PROXY -> "; has "$S_PROXY" && echo running || echo stopped
  for hp in "$DSH_WEB_BIND:$DSH_WEB_PORT" "$DSH_WEB_PUBLIC:$DSH_WEB_PORT"; do
    if ss -ltn 2>/dev/null | grep -q "${hp%:*}%\{0,1\}:${hp##*:} "; then
      echo "[web] 在听 $hp"
    else
      echo "[web] 未在听 $hp"
    fi
  done
  echo "[web] 入口（Tailscale 内网）：$(do_url)"
  if [ -s "$LOG" ]; then echo '[web] web.log 尾：'; tail -n 5 "$LOG" | sed 's/^/       /'; fi
  if [ -s "$PLOG" ]; then echo '[web] proxy.log 尾：'; tail -n 3 "$PLOG" | sed 's/^/       /'; fi
}

do_url() {
  if [ -s "$URL_FILE" ]; then cat "$URL_FILE"; else echo "http://$DSH_WEB_PUBLIC:$DSH_WEB_PORT/（尚未取到令牌，先 start）"; fi
}

do_logs() {
  local n="${1:-60}"
  [ -f "$LOG" ] && { echo "--- $LOG"; tail -n "$n" "$LOG"; }
  [ -f "$PLOG" ] && { echo "--- $PLOG"; tail -n "$((n / 3 + 3))" "$PLOG"; }
}

case "${1:-status}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; sleep 1; do_start ;;
  ensure)
    # 看门狗顺手把 state/url.txt 校准到**当前**令牌（2026-10-12 补的坑）：
    # `@reboot` 走的就是 ensure ⇒ 只拉会话不刷新的话，url.txt 里会留着上一代的死令牌，
    # 之后照着它发给甲方的链接一律 401。refresh_url 只读日志尾，幂等、便宜。
    has "$S_WEB" || { start_web >/dev/null; sleep 3; }
    has "$S_PROXY" || start_proxy >/dev/null
    refresh_url >/dev/null 2>&1 || true
    if has "$S_WEB" && has "$S_PROXY"; then echo "[web] ok"; else echo "[web] FAIL"; exit 1; fi
    ;;
  status)  do_status ;;
  url)     do_url ;;
  token)   refresh_url ;;
  logs)    do_logs "${2:-60}" ;;
  *) echo "用法: $0 {start|stop|restart|ensure|status|url|token|logs [N]}" >&2; exit 2 ;;
esac

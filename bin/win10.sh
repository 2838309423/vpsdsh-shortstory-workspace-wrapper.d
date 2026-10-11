#!/usr/bin/env bash
# win10 KVM 客机（甲方桌面，跑在 usavps 宿主上）—— 看状态 / 启停 / 截屏
#
# ⚠ 域定义在 qemu:///system（`virsh list` 默认走 qemu:///session ⇒ 空列表，别被误导）。
# ⚠ `virsh screenshot` 走 QEMU screendump，实测可能吐**旧帧**（QXL 表面不刷新）；
#    判定客机是否活着要看 guest agent + qwinsta，别只看截图。
set -uo pipefail

URI=${WIN10_URI:-qemu:///system}
DOM=${WIN10_DOM:-win10}
FF=${FFMPEG:-/home/longxia/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/ffmpeg}

v() { virsh -c "$URI" "$@"; }
agent() { timeout 8 virsh -c "$URI" qemu-agent-command "$DOM" "$1" 2>&1; }

guest_ip() {
  v net-dhcp-leases default 2>/dev/null |
    awk -v m="${WIN10_MAC:-52:54:00:5e:86:43}" 'tolower($0) ~ tolower(m) {print $5}' |
    cut -d/ -f1 | tail -1
}

case "${1:-status}" in
status)
  v list --all
  echo "-- 资源 --"
  v dominfo "$DOM" 2>&1 | sed -n '4,12p'
  echo "-- guest agent --"
  agent '{"execute":"guest-ping"}'
  echo "-- 客机 IP --"
  echo "192.168.122.x ⇒ $(guest_ip)"
  ;;
start)
  v start "$DOM" 2>&1 || true
  sleep 2
  v list --all
  ;;
stop)
  echo "⚠ 这是甲方桌面，会丢失客机内未保存的东西；确认后再跑本子命令。"
  read -r -p "回 OK 才关: " a
  [ "${a:-}" = OK ] && v shutdown "$DOM" 2>&1 || echo "已取消"
  ;;
reset)
  echo "⚠ 硬重启（不优雅关机）；确认后再跑本子命令。"
  read -r -p "回 OK 才重启: " a
  [ "${a:-}" = OK ] && v reset "$DOM" 2>&1 || echo "已取消"
  ;;
inspect)
  # 客机真实会话状态（截图不可信时的判据）
  pid=$(agent '{"execute":"guest-exec","arguments":{"path":"cmd.exe","arg":["/c","qwinsta"],"capture-output":true}}' |
    python3 -c 'import sys,json;print(json.load(sys.stdin)["return"]["pid"])' 2>/dev/null)
  [ -z "${pid:-}" ] && { echo "guest agent 无响应"; exit 1; }
  sleep 2
  agent "{\"execute\":\"guest-exec-status\",\"arguments\":{\"pid\":$pid}}" |
    python3 -c 'import sys,json,base64;d=json.load(sys.stdin)["return"];print(base64.b64decode(d.get("out-data") or b"").decode("gbk","replace"))'
  ;;
shot)
  out=${2:-/tmp/win10-shot-$(date +%H%M%S).png}
  tmp=$(mktemp --suffix=.ppm)
  if v screenshot "$DOM" "$tmp" >/dev/null 2>&1 && "$FF" -y -loglevel error -i "$tmp" "$out"; then
    rm -f "$tmp"; echo "$out"
  else
    rm -f "$tmp"; echo "截屏失败" >&2; exit 1
  fi
  ;;
console)
  echo "SPICE 只听宿主回环 127.0.0.1:5900（无口令），外部要打隧道："
  echo "  ssh -N -L 5900:127.0.0.1:5900 longxia@156.238.255.110"
  echo "  remote-viewer spice://127.0.0.1:5900"
  ;;
rdp)
  ip=$(guest_ip)
  echo "客机 RDP ${ip:-192.168.122.121}:3389，同样要隧道："
  echo "  ssh -N -L 13389:${ip:-192.168.122.121}:3389 longxia@156.238.255.110"
  echo "  然后 mstsc localhost:13389"
  ;;
*)
  echo "用法: $0 {status|start|stop|reset|inspect|shot [out.png]|console|rdp}"
  exit 2
  ;;
esac

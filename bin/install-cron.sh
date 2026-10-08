#!/usr/bin/env bash
# 给本实例上「开机自启 + 每 2 分钟看门狗」的用户 crontab 条目（幂等、可卸）。
#   bash bin/install-cron.sh install|verify|uninstall
#
# 为什么用 cron 而不是 systemd --user：本机 longxia **无 sudo 免密**，`loginctl enable-linger`
# 需要 root/polkit ⇒ 用户级 systemd 会在退出登录时被带走；cron 的 @reboot 与常驻条目不受影响。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
MARK="# vpsdsh-shortstory-web"
L1="@reboot $HERE/web.sh ensure >/dev/null 2>&1 $MARK"
L2="*/2 * * * * $HERE/web.sh ensure >/dev/null 2>&1 $MARK"
CHMOD="chmod +x $HERE/*.sh $HERE/*.py"

cur="$(crontab -l 2>/dev/null || true)"
clean="$(printf '%s\n' "$cur" | grep -v -F "$MARK" | grep -v '^$' || true)"

case "${1:-verify}" in
  install)
    printf '%s\n%s\n%s\n' "$clean" "$L1" "$L2" | grep -v '^$' | crontab -
    bash "$HERE/web.sh" ensure >/dev/null 2>&1 || true
    echo "[cron] 已装：@reboot + 每 2 分钟 ensure"
    crontab -l | grep -F "$MARK"
    ;;
  uninstall)
    printf '%s\n' "$clean" | grep -v '^$' | crontab - 2>/dev/null || crontab -r 2>/dev/null || true
    echo "[cron] 已卸"
    crontab -l 2>/dev/null | grep -F "$MARK" || echo "[cron] 无残留"
    ;;
  verify)
    if crontab -l 2>/dev/null | grep -qF "$MARK"; then
      echo "[cron] 在装："
      crontab -l | grep -F "$MARK"
    else
      echo "[cron] 未装（跑 install）"
    fi
    ;;
  *) echo "用法: $0 install|verify|uninstall" >&2; exit 2 ;;
esac

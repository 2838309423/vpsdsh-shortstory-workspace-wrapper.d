#!/usr/bin/env bash
# 统一环境：Node / DSH / DSH_HOME / 权限档 / 监听地址。被本目录其它脚本 `source`。
#
# ⚠ 三条实测口径（2026-10-08，DSH 0.2.0-rc.2）：
#   1. 本机 node 是 $HOME 自装的 v24.21.0（`~/toolchain/node/bin`），**系统 node 只有 v12**，
#      所以任何调用 dsh 的地方都必须先把 PATH 前置。
#   2. `DSH_PERMISSION_MODE` 属于「启动环境变量」，**写进 `$DSH_HOME/.env` 会被启动器拒绝**
#      （`... sets "DSH_PERMISSION_MODE", which only the launching environment may set`）
#      ⇒ 只能在这里 export。
#   3. `dsh web --host` **只接受 `127.0.0.1` / `0.0.0.0`**（其它值直接 ValidationError），
#      而该服务器「自带无 TLS、无认证、无来源策略」⇒ 绑 0.0.0.0 就等于把文本服务挂到公网（红线）。
#      做法：dsh 绑回环，`bin/ts-proxy.py` 只在 **Tailscale 网卡**上听同一端口转发进来。

export DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
export PATH="$HOME/toolchain/node/bin:$PATH"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

# 权限档：与甲方桌面端同档（无 sudo、整机 $HOME 都是自己的，不需要更窄的沙箱）
export DSH_PERMISSION_MODE="${DSH_PERMISSION_MODE:-danger-full-access}"

export DSH_WEB_PORT="${DSH_WEB_PORT:-19387}"
export DSH_WEB_BIND="${DSH_WEB_BIND:-127.0.0.1}"

# 公网侧（Tailscale）监听地址：缺省取本机 Tailscale IPv4
if [ -z "${DSH_WEB_PUBLIC:-}" ]; then
  DSH_WEB_PUBLIC="$(tailscale ip -4 2>/dev/null | head -n1)"
  DSH_WEB_PUBLIC="${DSH_WEB_PUBLIC:-127.0.0.1}"
fi
export DSH_WEB_PUBLIC

# `/api` 浏览器信任栅栏额外接受的 authority（经代理进来时 Host 头带的是公网侧 authority）
# 本机 Tailscale MagicDNS 名（split 档的"令牌档"书签用它；也进 /api 信任栅栏）
if [ -z "${DSH_WEB_DNS:-}" ] && [ "$DSH_WEB_PUBLIC" != "127.0.0.1" ]; then
  DSH_WEB_DNS="$(tailscale status --json 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("Self",{}).get("DNSName","").rstrip("."))' 2>/dev/null)"
fi
export DSH_WEB_DNS

DSH_WEB_TRUSTED="${DSH_WEB_PUBLIC}:${DSH_WEB_PORT}"
if [ -n "${DSH_WEB_DNS:-}" ]; then
  DSH_WEB_TRUSTED="$DSH_WEB_TRUSTED $DSH_WEB_DNS:$DSH_WEB_PORT"
fi
export DSH_WEB_TRUSTED

# 本工作区根（＝ DSH 启动 cwd ＝ profile 的 workspaceRoot）
DSH_VPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DSH_VPS_ROOT

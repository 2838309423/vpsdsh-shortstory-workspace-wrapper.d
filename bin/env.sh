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

# ── 会话轮转插件 @local/dsh-session-rotation.d 的 Linux 路径面（2026-10-13 装）──────────────
# 插件出厂缺省全是 Windows 路径（`D:\dsk-workspace.d\usavps-bridge.d\...`；驱动根更是
# `C:\Users\Administrator\.dsh\headless-driver`）⇒ 在服务器上必须显式改写，否则它会照字面量
# 去 mkdir 出 `D:\…` 这种怪目录（插件不做平台判断，见其 index.js 的 DEFAULT_INBOX）。
# 运行数据一律落本仓 `state/rotation/`（`state/` 已进 .gitignore，不进仓）。
# ⚠ 环境变量只在 DSH **启动时**读 ⇒ 改这里要 `bash bin/web.sh restart` 才生效。
# ⚠ 权限档：出厂 `observe` = **只报不改**（只读 L2/transcript + 往 state 里写读数，不建会话、
#   不归档、不移文件）。要真跑链条得 mode=rotate + 首跑测试闸，另见
#   `docs/落地记录-轮转插件-usavps-261013.md`。
# ⚠ **工作区白名单必须给**：插件口径是「空表 ⇒ fail-closed」，`workspaces` 空时每个会话都被判
#   `not-in-whitelist` ⇒ **零动作**（加载了但什么都没测）。本机 DSH 的工作区根 = `$DSH_VPS_ROOT`
#   （＝启动 cwd），所以名单就写它；多条用 `;` 或 `,` 分隔（插件不做平台判断，两边都会经过
#   同一个 normalize：`/`→`\` + 小写，所以 Linux 路径也能精确命中）。
export DSH_SESSION_ROTATION_MODE="${DSH_SESSION_ROTATION_MODE:-observe}"
export DSH_SESSION_ROTATION_WORKSPACES="${DSH_SESSION_ROTATION_WORKSPACES:-$DSH_VPS_ROOT}"
export DSH_SESSION_ROTATION_INBOX="${DSH_SESSION_ROTATION_INBOX:-$DSH_VPS_ROOT/state/rotation/inbox}"
export DSH_SESSION_ROTATION_AUDIT="${DSH_SESSION_ROTATION_AUDIT:-$DSH_VPS_ROOT/state/rotation/audit/dsh-rotation.jsonl}"
export DSH_SESSION_ROTATION_LOG="${DSH_SESSION_ROTATION_LOG:-$DSH_VPS_ROOT/state/rotation/plugin.log}"
# `DSH_SESSION_ROTATION_STATE` = **active 指针那个文件**的路径（不是目录！插件对它的
# `dirname()` 才是 `rotation-config.json` / 首跑闸 `test-session.txt` 的落点）。必须显式给：
#   ① 缺省是 `dirname(INBOX)/state/rotation-active.json` ⇒ 实落成 `state/rotation/state/…`（套娃）；
#   ② 写成目录 ⇒ `dirname()` 把配置文件甩到上一级 `state/rotation-config.json`（2026-10-13 实测两次）。
export DSH_SESSION_ROTATION_STATE="${DSH_SESSION_ROTATION_STATE:-$DSH_VPS_ROOT/state/rotation/rotation-active.json}"
# 于是三个运行真值件的落点 = `state/rotation/{rotation-active.json,rotation-config.json,test-session.txt}`。
# 跨会话调度（host 半 → headless 驱动）：驱动是 **Windows 侧**的 Chrome/CDP 件（schtasks +
# `hb-run.ps1`），服务器上没有 ⇒ 保持插件缺省 `driver.enabled=false`（此处不导出任何 DRIVER_*，
# 也就不会去碰 `C:\…\headless-driver`）。要开得先有 Linux 版驱动。

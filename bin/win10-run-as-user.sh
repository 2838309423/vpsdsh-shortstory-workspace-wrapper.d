#!/usr/bin/env bash
# win10-run-as-user.sh —— 把一条命令塞进**客机里已登录用户的交互桌面会话**（RDP/console，session ≥1）里跑
#
# 为什么需要它（2026-10-11 实测，踩了一整天才绕出来）：
#   `bin/win10-exec.sh` 走 qemu-guest-agent ⇒ 进程是 **SYSTEM / session 0**，那里**没有真桌面**：
#   GUI 程序（Blender GUI、浏览器无头/有头）在 session 0 里要么起不来、要么 GL 上下文建不起来
#   （`ChoosePixelFormat` 拿不到像素格式 ⇒ Mesa 刷 "without a rendering context"）。
#   ⇒ 想验"甲方在自己桌面双击能不能开"，**只能把命令塞进他自己那个会话里跑**。本脚本就是那把钥匙。
#
# 原理：schtasks 建一个 `LogonType=InteractiveToken` 的计划任务（**不需要密码**，这是关键 ——
#   `/ru <用户>` 不带 `/rp` 走 XML 才成立，命令行 `/ru … /it` 会要口令），跑完删掉。
#   ⚠ 任务 XML 必须是 **UTF-16LE + BOM**，否则 schtasks 报 `(1,40)::错误: 无法切换编码`。
#
# 用法：
#   bin/win10-run-as-user.sh --list                  # 只列出客机里有哪些交互会话/用户
#   bin/win10-run-as-user.sh <宿主上的 .bat> [--wait 40] [--keep] [--user DOMAIN\\name]
#       <宿主上的 .bat>：**在共享盘里**（$SHARE 下）就**原地**以用户身份跑（`%~dp0` 不变）；
#       在别处（如 /tmp）就先拷到 `Z:\_dsh-asuser\run.bat` 再跑。
#       --wait N  跑完等 N 秒再回读（默认 40；setx/装东西这类要留够）
#       --keep    别删计划任务（要现场看的话）
#   产物：`Z:\_dsh-asuser\` 下的 bat/xml/log；本脚本把任务查询结果打出来。
#
# 惯例：.bat 里自己把日志写到 `Z:\_dsh-asuser\*.log`（客机侧），宿主直接读共享盘。
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
WORK="$SHARE/_dsh-asuser"
GUEST_WORK='Z:\_dsh-asuser'
TASK=${WIN10_ASUSER_TASK:-DSHAsUser}
WAIT=40; KEEP=0; LIST=0; USER_OVERRIDE=""; SCRIPT=""

while [ $# -gt 0 ]; do case "$1" in
  --wait) WAIT=$2; shift 2;;
  --user) USER_OVERRIDE=$2; shift 2;;
  --keep) KEEP=1; shift;;
  --list) LIST=1; shift;;
  -h|--help) sed -n '2,30p' "$0"; exit 0;;
  *) SCRIPT=$1; shift;;
esac; done

ex() { bash "$HERE/win10-exec.sh" --timeout "$1" "${@:2}"; }
mkdir -p "$WORK"; chmod 755 "$WORK" 2>/dev/null || true

# ---------- 列出交互会话（explorer.exe 的 owner 就是"谁在某会话里真正登录着"） ----------
cat > "$WORK/list-sessions.ps1" <<'PS'
Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" | ForEach-Object {
  $o = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
  if ($o.User) { '{0}|{1}|{2}' -f $_.SessionId, $o.Domain, $o.User }
}
PS
chmod a+r "$WORK/list-sessions.ps1"
list_sessions() {
  ex 90 cmd.exe /c "powershell -NoProfile -ExecutionPolicy Bypass -File $GUEST_WORK\\list-sessions.ps1" 2>/dev/null \
    | tr -d '\r' | grep -aE '^[0-9]+\|'
}
if [ $LIST -eq 1 ]; then
  S=$(list_sessions)
  [ -n "$S" ] && echo "$S" || echo "[as-user] 没找到交互会话（甲方没登录 / explorer 没跑）" >&2
  exit 0
fi

[ -n "$SCRIPT" ] || { echo "用法: $0 <宿主上的 .bat> [--wait N] [--keep] [--user D\\name] | --list" >&2; exit 2; }
[ -f "$SCRIPT" ] || { echo "[as-user] 找不到 $SCRIPT" >&2; exit 1; }

# ---------- 定人（优先 --user，其次自动探测） ----------
if [ -n "$USER_OVERRIDE" ]; then
  WHO=$USER_OVERRIDE
else
  WHO=$(list_sessions | head -1 | cut -d'|' -f2,3 | sed 's/|/\\/')
fi
[ -n "$WHO" ] || { echo "[as-user] ❌ 拿不到交互会话用户；先跑 $0 --list 看看，或用 --user DOMAIN\\name" >&2; exit 1; }
echo "[as-user] 目标用户：$WHO"

# ---------- 放 bat + 生成任务 XML（UTF-16LE + BOM，必须） ----------
# ⚠ 脚本**本来就在共享盘里**时要在**原地**跑，不要拷进 _dsh-asuser/：
#   .bat 里 `%~dp0` 是"脚本自己所在的目录"，一拷就变了（实测：`open-room-gui.bat` 里
#   `%~dp0..\out\hello\room-hello.blend` 变成 Z:\_dsh-asuser\..\out\… ⇒ 找不到文件 + 卡在 pause）。
SHARE_ABS=$(readlink -f "$SHARE"); SCRIPT_ABS=$(readlink -f "$SCRIPT")
case "$SCRIPT_ABS" in
  "$SHARE_ABS"/*) REL=${SCRIPT_ABS#"$SHARE_ABS"/}; CMD="Z:\\${REL//\//\\}"; INPLACE=1;;
  *) cp -f "$SCRIPT" "$WORK/run.bat"; chmod a+r "$WORK/run.bat"; CMD='Z:\_dsh-asuser\run.bat'; INPLACE=0;;
esac
echo "[as-user] 执行：$CMD$([ $INPLACE -eq 1 ] && echo '（共享盘内就地跑，保住 %~dp0）' || echo '（已拷进 _dsh-asuser/）')"
WHO_ESC=${WHO//\\/\\\\}          # ⚠ sed 替换串里 `\` 是转义前缀：不双写会把 DOMAIN\user 变成 DOMAINuser
CMD_ESC=${CMD//\\/\\\\}
sed -e "s/@USER@/$WHO_ESC/g" -e "s|@CMD@|$CMD_ESC|g" > "$WORK/task_utf8.xml" <<'XML'
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>dsh run-as-user (temp)</Description></RegistrationInfo>
  <Triggers />
  <Principals>
    <Principal id="Author">
      <UserId>@USER@</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>@CMD@</Command></Exec>
  </Actions>
</Task>
XML
{ printf '\xff\xfe'; iconv -f UTF-8 -t UTF-16LE "$WORK/task_utf8.xml"; } > "$WORK/task.xml"
chmod a+r "$WORK/task.xml"

# ---------- 建任务 → 跑 → 等 → 回读 → 删 ----------
R=$(ex 90 cmd.exe /c "schtasks /create /tn $TASK /xml $GUEST_WORK\\task.xml /f && schtasks /run /tn $TASK" 2>&1 | tr -d '\r')
echo "$R" | grep -qE '成功|SUCCESS' || { echo "[as-user] ❌ 建/跑任务失败：$R" >&2; exit 1; }
echo "[as-user] 已在用户会话里启动，等 ${WAIT}s …"
sleep "$WAIT"
ex 90 cmd.exe /c "schtasks /query /tn $TASK /v /fo list" 2>/dev/null | tr -d '\r' | grep -aE '上次运行时间|上次结果|状态|作为用户运行|Last Run Time|Last Result|Status|Run As User'
if [ $KEEP -eq 0 ]; then
  ex 60 cmd.exe /c "schtasks /delete /tn $TASK /f" >/dev/null 2>&1
  echo "[as-user] 任务 $TASK 已删除"
else
  echo "[as-user] --keep ⇒ 任务 $TASK 留着（用完记得删：schtasks /delete /tn $TASK /f）"
fi
echo "[as-user] 产物目录（客机 $GUEST_WORK ⇄ 宿主 $WORK）："
ls -la "$WORK" | sed -n '2,12p'

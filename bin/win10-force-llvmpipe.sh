#!/usr/bin/env bash
# win10-force-llvmpipe.sh —— 让客机里的 **Mesa 走 llvmpipe（软件 OpenGL）**，而不是它默认挑的 d3d12
#
# 为什么必须做（2026-10-11 实测，甲方报"双击 blender.exe 灰窗口一闪就没了"的**真根因**）：
#   把 Mesa 的 opengl32.dll/libgallium_wgl.dll 放到 C:\blender\ **不够**。
#   Mesa 26.x 的 Windows WGL **默认驱动是 d3d12**；客机是 QXL 虚拟显卡，D3D12 只绑得到
#   `Microsoft Basic Render Driver`（假 3D 适配器）⇒ 表面上看 GL 版本 4.6、上下文也建了，
#   但一用就 `E_INVALIDARG`：Blender 立刻退出（exit code **-2147024809 = 0x80070057**）。
#   双击时的观感就是"灰色/黑色窗口（blender.exe 是 console 子系统程序，会开一个控制台）闪一下没了"。
#   ⇒ 必须把 **GALLIUM_DRIVER=llvmpipe**（+ LIBGL_ALWAYS_SOFTWARE=1）设进**机器级 + 用户级**环境变量。
#     设完实测：`vendor='Mesa' renderer='llvmpipe (LLVM 22.1.8, 256 bits)' version='4.6 (Core Profile) Mesa 26.2.4'`
#     ⇒ Blender GUI 正常开、EEVEE 也能渲（`MESA_GLTEST=OK engine=BLENDER_EEVEE_NEXT`）。
#
# ⚠ 两个环境变量**都要**设：
#   * 机器级（HKLM）—— 新登录/服务进程吃到；
#   * 用户级（HKCU\Environment）—— **已经在跑的 explorer.exe 只会靠 WM_SETTINGCHANGE 就地刷新**，
#     `setx` 正好会广播它 ⇒ 用户**不用注销重登**，双击立刻生效（实测：设完用 shell 启动 blender.exe 一次成功）。
#   用户级只能在他自己的会话里写（SYSTEM 的 HKCU 是 SYSTEM 的），所以借 `bin/win10-run-as-user.sh`。
#
# 用法：
#   bin/win10-force-llvmpipe.sh            # 设上（机器级 + 用户级），幂等
#   bin/win10-force-llvmpipe.sh --check    # 只体检：机器级 + 用户级环境变量各是什么
#   bin/win10-force-llvmpipe.sh --unset    # 撤掉（GUI 会回到打不开；无头 Cycles 不受影响）
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
ASUSER=${WIN10_ASUSER:-$HERE/win10-run-as-user.sh}
WORK="$SHARE/_dsh-asuser"
GVAR=${GALLIUM_DRIVER_NAME:-GALLIUM_DRIVER}
GVAL=${GALLIUM_DRIVER_VALUE:-llvmpipe}
SVAL=${LIBGL_ALWAYS_SOFTWARE_VALUE:-1}
MODE=install

while [ $# -gt 0 ]; do case "$1" in
  --check) MODE=check; shift;;
  --unset) MODE=unset; shift;;
  -h|--help) sed -n '2,26p' "$0"; exit 0;;
  *) echo "未知参数 $1" >&2; exit 2;;
esac; done

ex() { bash "$HERE/win10-exec.sh" --timeout "$1" "${@:2}"; }
mkdir -p "$WORK"; chmod 755 "$WORK" 2>/dev/null || true
HKLM_KEY='HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'

# ---------- 1. 机器级（SYSTEM 身份；⚠ 一律走 .bat，别把带引号的命令直接塞给 `cmd.exe /c`——
#              引号会被吃掉 ⇒ reg 报"无效语法"，实测踩过） ----------
case "$MODE" in
  install) MACT="setx /M $GVAR $GVAL
setx /M LIBGL_ALWAYS_SOFTWARE $SVAL" ;;
  unset)   MACT="reg delete \"HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment\" /v $GVAR /f
reg delete \"HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment\" /v LIBGL_ALWAYS_SOFTWARE /f" ;;
  check)   MACT="rem check only" ;;
esac
MBAT="$WORK/llvmpipe-machine-$MODE.bat"
cat > "$MBAT" <<EOF
@echo off
set L=Z:\\_dsh-asuser\\llvmpipe-machine-$MODE.log
echo === llvmpipe $MODE (machine scope) %DATE% %TIME% === > %L%
whoami >> %L% 2>&1
$MACT >> %L% 2>&1
echo --- HKLM Environment --- >> %L%
reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment" /v $GVAR >> %L% 2>&1
reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment" /v LIBGL_ALWAYS_SOFTWARE >> %L% 2>&1
echo DONE >> %L%
EOF
chmod a+r "$MBAT"
ex 180 cmd.exe /c "Z:\\_dsh-asuser\\llvmpipe-machine-$MODE.bat" >/dev/null 2>&1 || true
MLOG="$WORK/llvmpipe-machine-$MODE.log"
echo "[llvmpipe] 机器级（$MLOG）："
[ -f "$MLOG" ] && iconv -f CP936 -t UTF-8 -c "$MLOG" 2>/dev/null | grep -v '^[[:space:]]*$' | sed 's/^/    /' \
               || echo "    ⚠ 没拿到日志"

# ---------- 2. 用户级（必须在甲方自己的会话里写 HKCU） ----------
BAT="$WORK/llvmpipe-$MODE.bat"
case "$MODE" in
  install) ACT="setx $GVAR $GVAL
setx LIBGL_ALWAYS_SOFTWARE $SVAL" ;;
  unset)   ACT="reg delete \"HKCU\\Environment\" /v $GVAR /f
reg delete \"HKCU\\Environment\" /v LIBGL_ALWAYS_SOFTWARE /f" ;;
  check)   ACT="rem check only" ;;
esac
cat > "$BAT" <<EOF
@echo off
set L=Z:\\_dsh-asuser\\llvmpipe-$MODE.log
echo === llvmpipe $MODE (user scope) %DATE% %TIME% === > %L%
whoami >> %L% 2>&1
$ACT >> %L% 2>&1
echo --- HKCU Environment --- >> %L%
reg query "HKCU\\Environment" /v $GVAR >> %L% 2>&1
reg query "HKCU\\Environment" /v LIBGL_ALWAYS_SOFTWARE >> %L% 2>&1
echo DONE >> %L%
EOF
chmod a+r "$BAT"
if [ "$MODE" = check ]; then
  bash "$ASUSER" "$BAT" --wait 12 >/dev/null 2>&1 || true
else
  bash "$ASUSER" "$BAT" --wait 45 >/dev/null 2>&1 || true
fi
LOG="$WORK/llvmpipe-$MODE.log"
echo "[llvmpipe] 用户级（$LOG）："
[ -f "$LOG" ] && iconv -f CP936 -t UTF-8 -c "$LOG" 2>/dev/null | grep -v '^[[:space:]]*$' | sed 's/^/    /' \
              || echo "    ⚠ 没拿到日志（甲方没登录桌面？先跑 win10-run-as-user.sh --list）"

# ---------- 3. 判定 ----------
if [ "$MODE" = check ]; then
  M_OK=0; U_OK=0
  grep -qa "$GVAL" "$MLOG" 2>/dev/null && M_OK=1
  grep -qa "$GVAL" "$LOG"  2>/dev/null && U_OK=1
  if [ $M_OK -eq 1 ] && [ $U_OK -eq 1 ]; then
    echo "[llvmpipe] ✅ 机器级 + 用户级 $GVAR=$GVAL 都在位 ⇒ 双击 C:\\blender\\blender.exe 能开 GUI"; exit 0
  fi
  echo "[llvmpipe] ❌ 没设全（机器级=$M_OK 用户级=$U_OK）⇒ 甲方桌面上双击 blender.exe 仍会闪退（跑本脚本不带 --check 来设）" >&2; exit 1
fi
if [ "$MODE" = install ]; then
  if grep -qa "$GVAL" "$LOG" 2>/dev/null && grep -qa "$GVAL" "$MLOG" 2>/dev/null; then
    echo "[llvmpipe] ✅ 机器级 + 用户级都设好了；现在双击 C:\\blender\\blender.exe 就能开 GUI"; exit 0
  fi
  echo "[llvmpipe] ⚠ 只设上一半（多半是甲方没登录桌面，用户级没写成）⇒ 机器级下次登录生效；先跑 win10-run-as-user.sh --list 看看" >&2; exit 1
fi
echo "[llvmpipe] 已撤机器级 + 用户级（GUI 会回到打不开；无头 Cycles 渲染不受影响）"

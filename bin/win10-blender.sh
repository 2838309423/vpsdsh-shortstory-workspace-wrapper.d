#!/usr/bin/env bash
# win10-blender.sh —— 把一份 bpy(python) 脚本送到 usavps win10 客机里用 Blender 无头跑，产物落回宿主
#
# 用法：
#   bin/win10-blender.sh tools/roomgen/room_hello.py                 # 新 job（时间戳命名）
#   bin/win10-blender.sh tools/roomgen/room_hello.py --job mytest    # 指定 job 名（可复用同一目录）
#   bin/win10-blender.sh <脚本> -- --outdir Z:/x --samples 32        # `--` 之后原样传给脚本
#
# 数据通道（唯一）：宿主 /home/longxia/media-shared ⇄ 客机 Z:（virtiofs，卷标 shared）
#   media-shared/blender-jobs/<job>/
#       script/   送进去的 .py
#       run.bat   客机侧批处理（chcp 65001 + 重定向日志 + 记 EXITCODE）
#       logs/     run.log（UTF-8，宿主直接读）
#       out/      Blender 产物（png / blend / json）
#
# 设计口径：
#   * Blender 只在**客机**里跑；宿主只负责送脚本 + 读日志/取图 —— 客机是 Windows，Blender 才是原生的。
#   * 一律 `-b --factory-startup --python <script> --python-exit-code 1`：脚本抛异常 ⇒ 退出码非 0，
#     不会把"静默成功"混进产物。
#   * 长任务输出**必须重定向到文件**（guest-exec 的 base64 回传会截断）。
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
BLENDER_WIN=${WIN10_BLENDER:-'C:\blender\blender.exe'}
TIMEOUT=${WIN10_BLENDER_TIMEOUT:-3600}

USE=0; SCRIPT=""; JOB=""; PASSTHRU=()
while [ $# -gt 0 ]; do
  case "$1" in
    --job) JOB=$2; shift 2;;
    --timeout) TIMEOUT=$2; shift 2;;
    --blender) BLENDER_WIN=$2; shift 2;;
    --share) SHARE=$2; shift 2;;
    --) shift; PASSTHRU=("$@"); break;;
    -*) echo "未知参数 $1" >&2; exit 2;;
    *) if [ $USE -eq 0 ]; then SCRIPT=$1; USE=1; else echo "多余参数 $1" >&2; exit 2; fi; shift;;
  esac
done
[ -n "$SCRIPT" ] && [ -f "$SCRIPT" ] || { echo "用法: $0 <脚本.py> [--job NAME] [-- 脚本参数...]" >&2; exit 2; }
[ -n "$JOB" ] || JOB="job-$(date +%m%d-%H%M%S)"
SCRIPT=$(readlink -f "$SCRIPT")

JD="$SHARE/blender-jobs/$JOB"
mkdir -p "$JD/script" "$JD/logs" "$JD/out"
cp -f "$SCRIPT" "$JD/script/$(basename "$SCRIPT")"

# 客机用的 Z: 相对路径（统一正斜杠，Blender 在 Windows 上两种都吃）
ZJOB="Z:/blender-jobs/$JOB"
WINJOB=$(printf '%s' "$ZJOB" | tr '/' '\\')

{
  echo '@echo off'
  echo 'chcp 65001 >nul'
  echo 'set PYTHONIOENCODING=utf-8'
  printf '"%s" -b --factory-startup --python-exit-code 1 --python "%s" -- ' "$BLENDER_WIN" "${WINJOB}\\script\\$(basename "$SCRIPT")"
  for a in ${PASSTHRU+"${PASSTHRU[@]}"}; do printf '"%s" ' "$a"; done
  echo
  printf 'echo EXITCODE=%%ERRORLEVEL%%\n'
} > "$JD/run.bat.tmp"
# 上面最后两行要拼成一条命令，重写一遍更稳：
{
  echo '@echo off'
  echo 'chcp 65001 >nul'
  echo 'set PYTHONIOENCODING=utf-8'
  printf '"%s" -b --factory-startup --python-exit-code 1 --python "%s" --' "$BLENDER_WIN" "${WINJOB}\\script\\$(basename "$SCRIPT")"
  for a in ${PASSTHRU+"${PASSTHRU[@]}"}; do printf ' "%s"' "$a"; done
  printf ' > "%s\\logs\\run.log" 2>&1\n' "$WINJOB"
  printf 'echo EXITCODE=%%ERRORLEVEL%% >> "%s\\logs\\run.log"\n' "$WINJOB"
} > "$JD/run.bat"
rm -f "$JD/run.bat.tmp"

echo "[win10-blender] job=$JOB  script=$(basename "$SCRIPT")  blender=$BLENDER_WIN"
echo "[win10-blender] 宿主目录: $JD"
t0=$(date +%s)
set +e
WIN10_EXEC_PIDFILE="$JD/guest.pid" bash "$HERE/win10-exec.sh" --timeout "$TIMEOUT" cmd.exe /c "${WINJOB}\\run.bat"
rc=$?
set -e
t1=$(date +%s)
echo "[win10-blender] 客机批处理退出码=$rc  墙钟 $((t1-t0)) s"
echo "[win10-blender] 停这个 job（若还没结束）: bash bin/win10-exec.sh --kill-last  # pid 文件 $JD/guest.pid"
LOG="$JD/logs/run.log"
if [ -f "$LOG" ]; then
  echo "----- run.log 末尾 40 行（完整: $LOG） -----"
  tail -n 40 "$LOG"
  grep -q 'EXITCODE=0' "$LOG" || { echo "[win10-blender] ⚠ 客机侧 EXITCODE 非 0" >&2; exit 1; }
else
  echo "[win10-blender] ⚠ 没拿到 run.log（客机里 Blender 可能没起来）" >&2
  exit 1
fi
echo "[win10-blender] 产物: $(ls -1 "$JD/out" 2>/dev/null | tr '\n' ' ')"

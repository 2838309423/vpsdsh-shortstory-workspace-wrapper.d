#!/usr/bin/env bash
# win10-install-blender.sh —— 给 usavps 的 win10 KVM 客机装 / 体检 Blender（官方 Windows 便携版 zip）
#
# 用法：
#   bin/win10-install-blender.sh              # 幂等安装（已装且版本对 ⇒ 什么都不做）
#   bin/win10-install-blender.sh --check      # 只体检，不装
#   bin/win10-install-blender.sh --force      # 推倒重装（客机里先 rmdir C:\blender）
#   bin/win10-install-blender.sh --version 5.2.2
#
# 为什么是便携版 zip 而不是 msi：
#   * 免管理员、免注册表、免交互向导；SYSTEM 身份（guest-exec）下也装得动；
#   * 整包可复制/回滚，多版本能并存；坏了大不了删目录重解。
#
# 事实与坑：
#   * 客体 tar.exe（bsdtar）能解 zip；解压走 virtiofs（Z: → C:）实测 398 MB/79 s。
#   * 官方**不提供** .zip.sha256（404）⇒ 本脚本内嵌「本机实测已知良好」的 sha256，可用 --sha256 覆盖。
#   * 装完的路径固定为 C:\blender\blender.exe（bin/win10-blender.sh 的默认值）。
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
VERSION=${WIN10_BLENDER_VERSION:-4.5.14}
MIRROR=${WIN10_BLENDER_MIRROR:-https://download.blender.org/release}
DEST_WIN=${WIN10_BLENDER_DIR:-'C:\blender'}
CHECK=0; FORCE=0; SHA=""
TIMEOUT=${WIN10_BLENDER_TIMEOUT:-2400}

# 已知良好值（本机 2026-10-11 实测下载后 sha256sum 得到；官方页面不给 sha256 文件）
declare -A KNOWN_SHA=(
  [4.5.14]=b9533d2397ac1984db4466fb23a7a4649391cca93f6e84209f9bcc60d071c8b9
)

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift;;
    --force) FORCE=1; shift;;
    --version) VERSION=$2; shift 2;;
    --mirror) MIRROR=$2; shift 2;;
    --share) SHARE=$2; shift 2;;
    --sha256) SHA=$2; shift 2;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) echo "未知参数 $1" >&2; exit 2;;
  esac
done

SERIES=${VERSION%.*}
ZIP="blender-$VERSION-windows-x64.zip"
URL="$MIRROR/Blender$SERIES/$ZIP"
DL="$SHARE/_dl"
ZIP_PATH="$DL/$ZIP"
[ -z "$SHA" ] && SHA="${KNOWN_SHA[$VERSION]:-}"

ex() { bash "$HERE/win10-exec.sh" --timeout "$1" "${@:2}"; }

echo "[install-blender] 目标: win10 客机 $DEST_WIN  (版本 $VERSION)"

# ---------- 1. 体检 ----------
probe() {
  ex 120 cmd.exe /c "if exist $DEST_WIN\\blender.exe ($DEST_WIN\\blender.exe --version) else (echo __MISSING__)" 2>&1 |
    tr -d '\r' | grep -m1 -E '^Blender |__MISSING__' || echo "__MISSING__"
}
CUR=$(probe)
echo "[install-blender] 当前客机状态: $CUR"

if [ "$CUR" != "__MISSING__" ]; then
  curver=$(echo "$CUR" | awk '{print $2}')
  if [ "$curver" = "$VERSION" ] && [ $FORCE -eq 0 ]; then
    echo "[install-blender] ✅ 已装且版本一致（$CUR）⇒ 无需动作"
    exit 0
  fi
  [ $CHECK -eq 1 ] && { echo "[install-blender] 版本不一致：客机 $curver ≠ 目标 $VERSION" >&2; exit 1; }
fi
if [ $CHECK -eq 1 ]; then
  echo "[install-blender] ❌ 客机没装 Blender（去掉 --check 即开始安装）" >&2
  exit 1
fi

# ---------- 2. 宿主下载 + 校验 ----------
mkdir -p "$DL"
need_dl=1
if [ -s "$ZIP_PATH" ]; then
  have=$(sha256sum "$ZIP_PATH" | awk '{print $1}')
  if [ -n "$SHA" ] && [ "$have" = "$SHA" ]; then
    echo "[install-blender] 本地已有装包且 sha256 匹配 ⇒ 跳过下载"
    need_dl=0
  elif [ -z "$SHA" ]; then
    echo "[install-blender] 本地已有装包（未内嵌已知 sha256，跳过校验）"
    need_dl=0
  else
    echo "[install-blender] ⚠ 本地装包 sha256 不匹配（$have）⇒ 重新下载"
    rm -f "$ZIP_PATH"
  fi
fi
if [ $need_dl -eq 1 ]; then
  echo "[install-blender] 下载 $URL"
  curl -fSL --retry 3 -o "$ZIP_PATH.part" "$URL" || { echo "下载失败" >&2; exit 1; }
  mv "$ZIP_PATH.part" "$ZIP_PATH"
fi
GOT=$(sha256sum "$ZIP_PATH" | awk '{print $1}')
echo "[install-blender] 装包 $ZIP  $(stat -c%s "$ZIP_PATH") B  sha256=$GOT"
if [ -n "$SHA" ] && [ "$GOT" != "$SHA" ]; then
  echo "[install-blender] ❌ sha256 与已知良好值不符，中止（要接受请用 --sha256 $GOT）" >&2
  exit 1
fi
printf '%s  %s\n' "$GOT" "$ZIP" > "$ZIP_PATH.sha256"

# ---------- 3. 客机内解压安装（写成 .bat 跑，日志落共享盘） ----------
BAT="$DL/install-blender.bat"
LOG_HOST="$DL/install-blender.log"
rm -f "$LOG_HOST"
{
  echo '@echo off'
  echo 'chcp 65001 >nul'
  printf 'echo ==== install blender %s from %s ====\n' "$VERSION" "$ZIP"
  if [ $FORCE -eq 1 ]; then
    printf 'if exist %s rmdir /s /q %s\n' "$DEST_WIN" "$DEST_WIN"
  fi
  printf 'tar -xf Z:\\_dl\\%s -C C:\\\n' "$ZIP"
  printf 'echo TAR_EXIT=%%ERRORLEVEL%%\n'
  printf 'if exist C:\\blender-%s-windows-x64 move C:\\blender-%s-windows-x64 %s\n' "$VERSION" "$VERSION" "$DEST_WIN"
  printf 'echo MOVE_EXIT=%%ERRORLEVEL%%\n'
  printf '%s\\blender.exe --version\n' "$DEST_WIN"
  echo 'echo INSTALL_DONE'
} > "$BAT"
echo "[install-blender] 客机内解压安装中（398 MB，实测 ~80 s）…"
ex "$TIMEOUT" cmd.exe /c "Z:\\_dl\\install-blender.bat > Z:\\_dl\\install-blender.log 2>&1" >/dev/null 2>&1
if [ -f "$LOG_HOST" ]; then tail -6 "$LOG_HOST"; else echo "⚠ 没拿到客机安装日志" >&2; fi

# ---------- 4. 验收 ----------
NOW=$(probe)
echo "[install-blender] 装后: $NOW"
if echo "$NOW" | grep -q "Blender $VERSION"; then
  echo "[install-blender] ✅ 完成：$DEST_WIN\\blender.exe = $NOW"
  echo "[install-blender] 试跑: bash bin/win10-blender.sh tools/roomgen/room_hello.py -- --samples 8 --res 320x180"
  exit 0
fi
echo "[install-blender] ❌ 验收失败：客机里没拿到预期的 Blender $VERSION" >&2
exit 1

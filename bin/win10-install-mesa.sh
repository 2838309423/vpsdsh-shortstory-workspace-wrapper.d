#!/usr/bin/env bash
# win10-install-mesa.sh —— 给客机里的 Blender 装上 **软件 OpenGL（Mesa llvmpipe）**，让 GUI 能开
#
# 为什么需要它：
#   客机是 KVM 虚拟机，显卡是 QXL/virtio-gpu，**没有任何 OpenGL 4.3 驱动**
#   ⇒ 双击 blender.exe 只会弹 "Unsupported Graphics Card Configuration"（实测 2026-10-11）。
#   把 Mesa 的 opengl32.dll 放到 blender.exe 旁边，Blender 就会走**软件渲染（llvmpipe）**：
#   GUI 能开、能转视角、能按 F12 出图；代价是慢（软件光栅化，靠 CPU）。
#   ⚠ 无头渲染（`bin/win10-blender.sh`，Cycles CPU）**本来就不需要 GL**，加不加这个都不影响。
#
# ⚠⚠ 2026-10-11 晚补的**关键一步**（甲方报"双击 blender.exe 灰窗口一闪就没了"的真根因）：
#   光把两个 DLL 放过去**不够**。Mesa 26.x 的 Windows WGL **默认挑 d3d12 驱动**，在 QXL 客机上
#   它只绑得到 `Microsoft Basic Render Driver`（假 3D）⇒ 上下文建一半，Blender 立刻退出
#   （exit code **-2147024809 = 0x80070057**）。必须再强制 **GALLIUM_DRIVER=llvmpipe**：
#   `bash bin/win10-force-llvmpipe.sh`（本脚本第 4 步自动调它；幂等，机器级 + 用户级都设）。
#
# 用法：
#   bin/win10-install-mesa.sh              # 下载+解压+装进客机 C:\blender\，并做 EEVEE 功能验证
#   bin/win10-install-mesa.sh --check      # 只看客机里装没装、GL 能不能用
#   bin/win10-install-mesa.sh --remove     # 从 C:\blender\ 撤掉（回到"GUI 打不开、无头照跑"）
#   bin/win10-install-mesa.sh --mesa-version 26.2.4
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
DL="$SHARE/_dl/mesa"
MESA_VERSION=${MESA_VERSION:-26.2.4}
# mingw 版是**自带依赖**的（msvc 版要 VC++ 运行库，而客机里没装 ⇒ 会静默加载失败，实测踩过）
MESA_FLAVOR=${MESA_FLAVOR:-mingw}
MESA_ARCHIVE=mesa3d-$MESA_VERSION-release-$MESA_FLAVOR.7z
MESA_URL=${MESA_URL:-https://github.com/pal1000/mesa-dist-win/releases/download/$MESA_VERSION/$MESA_ARCHIVE}
BLENDER_DIR=${WIN10_BLENDER_DIR:-'C:\blender'}
TIMEOUT=${WIN10_MESA_TIMEOUT:-900}
MODE=install

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check; shift;;
    --remove) MODE=remove; shift;;
    --mesa-version) MESA_VERSION=$2; MESA_URL=${MESA_URL/$MESA_VERSION/$MESA_VERSION}; shift 2;;
    --share) SHARE=$2; DL="$SHARE/_dl/mesa"; shift 2;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) echo "未知参数 $1" >&2; exit 2;;
  esac
done

ex() { bash "$HERE/win10-exec.sh" --timeout "$1" "${@:2}"; }

# Mesa 的 opengl32.dll 是个瘦壳，真正干活的是 libgallium_wgl.dll；两个都要放过去。
DLLS=(opengl32.dll libgallium_wgl.dll)

# ---------- 探针：GL 到底能不能用 ----------
# 用一次 **EEVEE 渲染**当功能判据：EEVEE 必须要 GL 上下文，能渲出来 ⇒ GL 通了 ⇒ GUI 也就能开。
GLTEST_PY="$SHARE/_dl/mesa_gltest.py"
cat > "$GLTEST_PY" <<'PY'
import bpy, sys
sc = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        continue
sc.render.resolution_x, sc.render.resolution_y = 320, 180
sc.render.filepath = r"Z:\_dl\mesa_gltest.png"
try:
    bpy.ops.render.render(write_still=True)
    print("MESA_GLTEST=OK engine=%s" % sc.render.engine)
except Exception as e:
    print("MESA_GLTEST=FAIL %s: %s" % (type(e).__name__, e))
    sys.exit(3)
PY

gltest() {
  # ⚠ 必须**带着 GALLIUM_DRIVER=llvmpipe 跑**：不强制的话 Mesa 会挑 d3d12 ⇒ 假 GL 上下文 ⇒
  #   要么 E_INVALIDARG 秒退，要么渲到一半在 GPU_fence_wait 里 ACCESS_VIOLATION（都是实测过的假绿/假红）。
  #    所以这里走一个纯 ASCII .bat（`set "VAR=…"` 形式，避免 `set VAR=1 && …` 的行尾空格陷阱）。
  cat > "$SHARE/_dl/mesa_gltest.bat" <<'BAT'
@echo off
set "GALLIUM_DRIVER=llvmpipe"
set "LIBGL_ALWAYS_SOFTWARE=1"
C:\blender\blender.exe -b --factory-startup --python-exit-code 1 --python Z:\_dl\mesa_gltest.py
BAT
  chmod a+r "$SHARE/_dl/mesa_gltest.bat"
  ex "$TIMEOUT" cmd.exe /c 'Z:\_dl\mesa_gltest.bat' 2>&1 | grep -a 'MESA_GLTEST=' | tail -1
}

echo "[mesa] 客机 $BLENDER_DIR  ← Mesa $MESA_VERSION（软件 OpenGL / llvmpipe）"

if [ "$MODE" = check ]; then
  echo "[mesa] 客机里的 opengl32.dll: $(ex 60 cmd.exe /c "if exist $BLENDER_DIR\\opengl32.dll (echo 有) else (echo 无)" | tr -d '\r' | grep -m1 .)"
  echo "[mesa] 驱动强制（GALLIUM_DRIVER）:"; bash "$HERE/win10-force-llvmpipe.sh" --check 2>&1 | sed 's/^/    /'
  echo "[mesa] GL 功能测试: $(gltest)"
  exit 0
fi

if [ "$MODE" = remove ]; then
  for d in "${DLLS[@]}"; do ex 60 cmd.exe /c "if exist $BLENDER_DIR\\$d del /f /q $BLENDER_DIR\\$d"; done
  echo "[mesa] 已撤掉：${DLLS[*]}（GUI 会回到打不开，无头渲染不受影响）"
  echo "[mesa] 提示：GALLIUM_DRIVER 环境变量留着无害（没有 Mesa 的 opengl32.dll 时没人读它）；要清用 bin/win10-force-llvmpipe.sh --unset"
  exit 0
fi

# ---------- 1. 宿主侧：下载 + 解压（有缓存就跳过） ----------
mkdir -p "$DL"
LOCAL7Z="$DL/$MESA_ARCHIVE"
[ -s "$LOCAL7Z" ] || { echo "[mesa] 下载 $MESA_URL"; curl -fSL --retry 3 -o "$LOCAL7Z.part" "$MESA_URL" && mv "$LOCAL7Z.part" "$LOCAL7Z"; }
SRC="$DL/extracted-$MESA_FLAVOR/x64"
if [ ! -f "$SRC/opengl32.dll" ]; then
  echo "[mesa] 解压 $MESA_ARCHIVE …"
  rm -rf "$DL/extracted-$MESA_FLAVOR"
  7z x -y "$LOCAL7Z" -o"$DL/extracted-$MESA_FLAVOR" >/dev/null || { echo "7z 解压失败" >&2; exit 1; }
fi
for d in "${DLLS[@]}"; do
  [ -f "$SRC/$d" ] || { echo "[mesa] ❌ 解压结果里缺 $d" >&2; exit 1; }
done
chmod -R a+rX "$DL" 2>/dev/null || true
echo "[mesa] 宿主已备好：$(ls -la "$SRC"/{opengl32.dll,libgallium_wgl.dll} | awk '{printf "%s(%s) ", $9, $5}')"

# ---------- 2. 客机侧：拷到 blender.exe 旁边 ----------
CMDS=""
for d in "${DLLS[@]}"; do CMDS="$CMDS copy /y Z:\\_dl\\mesa\\extracted-$MESA_FLAVOR\\x64\\$d $BLENDER_DIR\\$d >nul &"; done
OUT=$(ex "$TIMEOUT" cmd.exe /c "$CMDS echo MESA_COPIED")
echo "$OUT" | tr -d '\r' | grep -q MESA_COPIED && echo "[mesa] 已拷入客机 $BLENDER_DIR" || { echo "[mesa] ⚠ 拷贝未确认" >&2; }

# ---------- 3. 强制走 llvmpipe（**少了这步 GUI 必闪退**，见文件头） ----------
bash "$HERE/win10-force-llvmpipe.sh" || echo "[mesa] ⚠ 强制 llvmpipe 没完全成功（多半是甲方没登录桌面 ⇒ 只设了机器级；下次登录生效）" >&2

# ---------- 4. 功能验证 ----------
R=$(gltest)
echo "[mesa] GL 功能测试: $R"
case "$R" in
  *OK*) echo "[mesa] ✅ 软件 OpenGL 生效 ⇒ Blender GUI 现在开得起来（慢，但能用）"; exit 0;;
  *)    echo "[mesa] ❌ 仍然拿不到 GL 上下文；GUI 还是开不了（无头 Cycles 渲染不受影响）" >&2; exit 1;;
esac

#!/usr/bin/env bash
# publish-share.sh —— 把「DSH 驱动 win10 里的 Blender」这套东西发布成宿主⇄客机共享盘上的**体验包**
#
# 用法：
#   bin/publish-share.sh                 # 重新发布（幂等，覆盖同名文件）
#   SHARE=/别的路径 bin/publish-share.sh
#
# 产物：/home/longxia/media-shared/dsh-blender-roomgen.d/
#   ├── README.md          先看这个（中文；Windows 记事本/VS Code 都能开）
#   ├── scripts/           bpy 脚本 + 客机里可双击的 .bat
#   ├── out/               已渲好的图 + .blend（.blend 可在 Windows 里用 Blender GUI 打开）
#   ├── host/              宿主（Linux）侧入口脚本副本
#   └── _manifest.txt      本包内容 md5 清单 + 生成时间 + 仓 HEAD
#
# 口径：仓（$DSH_VPS_ROOT）永远是**真值源**，共享盘里的包是**投影**（给 Windows 侧体验用）。
#       改脚本请改仓里的，再跑本脚本重新发布 —— 别在共享盘里直接改。
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
PKG=${PKG:-$SHARE/dsh-blender-roomgen.d}
JOBS=${JOBS:-$SHARE/blender-jobs}

mkdir -p "$PKG/scripts" "$PKG/out" "$PKG/host"

# ---------- 1. 脚本 ----------
cp -f "$ROOT/tools/roomgen/room_hello.py"  "$PKG/scripts/"
cp -f "$ROOT/tools/roomgen/room_living.py" "$PKG/scripts/" 2>/dev/null || true

# ---------- 2. 宿主侧入口副本 ----------
for f in win10-exec.sh win10-blender.sh win10-install-blender.sh win10.sh; do
  [ -f "$ROOT/bin/$f" ] && cp -f "$ROOT/bin/$f" "$PKG/host/"
done
chmod 755 "$PKG"/host/*.sh 2>/dev/null || true

# ---------- 3. 客机里可双击的 .bat ----------
#  ⚠ .bat 必须**纯 ASCII**：cmd.exe 是按 OEM 代码页(本机 cp936)逐行解析批处理文件的，
#    UTF-8 的中文注释会被解成乱码（甚至吐出 & | 之类元字符）⇒ 整行解析坏、后续命令错位。
#    实测后果：Blender 丢了 -b 参数，以 GUI 模式启动并挂死。中文一律放 README，不放 .bat。
gen_bat() {  # $1=产物子目录名(ASCII)  $2=脚本名  $3=英文说明(ASCII)
  cat > "$PKG/scripts/run-$1.bat" <<EOF
@echo off
chcp 65001 >nul
setlocal
rem Roomgen runner -- $3
rem Double-click this file inside the win10 guest (headless Cycles render, no GUI needed).
rem Overridable env: ROOMGEN_OUT=outdir  ROOMGEN_SAMPLES=n  ROOMGEN_NOUI=1 (no popup, no pause)
set HERE=%~dp0
set OUT=%ROOMGEN_OUT%
if "%OUT%"=="" set OUT=%HERE%..\\out\\$1
set SAMP=%ROOMGEN_SAMPLES%
if "%SAMP%"=="" set SAMP=32
if not exist "C:\\blender\\blender.exe" (
  echo [x] C:\\blender\\blender.exe not found.
  echo     On the Linux host run:  bash bin/win10-install-blender.sh
  if not "%ROOMGEN_NOUI%"=="1" pause
  exit /b 1
)
echo ============================================================
echo  Rendering : $3
echo  Engine    : Cycles CPU / %SAMP% samples / 960x540 / 3 shots
echo  Output    : %OUT%
echo  Notes     : see ../README.md  (Chinese)
echo ============================================================
"C:\\blender\\blender.exe" -b --factory-startup --python-exit-code 1 --python "%HERE%$2" -- --outdir "%OUT%" --samples %SAMP% --res 960x540
echo.
echo exit code = %ERRORLEVEL%   ^(0 = ok; last line should be __SELFTEST__ 13 0^)
if not "%ROOMGEN_NOUI%"=="1" (
  start "" "%OUT%"
  pause
)
EOF
}
gen_bat hello  room_hello.py  "hello bedroom (4.2 x 3.6 x 2.7 m)"
[ -f "$PKG/scripts/room_living.py" ] && gen_bat living room_living.py "living room (written by the DSH agent)"

# ---------- 4. 已渲产物（图 + blend） ----------
sync_out() {  # $1=job 目录  $2=目标子目录
  [ -d "$JOBS/$1/out" ] || return 0
  mkdir -p "$PKG/out/$2"
  cp -f "$JOBS/$1/out/"*.png "$PKG/out/$2/" 2>/dev/null || true
  cp -f "$JOBS/$1/out/"*.blend "$PKG/out/$2/" 2>/dev/null || true
  cp -f "$JOBS/$1/out/scene_report.json" "$PKG/out/$2/" 2>/dev/null || true
  rm -f "$PKG/out/$2"/*.blend1        # Blender 覆盖保存时的备份，不进包
}
sync_out hello-01   hello
sync_out agent-demo living

# ---------- 5. README ----------
BL=$(bash "$HERE/win10-exec.sh" --timeout 120 cmd.exe /c 'if exist C:\blender\blender.exe (C:\blender\blender.exe --version) else (echo 未安装)' 2>/dev/null | tr -d '\r' | grep -m1 . || echo "未探测到")
cat > "$PKG/README.md" <<EOF
# dsh-blender-roomgen.d —— DSH 驱动 win10 里的 Blender 搭「3D 小房间」

这是 **体验包**：宿主 Linux 上的 DSH(DeepSeek) 当 agent 写 python，驱动这台 KVM 里的
**win10 客机**用 Blender **无头渲染** 出短剧用的 3D 房间；产物经共享盘（客机里的 \`Z:\`，就是本目录所在的盘）
回到两边都能看。

- 客机侧 Blender：**$BL**（\`C:\\blender\\blender.exe\`）
- 渲染器：**Cycles CPU**（客机无 GPU 直通，EEVEE 在无头下要 GL 上下文，靠不住）
- 全案文档（宿主上）：\`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/方案-dsh驱动win10-blender-3D小房间-261011.md\`

## 三种体验方式

### A. 在 Windows 里双击（最快，1~3 分钟出图）
1. 打开 \`Z:\\dsh-blender-roomgen.d\\scripts\\\`
2. 双击 **\`run-hello.bat\`** —— 渲染样板卧室；双击 **\`run-living.bat\`** —— 渲染 agent 写的小客厅
3. 跑完会自动弹出 \`out\\<名字>\\\` 目录，里面是 3 张 PNG（全景 / 中景 / 特写）+ 一个 \`.blend\`
4. 窗口里末行应看到 \`__SELFTEST__ 13 0\`（13 条断言全过；非 0 就是有问题）

> 前提：客机里已装 Blender（见下）。没装的话 .bat 会提示你去宿主跑安装器。

### B. 在 Windows 里打开 .blend 自由玩
\`Z:\\dsh-blender-roomgen.d\\out\\hello\\room-hello.blend\` 双击 → Blender GUI 打开 →
可以自己转视角、关灯开灯、加家具、按 F12 出图。**这是最直观的那种"感受"。**

### C. 在 Linux 宿主上让 DSH 再来一遍
\`\`\`bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d
bash bin/win10-blender.sh tools/roomgen/room_hello.py --job myroom -- --samples 48 --res 1280x720
# 或者让 agent 自己写一版（自然语言给需求）：
source bin/env.sh && dsh headless "用 tools/roomgen/room_hello.py 当模板，写一间日式茶室并用 bin/win10-blender.sh 渲出来"
\`\`\`

## 目录内容

| 路径 | 说明 |
|---|---|
| \`scripts/room_hello.py\` | 样板卧室：4.2×3.6×2.7 m，墙体/门/窗 + 家具 + 3 机位 + 末行自检 |
| \`scripts/room_living.py\` | **DSH agent 自己写的**小客厅（沙发/茶几/落地灯/电视墙/地毯/边柜） |
| \`scripts/run-*.bat\` | 客机里双击即渲（无头 Cycles CPU） |
| \`out/hello/\` | 样板卧室产物（960×540 PNG ×3 + \`room-hello.blend\` + \`scene_report.json\`） |
| \`out/living/\` | agent 版小客厅产物（640×360 PNG ×3 + \`room-living.blend\`） |
| \`host/*.sh\` | 宿主（Linux）侧入口：客机执行器 / job 运行器 / Blender 安装器（**副本**） |
| \`_manifest.txt\` | 本包 md5 清单 + 生成时间 + 仓 HEAD |

## 客机里装 Blender（宿主上一条命令，幂等）

\`\`\`bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d
bash bin/win10-install-blender.sh          # 已装且版本对 ⇒ 什么都不做
bash bin/win10-install-blender.sh --check  # 只体检
bash bin/win10-install-blender.sh --force  # 推倒重装
\`\`\`

## 改脚本的正确姿势

**仓是真值源，本目录是投影。** 改 \`tools/roomgen/*.py\`（或让 agent 改），再回宿主跑
\`bash bin/publish-share.sh\` 重新发布到本目录；别在这里直接改，否则下次发布就被覆盖了。

---
生成时间：$(date -Is)　｜　宿主：usavps（Ubuntu 22.04）　｜　客机：win10 22H2（KVM）
EOF

# 共享盘要给**客机**的 SYSTEM/服务身份读得到：一律放开读权限（别改属主）
chmod -R a+rX "$PKG" 2>/dev/null || true

# ---------- 6. 清单 ----------
{
  echo "# dsh-blender-roomgen.d 内容清单"
  echo "# 生成: $(date -Is)"
  echo "# 仓 HEAD: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)"
  echo "# 客机 Blender: $BL"
  echo "#"
  ( cd "$PKG" && find . -type f ! -name _manifest.txt -printf '%s\t' -exec md5sum {} \; | awk '{printf "%10d  %s  %s\n", $1, $2, $3}' | sort -k3 )
} > "$PKG/_manifest.txt"

echo "[publish-share] 已发布到 $PKG"
ls -la "$PKG"; echo; tail -n +1 "$PKG/_manifest.txt" | head -20

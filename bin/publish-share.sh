#!/usr/bin/env bash
# publish-share.sh —— 把「驱动 win10 里的 Blender」这套东西发布成**独立体验仓** + 共享盘投影
#
# 用法：
#   bin/publish-share.sh              # 重建体验仓内容 + 同步到共享盘
#   bin/publish-share.sh --push       # 再 commit + push 到 gitee
#   bin/publish-share.sh --no-guest   # 跳过客机 Blender 版本探测（客机没起时用）
#   REPO=/别的路径 SHARE=/别的路径 bin/publish-share.sh
#
# 三层结构（别搞混）：
#   ① 本仓（$DSH_VPS_ROOT）= **脚本真值源**：tools/roomgen/*.py、bin/win10-*.sh、media-shared/blender-jobs/
#   ② 体验仓 REPO=/home/longxia/helloworld-blender-roomgen.d = **成品仓**（有 .git，推 gitee）
#        其中 scripts/ bin/ out/ README.md _manifest.txt 由本脚本**生成**；docs/ 在那边手工维护（本脚本不碰）
#   ③ 共享盘 PKG=$SHARE/helloworld-blender-roomgen.d = ②的**投影**（无 .git，给 Windows 侧双击用）
#
#   ⇒ 改脚本请改 ① 再跑本脚本；别直接改 ②③ 里生成出来的文件，下次发布就被覆盖。
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
SHARE=${SHARE:-/home/longxia/media-shared}
REPO=${REPO:-/home/longxia/helloworld-blender-roomgen.d}
PKG=${PKG:-$SHARE/helloworld-blender-roomgen.d}
JOBS=${JOBS:-$SHARE/blender-jobs}
PUSH=0; GUEST=1
for a in "$@"; do case "$a" in
  --push) PUSH=1;;
  --no-guest) GUEST=0;;
  -h|--help) sed -n '2,24p' "$0"; exit 0;;
  *) echo "未知参数 $a" >&2; exit 2;;
esac; done

[ -d "$REPO/.git" ] || { echo "[publish-share] ⚠ $REPO 不是 git 仓（缺 .git）" >&2; exit 1; }

mkdir -p "$REPO/scripts" "$REPO/bin" "$REPO/out" "$REPO/docs"

# ---------- 1. bpy 脚本 ----------
cp -f "$ROOT/tools/roomgen/room_hello.py"  "$REPO/scripts/"
cp -f "$ROOT/tools/roomgen/room_living.py" "$REPO/scripts/" 2>/dev/null || true

# ---------- 2. 宿主侧入口 ----------
for f in win10-exec.sh win10-blender.sh win10-install-blender.sh win10.sh; do
  [ -f "$ROOT/bin/$f" ] && cp -f "$ROOT/bin/$f" "$REPO/bin/"
done
chmod 755 "$REPO"/bin/*.sh 2>/dev/null || true

# ---------- 3. 客机里可双击的 .bat ----------
#  ⚠ .bat 必须**纯 ASCII**：cmd.exe 是按 OEM 代码页(本机 cp936)逐行解析批处理文件的，
#    UTF-8 的中文注释会被解成乱码（甚至吐出 & | 之类元字符）⇒ 整行解析坏、后续命令错位。
#    实测后果：Blender 丢了 -b 参数，以 GUI 模式启动并挂死。中文一律放 README，不放 .bat。
gen_bat() {  # $1=产物子目录名(ASCII)  $2=脚本名  $3=英文说明(ASCII)
  cat > "$REPO/scripts/run-$1.bat" <<EOF
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
[ -f "$REPO/scripts/room_living.py" ] && gen_bat living room_living.py "living room (written by the DSH agent)"

# 硬闸门：.bat 里出现任何非 ASCII 字节就中止发布（上面那条坑太贵，不能靠记性）
if LC_ALL=C grep -lP '[^\x00-\x7F]' "$REPO"/scripts/*.bat >/dev/null 2>&1; then
  echo "[publish-share] ❌ 有 .bat 含非 ASCII 字节，拒绝发布：" >&2
  LC_ALL=C grep -nP '[^\x00-\x7F]' "$REPO"/scripts/*.bat >&2
  exit 1
fi

# ---------- 4. 已渲产物（图 + blend） ----------
sync_out() {  # $1=job 目录  $2=目标子目录
  [ -d "$JOBS/$1/out" ] || return 0
  mkdir -p "$REPO/out/$2"
  cp -f "$JOBS/$1/out/"*.png "$REPO/out/$2/" 2>/dev/null || true
  cp -f "$JOBS/$1/out/"*.blend "$REPO/out/$2/" 2>/dev/null || true
  cp -f "$JOBS/$1/out/scene_report.json" "$REPO/out/$2/" 2>/dev/null || true
  rm -f "$REPO/out/$2"/*.blend1        # Blender 覆盖保存时的备份，不进包
}
sync_out hello-01   hello
sync_out agent-demo living

# ---------- 5. 方案文档（从本仓拷过来，保持体验仓自足） ----------
cp -f "$ROOT/docs/方案-dsh驱动win10-blender-3D小房间-261011.md" "$REPO/docs/方案与路线图.md" 2>/dev/null || true

# ---------- 6. README ----------
if [ $GUEST -eq 1 ]; then
  BL=$(bash "$HERE/win10-exec.sh" --timeout 120 cmd.exe /c 'if exist C:\blender\blender.exe (C:\blender\blender.exe --version) else (echo 未安装)' 2>/dev/null | tr -d '\r' | grep -m1 . || echo "未探测到")
else
  BL="未探测（--no-guest）"
fi
cat > "$REPO/README.md" <<EOF
# helloworld-blender-roomgen.d —— 驱动 win10 里的 Blender 搭「3D 小房间」

**最小 MVP 体验包**：宿主 Linux 上的 DSH(DeepSeek) 当 agent 写 python，驱动这台 KVM 里的
**win10 客机**用 Blender **无头渲染**出短剧用的 3D 房间；产物经共享盘（客机里的 \`Z:\`，就是本目录所在的盘）
回到两边都能看。

> 目录名为什么叫 \`helloworld-blender-roomgen.d\`：这是 **helloworld 级最小验证**，
> 而且它**不是 DSH 专属**的 —— 核心只有「guest-agent 下命令 + virtiofs 送文件 + Blender 无头渲」，
> DSH 只是恰好坐在最上层写脚本的那个 agent。换成别的 agent（或你自己手写脚本）照样能用。

- 客机侧 Blender：**$BL**（\`C:\\blender\\blender.exe\`）
- 渲染器：**Cycles CPU**（客机无 GPU 直通，EEVEE 在无头下要 GL 上下文，靠不住）
- 施工文档：\`docs/最小MVP-搭建与实测.md\`（从零照做一遍）
- 方案与路线图：\`docs/方案与路线图.md\`（取舍、L0→L4、未决事项）
- 上游工作区仓（真值源）：\`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/\`

## 三种体验方式

### A. 在 Windows 里双击（最快，1~3 分钟出图）
1. 打开 \`Z:\\helloworld-blender-roomgen.d\\scripts\\\`
2. 双击 **\`run-hello.bat\`** —— 渲染样板卧室；双击 **\`run-living.bat\`** —— 渲染 agent 写的小客厅
3. 跑完会自动弹出 \`out\\<名字>\\\` 目录，里面是 3 张 PNG（全景 / 中景 / 特写）+ 一个 \`.blend\`
4. 窗口里末行应看到 \`__SELFTEST__ 13 0\`（13 条断言全过；非 0 就是有问题）

> 前提：客机里已装 Blender（见下）。没装的话 .bat 会提示你去宿主跑安装器。

### B. 在 Windows 里打开 .blend 自由玩
\`Z:\\helloworld-blender-roomgen.d\\out\\hello\\room-hello.blend\` 双击 → Blender GUI 打开 →
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
| \`README.md\` | 本文件 |
| \`docs/最小MVP-搭建与实测.md\` | **施工文档**：从零到跑通 7 步 + 验收口径 + 15 条坑 |
| \`docs/方案与路线图.md\` | 方案取舍表、实测时间线、L0→L4 路线图、成本、未决事项 |
| \`scripts/room_hello.py\` | 样板卧室：4.2×3.6×2.7 m，墙体/门/窗 + 家具 + 3 机位 + 末行自检 |
| \`scripts/room_living.py\` | **DSH agent 自己写的**小客厅（沙发/茶几/落地灯/电视墙/地毯/边柜） |
| \`scripts/run-*.bat\` | 客机里双击即渲（无头 Cycles CPU） |
| \`out/hello/\` | 样板卧室产物（960×540 PNG ×3 + \`room-hello.blend\` + \`scene_report.json\`） |
| \`out/living/\` | agent 版小客厅产物（640×360 PNG ×3 + \`room-living.blend\`） |
| \`bin/*.sh\` | 宿主（Linux）侧入口：客机执行器 / job 运行器 / Blender 安装器（**副本**） |
| \`_manifest.txt\` | 本包 md5 清单 + 生成时间 + 来源仓 HEAD + 客机 Blender 版本 |

## 客机里装 Blender（宿主上一条命令，幂等）

\`\`\`bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d
bash bin/win10-install-blender.sh          # 已装且版本对 ⇒ 什么都不做
bash bin/win10-install-blender.sh --check  # 只体检
bash bin/win10-install-blender.sh --force  # 推倒重装
\`\`\`

## 改脚本的正确姿势

本包里的 \`scripts/\`、\`bin/\`、\`out/\`、\`README.md\`、\`_manifest.txt\` 都是**生成物**：
改上游 \`tools/roomgen/*.py\`（或让 agent 改），再回宿主跑

\`\`\`bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d
bash bin/publish-share.sh --push     # 重建本包 → commit/push gitee → 同步共享盘
\`\`\`

别在共享盘（或本仓的生成物里）直接改，否则下次发布就被覆盖。

---
生成时间：$(date -Is)　｜　宿主：usavps（Ubuntu 22.04）　｜　客机：win10 22H2（KVM）
EOF

# 共享盘要给**客机**的 SYSTEM/服务身份读得到：一律放开读权限（别改属主）
chmod -R a+rX "$REPO" 2>/dev/null || true

# ---------- 7. 清单 ----------
{
  echo "# helloworld-blender-roomgen.d 内容清单"
  echo "# 生成: $(date -Is)"
  echo "# 来源仓 HEAD: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)"
  echo "# 本仓 HEAD（上一版）: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '首次')"
  echo "# 客机 Blender: $BL"
  echo "#"
  ( cd "$REPO" && find . -type f ! -name _manifest.txt ! -path './.git/*' -printf '%s\t' -exec md5sum {} \; \
      | awk '{printf "%10d  %s  %s\n", $1, $2, $3}' | sort -k3 )
} > "$REPO/_manifest.txt"

# ---------- 8. 推 gitee ----------
if [ $PUSH -eq 1 ]; then
  cd "$REPO"
  git add -A
  if git diff --cached --quiet; then
    echo "[publish-share] 本仓无改动，跳过 commit"
  else
    git commit -q -m "体验包重建 $(date +%F' '%H:%M)（来源仓 $(git -C "$ROOT" rev-parse --short HEAD)）"
    echo "[publish-share] 已 commit: $(git rev-parse --short HEAD)"
  fi
  git push -q origin HEAD && echo "[publish-share] 已 push 到 $(git remote get-url origin)"
  echo "[publish-share] 对账 本地=$(git rev-parse HEAD)  远端=$(git ls-remote origin HEAD | awk '{print $1}')"
else
  echo "[publish-share] （未加 --push ⇒ 只写盘不推 gitee）"
fi

# ---------- 9. 同步到共享盘（投影，无 .git） ----------
mkdir -p "$PKG"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '.git/' "$REPO/" "$PKG/"
else
  rm -rf "$PKG"; mkdir -p "$PKG"
  ( cd "$REPO" && tar --exclude ./.git -cf - . ) | ( cd "$PKG" && tar -xf - )
fi
chmod -R a+rX "$PKG" 2>/dev/null || true

echo "[publish-share] 体验仓: $REPO"
echo "[publish-share] 共享盘投影: $PKG  （客机里 = Z:\\helloworld-blender-roomgen.d\\）"
du -sh "$PKG" 2>/dev/null || true
ls -la "$PKG"

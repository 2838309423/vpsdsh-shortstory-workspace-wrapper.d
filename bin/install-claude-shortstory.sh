#!/usr/bin/env bash
# install-claude-shortstory.sh —— 给 shortstory 用户配「claude 本体 + deepseek-flash 单线接入」。
#
# 甲方 2026-10-10 口径：shortstory 用户只配 deepseek-flash 一个大模型，用途是角色蒸馏与写文。
#   ⇒ 只装两层：① claude 官方原生本体（与 longxia 同版本）② deepseek 端点与密钥。
#   ⇒ **不装** GLM 微代理 / 模型 toggle / longxia 的 settings.json、CLAUDE.md、skills、plugins。
#
# 为什么要复制而不是就地共享：/home/longxia 是 0750，shortstory 连目录都进不去；
#   所以一切必须落到 shortstory 自己家（/data/home/shortstory，/data 盘）。
#   密钥只以「整文件 tar 过 ssh 管道」的方式搬运，**不出现在命令行/日志/本脚本里**。
#
# 幂等：可重复执行。二进制按 md5 判重，配置与环境注入段都带标记、重复跑不叠加。
# 远端脚本一律用 `bash -s` + 位置参数传值，避免嵌套引号踩坑。
#
# 用法（以 longxia 身份跑）：
#   bash bin/install-claude-shortstory.sh            # 安装（含验收打印）
#   bash bin/install-claude-shortstory.sh --check    # 只体检，不改盘
set -euo pipefail

TARGET_USER="shortstory"
SSH_KEY="/home/longxia/.ssh/shortstory_ed25519"
REMOTE="${TARGET_USER}@127.0.0.1"

CLAUDE_VERSION="2.1.285"
SRC_CLAUDE_BIN="/home/longxia/.local/share/claude/versions/${CLAUDE_VERSION}"
SRC_DSK_ENV="/home/longxia/.deepseek-v4-flash.bashrc"
ENV_MARKER="claude (shortstory)"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

log() { printf '[install-claude-shortstory] %s\n' "$*"; }
die() { printf '[install-claude-shortstory] 失败: %s\n' "$*" >&2; exit 1; }

rsh() { ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" "$@"; }
# 远端跑一段从 stdin 读的脚本，参数按位置传入：rscript A B <<'EOF' ... $1 $2 ... EOF
rscript() { ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" "bash -s -- $(printf '%q ' "$@")"; }

# ---------------------------------------------------------------- 预检
[ -x "$SRC_CLAUDE_BIN" ] || die "源二进制不存在或不可执行: $SRC_CLAUDE_BIN"
[ -f "$SRC_DSK_ENV" ]    || die "deepseek 端点配置不存在: $SRC_DSK_ENV"
rsh true 2>/dev/null     || die "无法以 $REMOTE 登录（检查 $SSH_KEY）"
log "预检通过：源二进制 ${CLAUDE_VERSION}、deepseek 端点配置、ssh 通道均就绪"

# ---------------------------------------------------------------- 体检模式
if [ "$CHECK_ONLY" = 1 ]; then
  rscript "$ENV_MARKER" <<'EOF'
MARK="$1"
printf '=== shortstory claude 环境体检 ===\n'
printf '  claude 本体 : '
if [ -x "$HOME/.local/bin/claude" ]; then timeout 60 "$HOME/.local/bin/claude" --version </dev/null 2>&1 | head -1 || echo '（执行超时/失败）'; else echo '缺失'; fi
printf '  版本目录    : '
ls -l "$HOME/.local/share/claude/versions/" 2>/dev/null | awk 'NR>1{printf "%s(%s bytes) ", $9, $5}'; echo
printf '  端点配置    : '
if [ -f "$HOME/.deepseek-v4-flash.bashrc" ]; then stat -c '%a %n' "$HOME/.deepseek-v4-flash.bashrc"; else echo 缺失; fi
printf '  环境注入    : '
for f in "$HOME/.profile" "$HOME/.bashrc"; do
  if grep -qF "$MARK" "$f" 2>/dev/null; then printf '%s✓ ' "$(basename "$f")"; else printf '%s✗ ' "$(basename "$f")"; fi
done; echo
printf '  登录态变量  : '
bash -lc 'printf "ANTHROPIC_BASE_URL=%s  ANTHROPIC_MODEL=%s\n" "${ANTHROPIC_BASE_URL:-<未设置>}" "${ANTHROPIC_MODEL:-<未设置>}"'
printf '  裸命令模式  : '
if out="$(timeout 60 "$HOME/.local/bin/claude" --version </dev/null 2>&1 | head -1)"; then echo "$out（启动器自动注入环境 ✓）"; else echo "失败/超时: $out"; fi
EOF
  exit 0
fi

# ---------------------------------------------------------------- ① claude 本体
log "① 安装 claude 本体 ${CLAUDE_VERSION}（约 240 MB，走回环 ssh 管道）"
SRC_MD5="$(md5sum "$SRC_CLAUDE_BIN" | awk '{print $1}')"
DST_MD5="$(rscript "$CLAUDE_VERSION" <<'EOF' | awk '{print $1}'
md5sum "$HOME/.local/share/claude/versions/$1" 2>/dev/null || echo MISSING
EOF
)"

if [ "$SRC_MD5" = "$DST_MD5" ]; then
  log "   已存在且 md5 一致，跳过拷贝"
else
  rsh 'mkdir -p "$HOME/.local/bin" "$HOME/.local/share/claude/versions"'
  tar -C "$(dirname "$SRC_CLAUDE_BIN")" -cf - "$CLAUDE_VERSION" \
    | rsh 'tar -xf - -C "$HOME/.local/share/claude/versions"'
  rscript "$CLAUDE_VERSION" <<'EOF'
chmod 755 "$HOME/.local/share/claude/versions/$1"
EOF
  DST_MD5="$(rscript "$CLAUDE_VERSION" <<'EOF' | awk '{print $1}'
md5sum "$HOME/.local/share/claude/versions/$1" | awk '{print $1}'
EOF
)"
  [ "$SRC_MD5" = "$DST_MD5" ] || die "拷贝后 md5 不一致（源 $SRC_MD5 / 目标 $DST_MD5）"
  log "   md5 校验一致: $SRC_MD5"
fi
# ~/.local/bin/claude 刻意做成**启动器包装**而不是裸软链：
#   ssh 命令模式（非登录 shell）不读 .profile/.bashrc ⇒ env 全缺、PATH 里也没有 ~/.local/bin。
#   包装脚本自己注入环境再 exec 本体，于是「绝对路径直接调用」在任何 shell 模式下都成立：
#     ssh shortstory@127.0.0.1 '/data/home/shortstory/.local/bin/claude -p "..."'
rscript "$CLAUDE_VERSION" "$SRC_MD5" <<'EOF'
# ⚠ 必须先 rm：`cat > 软链` 会**穿透**写入链接目标。首版脚本就是这样把 240 MB 本体
#   覆写成启动器、再让启动器 exec 自己 ⇒ 单进程 99% CPU 死循环（2026-10-10 实测踩过）。
rm -f "$HOME/.local/bin/claude"
cat > "$HOME/.local/bin/claude" <<LAUNCHER
#!/bin/sh
# shortstory 用户的 claude 启动器（deepseek-flash）—— 由 longxia 侧
# bin/install-claude-shortstory.sh 生成，勿手改（改环境请改 ~/.claude-env.sh）。
# 先注入环境（路径无关、任何 shell 模式都成立），再交给官方本体。
[ -f "\$HOME/.claude-env.sh" ] && . "\$HOME/.claude-env.sh"
exec "\$HOME/.local/share/claude/versions/$1" "\$@"
LAUNCHER
chmod 755 "$HOME/.local/bin/claude"
# 反证：必须是普通文件（不是软链），且本体仍在
[ -L "$HOME/.local/bin/claude" ] && { echo "启动器仍是软链（穿透未消除）" >&2; exit 1; }
[ -x "$HOME/.local/share/claude/versions/$1" ] || { echo "本体缺失: versions/$1" >&2; exit 1; }
[ "$(md5sum "$HOME/.local/share/claude/versions/$1" | awk '{print $1}')" = "$2" ] \
  || { echo "本体 md5 与源不一致（被改动过）" >&2; exit 1; }
EOF
log "   启动器就位: ~/.local/bin/claude（注入环境后 exec versions/${CLAUDE_VERSION}）"

# ---------------------------------------------------------------- ② deepseek-flash 接入
log "② 安装 deepseek-flash 端点配置（整文件搬运，密钥不经命令行）"
tar -C "$(dirname "$SRC_DSK_ENV")" -cf - "$(basename "$SRC_DSK_ENV")" \
  | rsh 'tar -xf - -C "$HOME"'
rscript <<'EOF'
chmod 600 "$HOME/.deepseek-v4-flash.bashrc"
grep -q '^export ANTHROPIC_API_KEY=' "$HOME/.deepseek-v4-flash.bashrc" || { echo "端点配置缺密钥行" >&2; exit 1; }
grep -q '^export ANTHROPIC_BASE_URL=' "$HOME/.deepseek-v4-flash.bashrc" || { echo "端点配置缺 BASE_URL 行" >&2; exit 1; }
EOF
log "   落地: ~/.deepseek-v4-flash.bashrc (600)"

# ---------------------------------------------------------------- ③ 环境注入（幂等）
log "③ 写 ~/.claude-env.sh 并注入 ~/.profile / ~/.bashrc"
rsh 'cat > "$HOME/.claude-env.sh" && chmod 600 "$HOME/.claude-env.sh"' <<'REMOTE_ENV_EOF'
#!/bin/sh
# shortstory 用户的 claude 环境 —— deepseek-flash 单线（甲方 2026-10-10 口径）
# 由 longxia 侧 bin/install-claude-shortstory.sh 生成；要改就改这里，别手改 .profile/.bashrc 的注入段。
# 幂等：可重复 source。

# claude 本体所在目录
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# deepseek 端点与密钥（600；ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic）
if [ -f "$HOME/.deepseek-v4-flash.bashrc" ]; then
    . "$HOME/.deepseek-v4-flash.bashrc"
fi

# claude 运行优化（与 longxia 同款；DISABLE_AUTOUPDATER 防止自动更新覆盖这份手装本体）
export CLAUDE_CODE_EFFORT_LEVEL="max"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
export CLAUDE_AUTO_UPDATE=false
export DISABLE_AUTOUPDATER=1
REMOTE_ENV_EOF

rscript "$ENV_MARKER" <<'EOF'
MARK="$1"
for f in "$HOME/.profile" "$HOME/.bashrc"; do
  if grep -qF "$MARK" "$f" 2>/dev/null; then
    echo "  已有注入（跳过）: $f"
  else
    {
      printf '\n# >>> %s >>>\n' "$MARK"
      printf '[ -f "$HOME/.claude-env.sh" ] && . "$HOME/.claude-env.sh"\n'
      printf '# <<< %s <<<\n' "$MARK"
    } >> "$f"
    echo "  已注入: $f"
  fi
done
EOF

# ---------------------------------------------------------------- ④ 首启最小 onboarding
log "④ 最小 ~/.claude.json（只跳过首启向导，不含 longxia 的记忆/技能/历史）"
rscript <<'EOF'
if [ ! -f "$HOME/.claude.json" ]; then
  printf '%s\n' '{"hasCompletedOnboarding": true}' > "$HOME/.claude.json"
  chmod 600 "$HOME/.claude.json"
  echo "  已写 ~/.claude.json"
else
  echo "  已存在，保留不动"
fi
EOF

# ---------------------------------------------------------------- ⑤ 验收
log "⑤ 验收"
rscript <<'EOF'
printf '  claude 版本 : '; timeout 60 "$HOME/.local/bin/claude" --version </dev/null 2>&1 | head -1
printf '  占盘        : '; du -sh "$HOME/.local/share/claude" | awk '{print $1}'
printf '  端点配置权  : '; stat -c '%a' "$HOME/.deepseek-v4-flash.bashrc"
printf '  登录态变量  : '
bash -lc 'printf "BASE_URL=%s  MODEL=%s  KEY=%s\n" "${ANTHROPIC_BASE_URL:-<未设置>}" "${ANTHROPIC_MODEL:-<未设置>}" "$([ -n "${ANTHROPIC_API_KEY:-}" ] && echo 已注入 || echo 未注入)"'
EOF
log "完成。下一步冒烟测试：bash bin/smoke-claude-shortstory.sh"

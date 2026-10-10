#!/usr/bin/env bash
# smoke-claude-shortstory.sh —— shortstory 用户 claude 环境的冒烟测试。
#
# 以 longxia 身份跑；所有断言在 shortstory 侧执行。末行 `__SELFTEST__ <断言数> <失败数>`，
# 退出码 = 失败数（工作区自测口径：绿=0 则零日志阅读）。
#
# 覆盖：① 本体可执行且版本对 ② 端点变量（登录 shell）③ 密钥文件权限 600
#       ④ **真实补全一发**（ssh 命令模式 + 绝对路径 ⇒ 同时证明启动器包装自动注入环境）
set -uo pipefail

SSH_KEY="/home/longxia/.ssh/shortstory_ed25519"
REMOTE="shortstory@127.0.0.1"

ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" 'bash -s' <<'EOF'
pass=0; fail=0
ok() { printf '  [✓] %s\n' "$1"; pass=$((pass+1)); }
no() { printf '  [✗] %s\n' "$1"; fail=$((fail+1)); }
CL="$HOME/.local/bin/claude"

printf '=== shortstory claude 冒烟测试 ===\n'

# ① 本体（ssh 命令模式、绝对路径、无任何 shell 初始化）
# ⚠ 远端脚本是 `bash -s` 从 stdin 读的 ⇒ **任何子进程都不得继承这个 stdin**：
#   claude -p 在 stdin 非 TTY 时会去读 stdin，会把脚本剩下的行当输入吞掉（首版实测：
#   补全跑完、脚本却在中途 EOF 退出，`__SELFTEST__` 行凭空消失）。故逐条 `</dev/null`。
if [ -x "$CL" ]; then
  v="$(timeout 60 "$CL" --version </dev/null 2>&1 | head -1)"
  case "$v" in
    *2.1.285*) ok "裸命令模式可执行: $v" ;;
    *)         no "版本异常: $v" ;;
  esac
else
  no "启动器缺失: $CL"
fi

# ② 端点变量（登录 shell）
envout="$(bash -lc 'printf "%s|%s|%s" "${ANTHROPIC_BASE_URL:-}" "${ANTHROPIC_MODEL:-}" "$([ -n "${ANTHROPIC_API_KEY:-}" ] && echo key || echo nokey)"')"
IFS='|' read -r bu mo ky <<<"$envout"
[ "$bu" = "https://api.deepseek.com/anthropic" ] && ok "BASE_URL=$bu" || no "BASE_URL 异常: $bu"
[ "$mo" = "deepseek-flash[1m]" ]                 && ok "MODEL=$mo"     || no "MODEL 异常: $mo"
[ "$ky" = "key" ]                                && ok "密钥已注入登录态" || no "密钥未注入"

# ③ 密钥文件权限
for f in "$HOME/.deepseek-v4-flash.bashrc" "$HOME/.claude-env.sh" "$HOME/.claude.json"; do
  m="$(stat -c '%a' "$f" 2>/dev/null)"
  [ "$m" = "600" ] && ok "权限 600: $(basename "$f")" || no "权限 $m（期望 600）: $(basename "$f")"
done

# ④ 真实补全一发
t0="$(date +%s)"
out="$(timeout 300 "$CL" -p '只回复四个字：蒸馏就绪' --output-format json </dev/null 2>&1)"; rc=$?
t1="$(date +%s)"
if [ "$rc" -eq 0 ]; then
  # 客户端会在 JSON 之前打若干告警行（如 [claude-code:unrecognized_model] 与 auto mode 提示）
  # ⇒ 取**最后一条**以 { 开头、以 } 结尾的行才是结果 JSON。
  json="$(printf '%s\n' "$out" | grep -E '^\{.*\}$' | tail -1)"
  res="$(printf '%s' "$json" | jq -r '.result // empty' 2>/dev/null)"
  mdl="$(printf '%s' "$json" | jq -r '.modelUsage | keys | join(",")' 2>/dev/null)"
  in_tok="$(printf '%s' "$json" | jq -r '.usage.input_tokens // 0' 2>/dev/null)"
  out_tok="$(printf '%s' "$json" | jq -r '.usage.output_tokens // 0' 2>/dev/null)"
  if [ -n "$res" ]; then
    ok "真实补全 $((t1-t0))s 返回: $res"
    printf '      实际模型: %s | tokens in=%s out=%s\n' "${mdl:-未知}" "$in_tok" "$out_tok"
    printf '%s\n' "$out" | grep -E '^\[claude-code:' | sed 's/^/      客户端告警: /' || true
  else
    no "补全无 result 字段（退出码 0）"; printf '%s\n' "$out" | head -5
  fi
else
  no "补全失败，退出码 $rc"; printf '%s\n' "$out" | head -12
fi

printf '__SELFTEST__ %d %d\n' "$((pass+fail))" "$fail"
exit "$fail"
EOF

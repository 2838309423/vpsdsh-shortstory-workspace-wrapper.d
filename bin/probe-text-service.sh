#!/usr/bin/env bash
# 探活「服务器上的文本服务」（DeepSeek 官方 API）。**不打印密钥**，只打读数。
#   bash bin/probe-text-service.sh
# 退出码：0 = /v1/models 与一次真实 message 调用都通；2 = 找不到密钥；1 = 调用失败。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

KEY="${DEEPSEEK_API_KEY:-}"
if [ -z "$KEY" ] && [ -f "$DSH_HOME/.credentials.yaml" ]; then
  KEY="$(grep -oP '^\s*DEEPSEEK_API_KEY:\s*\K\S+' "$DSH_HOME/.credentials.yaml" | head -n1)"
fi
if [ -z "$KEY" ]; then
  KEY="$(grep -oP 'ANTHROPIC_API_KEY="\K[^"]+' "$HOME/.deepseek-v4-flash.bashrc" 2>/dev/null | head -n1)"
fi
if [ -z "$KEY" ]; then echo "probe: 找不到 DEEPSEEK_API_KEY（$DSH_HOME/.credentials.yaml 或启动环境）" >&2; exit 2; fi
echo "probe: key 已找到（长度 ${#KEY}，不打印内容）"

echo '--- /v1/models ---'
curl -sS -m 25 https://api.deepseek.com/v1/models -H "Authorization: Bearer $KEY" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(" ", m["id"], "ctx="+str(m.get("context_window")), "max_out="+str(m.get("max_output_tokens"))) for m in d.get("data",[])]' 2>/dev/null \
  || { echo "  /v1/models 失败"; exit 1; }

echo '--- anthropic /v1/messages（deepseek-flash，一次真实调用）---'
BODY='{"model":"deepseek-flash","max_tokens":32,"messages":[{"role":"user","content":"只回四个字：文本服务在线"}]}'
OUT="$(curl -sS -m 90 https://api.deepseek.com/anthropic/v1/messages \
  -H "x-api-key: $KEY" -H 'anthropic-version: 2023-06-01' -H 'content-type: application/json' \
  -d "$BODY")" || { echo "  调用失败"; exit 1; }
echo "$OUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
if "error" in d: print("  ERROR:", d["error"]); sys.exit(1)
txt="".join(b.get("text","") for b in d.get("content",[]))
print("  model=", d.get("model"), "stop=", d.get("stop_reason"), "usage=", d.get("usage"))
print("  回答=", txt.strip() or "(无 text 块，可能全是 thinking)")
' || exit 1
echo "probe: OK"

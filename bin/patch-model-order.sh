#!/usr/bin/env bash
# 让「智谱 GLM」（llm-pi-ai 路由 zai-coding-cn）在 DSH 模型选择器里排到**最顶部第一个**。
#
# 为什么要打这个补丁（2026-10-12，DSH 0.2.0-rc.2 实测）：
#   输入框最下面那个模型选择器的**分组顺序**由
#     <dsh-安装目录>/node_modules/@deepseek-ai/dsh-client-ui-model-selection/lib/client.js
#   里的 orderModelProviders() 决定，它把 deepseek-account / deepseek-official 硬编码为 0/1，
#   其余提供商一律 2 ⇒ 不补丁的话 GLM 只能排在 DeepSeek 下面，与甲方「GLM 放最顶部第一个」冲突。
#   该函数被选择器菜单和命令面板（optionsOf）共用 ⇒ 补一处，两处都生效。
#   （组内模型顺序另由 rankByName 决定；空查询时保持 Host 目录顺序。）
#
# 用法：
#   bash bin/patch-model-order.sh check     # 只看状态（不带参数时的默认动作）
#   bash bin/patch-model-order.sh apply     # 打补丁（幂等；首次会留 .orig-dsh 原档）
#   bash bin/patch-model-order.sh revert    # 用 .orig-dsh 回滚
#
# ⚠ npm 升级/重装 @deepseek-ai/dsh 会覆盖 client.js ⇒ 升级后重跑 apply（check 会报 missing）。
# ⚠ 补丁只改浏览器侧排序，与服务端路由注册无关；GLM 路由本身由 profile 的 llm-pi-ai 段提供。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

MODE="${1:-check}"
PKG_DIR="${DSH_PKG_DIR:-$HOME/toolchain/node/lib/node_modules/@deepseek-ai/dsh}"
TARGET="$PKG_DIR/node_modules/@deepseek-ai/dsh-client-ui-model-selection/lib/client.js"
ORIG="$TARGET.orig-dsh"

# 原串 / 补丁串（必须与文件里的字节完全一致；改 DSH 版本后先跑 check）
ORIG_SNIPPET='(left.id === "deepseek-account" ? 0 : left.id === "deepseek-official" ? 1 : 2) - (right.id === "deepseek-account" ? 0 : right.id === "deepseek-official" ? 1 : 2)'
PATCHED_SNIPPET='(left.id === "zai-coding-cn" ? 0 : left.id === "deepseek-account" ? 1 : left.id === "deepseek-official" ? 2 : 3) - (right.id === "zai-coding-cn" ? 0 : right.id === "deepseek-account" ? 1 : right.id === "deepseek-official" ? 2 : 3)'
ORIG_DOC='* Put the account and official providers first, preserving every other relative order.'
PATCHED_DOC='* Put the GLM route (zai-coding-cn) first, then the account and official providers, preserving every other relative order.'

if [ ! -f "$TARGET" ]; then
  echo "patch-model-order: 找不到目标文件：$TARGET" >&2
  echo "__PATCH__ missing"
  exit 1
fi

python3 - "$TARGET" "$ORIG" "$MODE" "$ORIG_SNIPPET" "$PATCHED_SNIPPET" "$ORIG_DOC" "$PATCHED_DOC" <<'PY'
import shutil, sys, os

target, orig, mode, old, new, old_doc, new_doc = sys.argv[1:8]
text = open(target, encoding="utf-8").read()
applied = text.count(new)
pristine = text.count(old)
state = "applied" if applied == 1 and pristine == 0 else "pristine" if pristine == 1 and applied == 0 else "unknown"

def report(state_name, code):
    print(f"__PATCH__ {state_name} target={target}")
    sys.exit(code)

if mode == "check":
    report(state, 0 if state in ("applied", "pristine") else 1)

if mode == "revert":
    if not os.path.exists(orig):
        print("patch-model-order: 没有 .orig-dsh 原档，无法回滚", file=sys.stderr)
        report("no-backup", 1)
    shutil.copyfile(orig, target)
    back = open(target, encoding="utf-8").read()
    report("pristine" if back.count(old) == 1 and back.count(new) == 0 else "unknown", 0)

if mode != "apply":
    print(f"patch-model-order: 未知动作 {mode!r}（用 check|apply|revert）", file=sys.stderr)
    report("unknown-mode", 2)

if state == "applied":
    report("applied", 0)
if state != "pristine":
    print("patch-model-order: client.js 与预期不符（DSH 可能已升级/改版）——未改动", file=sys.stderr)
    report("mismatch", 1)

if not os.path.exists(orig):
    shutil.copyfile(target, orig)
    os.chmod(orig, 0o644)
patched = text.replace(old, new, 1).replace(old_doc, new_doc, 1)
open(target, "w", encoding="utf-8").write(patched)
verify = open(target, encoding="utf-8").read()
report("applied" if verify.count(new) == 1 else "failed", 0 if verify.count(new) == 1 else 1)
PY
rc=$?
exit "$rc"

#!/usr/bin/env bash
# 把本仓 profile/ 落地到 $DSH_HOME/profiles/vps（幂等）。
#
#   bash bin/apply-profile.sh              # 落地 profile（缺则先从 web 模板初始化）
#   bash bin/apply-profile.sh --force      # 同时覆盖已存在的 $DSH_HOME/AGENTS.md（全局记忆）
#   bash bin/apply-profile.sh --from-template  # 用 DSH 自带模板重置 package.json（升级 DSH 后用）
#
# 落地的东西：
#   1) $DSH_HOME/profiles/vps/            ← package.json（插件/束注册表）+ cordis.patch.yml（模型路由）
#   2) $DSH_HOME/AGENTS.md                ← profile/AGENTS.md（服务器侧全局长期记忆；已存在则不覆盖）
#   3) $DSH_HOME/.credentials.yaml        ← 只在缺失时创建空骨架（**密钥由人填，脚本不写密钥**）
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
PROFILE="${DSH_PROFILE:-vps}"
PDIR="$DSH_HOME/profiles/$PROFILE"
FORCE=0
FROM_TEMPLATE=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --from-template) FROM_TEMPLATE=1 ;;
  esac
done

mkdir -p "$DSH_HOME/profiles"

# 1) 首次：从 DSH 自带的 web 模板初始化自定义 profile
if [ ! -f "$PDIR/package.json" ]; then
  echo "[apply] 初始化 profile '$PROFILE'（模板 web）"
  ( cd "$ROOT" && dsh "$PROFILE" --from-default-profile web --dump-config >/dev/null 2>&1 ) || true
fi
if [ ! -f "$PDIR/package.json" ]; then
  echo "[apply] 启动器未建出 profile，退回整目录复制 web"
  rm -rf "$PDIR"
  cp -a "$DSH_HOME/profiles/web" "$PDIR"
  sed -i "s/dsh-profile-web/dsh-profile-$PROFILE/" "$PDIR/package.json"
fi

# 2) 注册表：默认用仓库权威副本；--from-template 则保留模板新值
if [ "$FROM_TEMPLATE" = "1" ]; then
  echo "[apply] 保留模板 package.json（--from-template）"
else
  cp -f "$ROOT/profile/package.json" "$PDIR/package.json"
fi

# 3) 用户 patch 层：仓库权威副本覆盖（先备份）
[ -f "$PDIR/cordis.patch.yml" ] && cp -f "$PDIR/cordis.patch.yml" "$PDIR/cordis.patch.yml.bak-$(date +%s)"
cp -f "$ROOT/profile/cordis.patch.yml" "$PDIR/cordis.patch.yml"

# 4) 全局长期记忆
if [ "$FORCE" = "1" ] || [ ! -f "$DSH_HOME/AGENTS.md" ]; then
  cp -f "$ROOT/profile/AGENTS.md" "$DSH_HOME/AGENTS.md"
  echo "[apply] 装了 $DSH_HOME/AGENTS.md"
else
  echo "[apply] 已有 $DSH_HOME/AGENTS.md，跳过（要覆盖加 --force）"
fi

# 5) 凭据骨架：只建不覆盖，也从不在日志里打印密钥
if [ ! -f "$DSH_HOME/.credentials.yaml" ]; then
  umask 077
  cat > "$DSH_HOME/.credentials.yaml" <<'EOF'
version: 1
records: {}
refs:
  # 服务器上的文本服务密钥（DeepSeek 官方 API）。填法：
  #   refs:
  #     DEEPSEEK_API_KEY: sk-...
  # 或 export DEEPSEEK_API_KEY=... 后再起 DSH（启动环境变量优先）。
EOF
  chmod 600 "$DSH_HOME/.credentials.yaml"
  echo "[apply] 建了凭据骨架 $DSH_HOME/.credentials.yaml（请填 DEEPSEEK_API_KEY）"
fi

echo "[apply] done: profile=$PDIR"
echo "[apply] 生效：cd $ROOT && bash bin/web.sh restart"

#!/usr/bin/env bash
# 把服务器上已有的小说业务仓软链进本工作区的 novels/（不复制、不搬动原仓）。
#   bash bin/link-novels.sh
# 约定：novels/<slug>/ 就是一部小说；<slug> 来自仓名去掉 shortstory. 前缀与 .shortstory.d 后缀。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$HERE/env.sh"

ROOT="$DSH_VPS_ROOT"
mkdir -p "$ROOT/novels"
shopt -s nullglob
found=0
for d in "$HOME"/shortstory-workshop.d/*.shortstory.d "$HOME"/*.shortstory.d; do
  [ -d "$d" ] || continue
  base="$(basename "$d")"
  slug="${base%.shortstory.d}"
  slug="${slug#shortstory.}"
  ln -sfn "$d" "$ROOT/novels/$slug"
  echo "[link] novels/$slug -> $d"
  found=$((found + 1))
done
shopt -u nullglob
[ "$found" -gt 0 ] || echo "[link] 没找到 *.shortstory.d 小说仓（$HOME/shortstory-workshop.d/），只在 novels/ 里自建新仓即可"
ls -la "$ROOT/novels"

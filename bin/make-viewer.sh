#!/usr/bin/env bash
# make-viewer.sh —— 把 glTF(.glb) + web 模板 + three.js 打成一个**自包含、双击就能开**的查看器
#
# 用法: bin/make-viewer.sh <room.glb> <输出目录> [web 资产目录]
#   例: bin/make-viewer.sh /path/room.glb /home/longxia/helloworld-blender-roomgen.d/web
#
# 为什么要把 glb **内嵌成 base64**：
#   双击 HTML 时页面是 file:// 协议，浏览器会拦掉 fetch/XHR 读本地文件（CORS），
#   GLTFLoader 就报 "Cross origin requests are only supported for http/https"。
#   内嵌后没有任何外部请求 ⇒ file:// 直接能开，不需要起服务器。
#   同时保留一个走 URL 的 viewer.html，供以后用 http 服务时用（体积小、glb 可换）。
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
GLB=${1:?用法: $0 <room.glb> <输出目录> [web 资产目录]}
OUTDIR=${2:?}
WEB=${3:-$ROOT/tools/roomgen/web}
TPL=${TPL:-$ROOT/tools/roomgen/web/viewer-template.html}

[ -f "$GLB" ] || { echo "找不到 glb: $GLB" >&2; exit 1; }
[ -f "$TPL" ] || { echo "找不到模板: $TPL" >&2; exit 1; }

mkdir -p "$OUTDIR/vendor/jsm/loaders" "$OUTDIR/vendor/jsm/controls" "$OUTDIR/vendor/jsm/utils"
VSRC=${THREE_SRC:-/home/longxia/media-shared/_dl/three/vendor}
for f in three.module.js jsm/loaders/GLTFLoader.js jsm/controls/OrbitControls.js jsm/utils/BufferGeometryUtils.js; do
  [ -f "$VSRC/$f" ] || { echo "[make-viewer] ❌ 缺 three.js 资产 $VSRC/$f" >&2; exit 1; }
  cp -f "$VSRC/$f" "$OUTDIR/vendor/$f"
done

python3 - "$GLB" "$TPL" "$OUTDIR" <<'PY'
import base64, os, sys
glb, tpl, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
b64 = base64.b64encode(open(glb, 'rb').read()).decode()
t = open(tpl, encoding='utf-8').read()
assert '__GLB_BASE64__' in t and '__GLB_URL__' in t, '模板缺占位符'

# 自包含版（双击可用）
self = t.replace('__GLB_BASE64__', b64).replace('__GLB_URL__', os.path.basename(glb))
p1 = os.path.join(outdir, 'viewer-hello.html')
open(p1, 'w', encoding='utf-8').write(self)
# URL 版（需要 http 打开；glb 放 ../out/hello/）
urlv = t.replace('__GLB_BASE64__', '').replace('__GLB_URL__', '../out/hello/' + os.path.basename(glb))
p2 = os.path.join(outdir, 'viewer.html')
open(p2, 'w', encoding='utf-8').write(urlv)
print("[make-viewer] %s  (%.1f KB, glb 内嵌 %.1f KB)" % (p1, os.path.getsize(p1)/1024, os.path.getsize(glb)/1024))
print("[make-viewer] %s  (%.1f KB, 走 URL)" % (p2, os.path.getsize(p2)/1024))
PY
du -sh "$OUTDIR" | awk '{print "[make-viewer] 目录合计 " $1}'

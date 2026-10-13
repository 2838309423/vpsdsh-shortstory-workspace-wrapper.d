#!/usr/bin/env bash
# push-payload.sh -- run ON usavps: push the render payload to an AutoDL instance and provision it.
#
# Usage:
#   bash push-payload.sh --host connect.nmb1.seetacloud.com --port 10309 \
#        [--key ~/.ssh/id_ed25519] [--with-blender] [--blender-tar /home/longxia/media-shared/_dl/blender-4.5.14-linux-x64.tar.xz] \
#        [--jobdir /path/to/job] [--skip-selftest] [--dry-run]
#
# Prereq (once): paste usavps' public key into AutoDL console -> 设置 -> SSH 公钥:
#   cat ~/.ssh/id_ed25519.pub
set -u

HOST=""; PORT=""; KEY="$HOME/.ssh/id_ed25519"; WITH_BLENDER=0
BTAR="/home/longxia/media-shared/_dl/blender-4.5.14-linux-x64.tar.xz"
JOBDIR=""; SKIP_ST="0"; DRY="0"
HERE="$(cd "$(dirname "$0")" && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift ;;
    --port) PORT="${2:-}"; shift ;;
    --key) KEY="${2:-}"; shift ;;
    --with-blender) WITH_BLENDER=1 ;;
    --blender-tar) BTAR="${2:-}"; shift ;;
    --jobdir) JOBDIR="${2:-}"; shift ;;
    --skip-selftest) SKIP_ST=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$HOST" ] && [ -n "$PORT" ] || { echo "FATAL: --host and --port are required" >&2; exit 2; }
[ -f "$KEY" ] || { echo "FATAL: private key not found: $KEY" >&2; exit 2; }

SSH=(ssh -i "$KEY" -p "$PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 "root@$HOST")
SCP=(scp -i "$KEY" -P "$PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
say() { printf '[push] %s\n' "$*"; }

say "target root@$HOST:$PORT  (key $KEY)"
"${SSH[@]}" 'echo "[push] remote: $(hostname) $(uname -r)"; nproc; free -g | head -2; df -h / /root/autodl-tmp 2>/dev/null | tail -3' || {
  echo "FATAL: ssh failed -- is the instance powered on, and is this key registered in the AutoDL console?" >&2; exit 3; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar -czf "$TMP/autodl-payload.tar.gz" -C "$HERE" .
say "payload: $(stat -c%s "$TMP/autodl-payload.tar.gz") bytes"

if [ "$DRY" = "1" ]; then say "dry-run: stopping before any transfer"; exit 0; fi

"${SSH[@]}" 'mkdir -p /root/_dl /root/vibe-render /root/autodl-tmp/jobs'
"${SCP[@]}" "$TMP/autodl-payload.tar.gz" "root@$HOST:/root/_dl/autodl-payload.tar.gz"

if [ "$WITH_BLENDER" = "1" ]; then
  [ -f "$BTAR" ] || { echo "FATAL: --with-blender but tarball missing: $BTAR" >&2; exit 2; }
  say "pushing Blender tarball ($(stat -c%s "$BTAR") bytes) -- this is the slow step from the US"
  "${SCP[@]}" "$BTAR" "root@$HOST:/root/_dl/$(basename "$BTAR")"
fi

REMOTE_TAR=""
[ "$WITH_BLENDER" = "1" ] && REMOTE_TAR="--tarball /root/_dl/$(basename "$BTAR")"

"${SSH[@]}" "set -e
  tar -xzf /root/_dl/autodl-payload.tar.gz -C /root/vibe-render
  chmod +x /root/vibe-render/*.sh
  ls -l /root/vibe-render
  if [ ! -x /opt/blender-4.5.14-linux-x64/blender ]; then
    echo '--- bootstrap ---'
    bash /root/vibe-render/bootstrap.sh $REMOTE_TAR
  else
    bash /root/vibe-render/bootstrap.sh --check
  fi"

if [ -n "$JOBDIR" ]; then
  [ -d "$JOBDIR" ] || { echo "FATAL: --jobdir not a directory: $JOBDIR" >&2; exit 2; }
  JOB="$(basename "$JOBDIR")"
  say "pushing job dir -> /root/autodl-tmp/jobs/$JOB"
  rsync -az --partial -e "ssh -i $KEY -p $PORT -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
        "$JOBDIR/" "root@$HOST:/root/autodl-tmp/jobs/$JOB/"
fi

if [ "$SKIP_ST" != "1" ]; then
  say "--- selftest (no GPU needed) ---"
  "${SSH[@]}" 'bash /root/vibe-render/selftest.sh' || say "selftest reported failures (see above)"
fi
say "done. next: 控制台 -> 关机 -> 更多操作 -> 保存镜像"

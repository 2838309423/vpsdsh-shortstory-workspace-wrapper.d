#!/usr/bin/env bash
# win10-exec.sh —— 在 usavps win10 KVM 客机里执行命令（走 qemu-guest-agent 的 guest-exec）
#
# 用法：
#   bin/win10-exec.sh <exe> [args...]              # 例：bin/win10-exec.sh cmd.exe /c ver
#   bin/win10-exec.sh --timeout 1800 cmd.exe /c ...# 长任务（默认 300 s）
#   echo '...' | bin/win10-exec.sh --stdin-file /tmp/x.bat   # 需要喂 stdin 的场景请改用文件
#
# 事实与坑（2026-10-11 实测）：
#   * guest-exec 以 **SYSTEM / session 0** 身份跑 ⇒ 无桌面、无 GUI，适合 `blender -b`。
#   * 客机 cmd.exe 控制台是 **cp936(GBK)** ⇒ 本脚本按 GBK 解码；UTF-8 程序（Blender）请把输出
#     重定向到文件（放到 \\shared ⇄ /home/longxia/media-shared）再从宿主按 UTF-8 读。
#   * guest-exec 的输出是 base64 回传，**大输出会截断** ⇒ 长任务一律重定向到文件。
#   * guest-exec 只要 pid 拿到手，宿主侧就算断了客机也会跑完；本脚本只负责轮询等它结束。
set -uo pipefail

URI=${WIN10_URI:-qemu:///system}
DOM=${WIN10_DOM:-win10}
TIMEOUT=${WIN10_EXEC_TIMEOUT:-300}
ENC=${WIN10_EXEC_ENC:-gbk}
PIDFILE=${WIN10_EXEC_PIDFILE:-$HOME/.cache/win10-exec-lastpid}

# ⚠ 宿主侧 Ctrl-C / 杀进程 **不会**停掉客机里已经在跑的程序（guest-exec 是发射后不管）。
#    要停就用这个：bin/win10-exec.sh --kill-last  ⇒ 对上一次的 pid 做 taskkill /T /F。
if [ "${1:-}" = "--kill-last" ]; then
  p=$(cat "$PIDFILE" 2>/dev/null || true)
  [ -n "$p" ] || { echo "没记录到上次的客机 pid（$PIDFILE）" >&2; exit 1; }
  echo "taskkill 客机 pid=$p（连同子进程）"
  exec bash "$0" cmd.exe /c "taskkill /PID $p /T /F"
  exit $?
fi

if [ "${1:-}" = "--timeout" ]; then TIMEOUT=$2; shift 2; fi
if [ "${1:-}" = "--enc" ]; then ENC=$2; shift 2; fi
if [ $# -eq 0 ]; then echo "用法: $0 [--timeout N] [--enc gbk|utf-8] <exe> [args...] | --kill-last" >&2; exit 2; fi

WIN10_EXEC_URI=$URI WIN10_EXEC_DOM=$DOM WIN10_EXEC_TIMEOUT=$TIMEOUT WIN10_EXEC_ENC=$ENC \
WIN10_EXEC_PIDFILE=$PIDFILE \
python3 - "$@" <<'PY'
import base64, json, os, subprocess, sys, time

URI = os.environ["WIN10_EXEC_URI"]; DOM = os.environ["WIN10_EXEC_DOM"]
TIMEOUT = float(os.environ["WIN10_EXEC_TIMEOUT"]); ENC = os.environ["WIN10_EXEC_ENC"]
PIDFILE = os.environ["WIN10_EXEC_PIDFILE"]
exe, args = sys.argv[1], sys.argv[2:]

def agent(obj):
    p = subprocess.run(["virsh", "-c", URI, "qemu-agent-command", DOM, json.dumps(obj)],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        sys.exit("guest-agent 调用失败: " + (p.stderr or p.stdout).strip())
    return json.loads(p.stdout)

req = {"execute": "guest-exec",
       "arguments": {"path": exe, "arg": args, "capture-output": True}}
r = agent(req).get("return", {})
pid = r.get("pid")
if not pid:
    sys.exit("guest-exec 没返回 pid: " + json.dumps(r))
try:
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, "w") as f:
        f.write(str(pid))
except OSError:
    pass
t0 = time.time(); st = None
while time.time() - t0 < TIMEOUT:
    st = agent({"execute": "guest-exec-status", "arguments": {"pid": pid}}).get("return", {})
    if st.get("exited"):
        break
    time.sleep(0.4)
else:
    sys.stderr.write("[win10-exec] %ss 未结束（客机里仍在跑，pid=%s）\n" % (TIMEOUT, pid))
    sys.exit(124)

out = base64.b64decode(st.get("out-data") or b"")
err = base64.b64decode(st.get("err-data") or b"")
sys.stdout.write(out.decode(ENC, "replace"))
if err:
    sys.stderr.write(err.decode(ENC, "replace"))
sys.stdout.write("\n[win10-exec] exit=%s elapsed=%.1fs\n" % (st.get("exitcode"), time.time() - t0))
sys.exit(0 if st.get("exitcode") == 0 else 1)
PY

#!/usr/bin/env python3
"""入口鉴权门：给 `dsh web` 当 Tailscale 门面，顺带管"怎么进得来"这件事。

为什么还需要它：`@deepseek-ai/dsh-host-webserver` 只肯绑 `127.0.0.1`/`0.0.0.0`，而 `dsh web`
自带的入口令牌**每次启动都换** ⇒ 手机里存的书签过一阵就 401。这是 `bin/ts-proxy.py` 的升级版：
同一个监听、同一套直通语义，但多认几种"进门方式"。

三种模式（写在 `state/gate.conf` 的 `mode = ...`，**每条连接现读**，改完即生效、不用重启）：

  off       纯 TCP 转发，行为与本来的 ts-proxy.py 完全一致（回滚档）
  tailnet   方案①：**Tailscale 网内即通行**。浏览器开干净 URL `http://100.85.190.17:19387/`，
            门发现 DSH 回 401（没 cookie）就自动补一次 `/?token=<当前令牌>` 跳转 ⇒ 永久书签，重启也不怕。
  password  方案②：在 ① 之上加一道**真·Linux 口令**登录页。只认 `longxia` / `shortstory`
            （`root` 永不在白名单里），口令校验直接走系统：
              longxia    : `sudo -S -k -u root /bin/true`（PAM 校验发起者口令；实测错口令 ⇒ EXIT=1）
              shortstory : `su shortstory -c /bin/true`（起了 PTY 喂口令；实测错口令 ⇒ Authentication failure）
            通过后发一枚 HMAC 签名的 `dsh-gate` cookie（默认 365 天），之后才轮到 DSH 自己的认证。

⚠ 这是**身份门**，不是权限边界：web 里跑的一切仍然以服务账号 `longxia` 身份执行，
  用 `shortstory` 登录并不会让 agent 变成 shortstory。要真分权限得另起一个 DSH 实例换 uid 跑。
⚠ 口令只经 stdin / PTY 传，绝不落日志、绝不进 argv。

用法：
    python3 web-gate.py --listen-host 100.85.190.17 --listen-port 19387 \
                        --target-host 127.0.0.1 --target-port 19387 \
                        --state-dir /home/longxia/vpsdsh-shortstory-workspace-wrapper.d/state
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import functools
import hashlib
import hmac
import json
import os
import re
import select
import subprocess
import sys
import time
import urllib.parse

MAX_HEAD = 32 * 1024
MAX_FORM = 8 * 1024
GATE_COOKIE = "dsh-gate"
ALLOWED_USERS = ("longxia", "shortstory")  # root 永不入列
MODE_OFF, MODE_TAILNET, MODE_PASSWORD = "off", "tailnet", "password"
MODES = (MODE_OFF, MODE_TAILNET, MODE_PASSWORD)
DEFAULT_MODE = MODE_TAILNET
COOKIE_TTL_SECONDS = 365 * 24 * 3600
FAIL_LIMIT = 5
FAIL_WINDOW_SECONDS = 300
CONFIG_CACHE_SECONDS = 2.0

STATE_DIR = "."
FAILS: dict[str, list[float]] = {}
_CACHE: dict[str, tuple[float, object]] = {}


def log(msg: str) -> None:
    print(f"[web-gate] {time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}", flush=True)


# --------------------------------------------------------------------------- 状态文件

def _cached(key: str, producer, ttl: float):
    now = time.time()
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _CACHE[key] = (now, value)
    return value


def read_mode() -> str:
    def produce() -> str:
        path = os.path.join(STATE_DIR, "gate.conf")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.split("#", 1)[0].strip()
                    if not line or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    if key.strip() == "mode":
                        value = value.strip().lower()
                        if value in MODES:
                            return value
                        log(f"gate.conf 里的 mode={value!r} 不认识，退回 {DEFAULT_MODE}")
        except FileNotFoundError:
            pass
        except OSError as exc:
            log(f"读 gate.conf 失败（{exc}），退回 {DEFAULT_MODE}")
        return DEFAULT_MODE

    return _cached("mode", produce, CONFIG_CACHE_SECONDS)  # type: ignore[return-value]


def current_token() -> str | None:
    """当前 `dsh web` 的入口令牌：先看 web.sh 校准过的 url.txt，再退回 web.log 日志尾。"""
    pattern = re.compile(r"token=([A-Za-z0-9_-]{16,})")

    def produce() -> str | None:
        for path, whole in ((os.path.join(STATE_DIR, "url.txt"), False),
                            (os.path.join(STATE_DIR, "web.log"), True)):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            found = pattern.findall(text)
            if found:
                return found[-1] if whole else found[0]
        return None

    return _cached("token", produce, CONFIG_CACHE_SECONDS)  # type: ignore[return-value]


def gate_secret() -> bytes:
    def produce() -> bytes:
        path = os.path.join(STATE_DIR, "gate-secret.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
            if raw:
                return raw.encode()
        except OSError:
            pass
        secret = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        os.makedirs(STATE_DIR, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(secret + "\n")
        log(f"首次生成入口门签名密钥 {path}（600）")
        return secret.encode()

    return _cached("secret", produce, 3600.0)  # type: ignore[return-value]


# --------------------------------------------------------------------------- cookie

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]*", text) or len(text) % 4 == 1:
        return None
    pad = "=" * ((4 - len(text) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except Exception:  # noqa: BLE001
        return None


def make_gate_cookie(user: str) -> str:
    payload = _b64e(json.dumps({"u": user, "exp": int(time.time()) + COOKIE_TTL_SECONDS},
                               separators=(",", ":")).encode())
    sig = _b64e(hmac.new(gate_secret(), payload.encode(), hashlib.sha256).digest())
    return f"v1.{payload}.{sig}"


def cookie_user(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    raw = None
    for segment in cookie_header.split(";"):
        name, _, value = segment.strip().partition("=")
        if name == GATE_COOKIE:
            raw = value
    if not raw or not raw.startswith("v1."):
        return None
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    payload, sig = parts[1], parts[2]
    expected = _b64e(hmac.new(gate_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    body = _b64d(payload)
    if body is None:
        return None
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict) or data.get("u") not in ALLOWED_USERS:
        return None
    if not isinstance(data.get("exp"), int) or data["exp"] <= time.time():
        return None
    return str(data["u"])


# --------------------------------------------------------------------------- 口令校验

def verify_linux_password(user: str, password: str) -> bool:
    """用系统自己的 PAM 栈校验；只认白名单用户，root 连试都不试。"""
    if user not in ALLOWED_USERS or not password:
        return False
    if user == "longxia":
        return _verify_via_sudo(password)
    return _verify_via_su(user, password)


def _verify_via_sudo(password: str) -> bool:
    """`sudo -S -k -u root /bin/true`：sudo 校验的是**发起者 longxia** 的口令（实测错口令 EXIT=1）。"""
    env = dict(os.environ, LC_ALL="C")
    try:
        proc = subprocess.run(
            ["sudo", "-S", "-k", "-u", "root", "/bin/true"],
            input=password + "\n", text=True, capture_output=True, timeout=25, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"sudo 校验不可用：{exc}")
        return False
    return proc.returncode == 0


def _verify_via_su(user: str, password: str) -> bool:
    """`su <user> -c /bin/true`：su 是 setuid root，长xia 也能替自己以外的用户校验口令。"""
    try:
        pid, fd = os.forkpty()
    except OSError as exc:
        log(f"forkpty 失败：{exc}")
        return False
    if pid == 0:  # 子进程：立刻换成 su
        try:
            os.execvp("su", ["su", user, "-c", "/bin/true"])
        finally:
            os._exit(127)
    sent = False
    buf = b""
    deadline = time.time() + 25
    status = None
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.3)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if not sent and b"assword" in buf:
                    os.write(fd, (password + "\n").encode())
                    sent = True
            done, st = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                status = st
                break
        if status is None:
            os.waitpid(pid, 0)
            return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


# --------------------------------------------------------------------------- 限速

def _client_ip(writer: asyncio.StreamWriter) -> str:
    peer = writer.get_extra_info("peername")
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return "?"


def rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in FAILS.get(ip, []) if now - t < FAIL_WINDOW_SECONDS]
    FAILS[ip] = hits
    return len(hits) >= FAIL_LIMIT


def note_failure(ip: str) -> None:
    FAILS.setdefault(ip, []).append(time.time())


def note_success(ip: str) -> None:
    FAILS.pop(ip, None)


# --------------------------------------------------------------------------- HTTP 小工具

def _respond(writer: asyncio.StreamWriter, status: int, body: bytes = b"",
             headers: dict[str, str] | None = None, close: bool = True) -> None:
    lines = [f"HTTP/1.1 {status} {_reason(status)}", "cache-control: no-store",
             "referrer-policy: no-referrer"]
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    if body:
        lines.append(f"content-length: {len(body)}")
    lines.append("connection: close" if close else "connection: keep-alive")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode() + body)


def _reason(status: int) -> str:
    return {200: "OK", 303: "See Other", 400: "Bad Request", 401: "Unauthorized",
            403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
            413: "Payload Too Large", 429: "Too Many Requests",
            503: "Service Unavailable"}.get(status, "OK")


async def _read_head(reader: asyncio.StreamReader) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(4096)
        if not chunk:
            return buf
        buf += chunk
        if len(buf) > MAX_HEAD:
            raise ValueError("请求头过大")
    return buf


class Request:
    __slots__ = ("method", "target", "path", "query", "headers", "head", "body_prefix")

    def __init__(self, head: bytes) -> None:
        self.head = head
        try:
            # ⚠ _read_head 一次读 4 KB 再找 CRLFCRLF ⇒ 首包里可能**连带**装进了 body 的开头，
            #   那部分必须留在 body_prefix 里交给需要读 body 的地方（登录表单），否则会傻等。
            head_part, _, self.body_prefix = head.partition(b"\r\n\r\n")
            text = head_part.decode("iso-8859-1")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("请求头解码失败") from exc
        lines = text.split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) < 2:
            raise ValueError("请求行不合法")
        self.method = parts[0].upper()
        self.target = parts[1]
        self.headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            self.headers[name.strip().lower()] = value.strip()
        split = urllib.parse.urlsplit(self.target)
        self.path = split.path or "/"
        self.query = urllib.parse.parse_qs(split.query)

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def with_connection_close(self) -> bytes:
        # ⚠ self.head 可能**连带**装进了首包里的 body 字节（_read_head 是一次读 4 KB 再找 CRLFCRLF），
        #   那些字节一个都不能丢：只在 CRLFCRLF 之前的头里替换 connection。
        head, sep, rest = self.head.partition(b"\r\n\r\n")
        kept = [line for line in head.split(b"\r\n")
                if not line.lower().startswith(b"connection:")]
        kept.append(b"connection: close")
        return b"\r\n".join(kept) + sep + rest


# --------------------------------------------------------------------------- 页面

LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DSH 入口登录</title>
<style>
 :root{color-scheme:light dark}
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
      font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC",sans-serif;
      background:#f5f6f8;color:#1c1e21}
 form{width:min(88vw,360px);background:#fff;border-radius:14px;padding:28px 24px;
      box-shadow:0 8px 30px rgba(0,0,0,.10)}
 h1{margin:0 0 4px;font-size:20px}
 p.sub{margin:0 0 20px;color:#6b7280;font-size:13px}
 input{width:100%;box-sizing:border-box;padding:12px 14px;margin-bottom:12px;font-size:16px;
       border:1px solid #d1d5db;border-radius:10px;background:#fff;color:inherit}
 button{width:100%;padding:12px;font-size:16px;border:0;border-radius:10px;background:#2563eb;
        color:#fff;cursor:pointer}
 button:active{background:#1d4ed8}
 .err{color:#b91c1c;font-size:14px;margin:0 0 12px}
 .hint{color:#6b7280;font-size:12px;margin:14px 0 0}
</style></head><body>
<form method="post" action="/login">
  <h1>DSH 入口</h1>
  <p class="sub">Tailscale 网内 · 系统账户登录</p>
  __ERROR__
  <input name="username" placeholder="用户名" autocomplete="username" autocapitalize="none" autofocus>
  <input name="password" type="password" placeholder="口令" autocomplete="current-password">
  <button type="submit">登录</button>
  <p class="hint">只允许 longxia / shortstory；root 不可登录。口令即本机 Linux 账户口令。</p>
</form></body></html>
"""


def login_page(error: str = "") -> bytes:
    block = f'  <p class="err">{error}</p>\n' if error else ""
    return LOGIN_PAGE.replace("__ERROR__", block).encode()


# --------------------------------------------------------------------------- 主处理

async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:  # noqa: BLE001
            pass


async def _forward_raw(head: bytes, reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter, target: tuple[str, int]) -> None:
    try:
        up_r, up_w = await asyncio.open_connection(*target)
    except OSError as exc:
        log(f"连接上游 {target[0]}:{target[1]} 失败：{exc}")
        writer.close()
        return
    up_w.write(head)
    try:
        await up_w.drain()
    except OSError:
        pass
    await asyncio.gather(_pipe(reader, up_w), _pipe(up_r, writer))


async def _document(head: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                    request: Request, target: tuple[str, int]) -> None:
    """文档请求单独走一次完整交换：上游 401（没 cookie）就补一次 /?token=<当前令牌>。"""
    try:
        up_r, up_w = await asyncio.open_connection(*target)
    except OSError as exc:
        log(f"连接上游 {target[0]}:{target[1]} 失败：{exc}")
        _respond(writer, 503, b"upstream unreachable\n")
        writer.close()
        return
    up_w.write(request.with_connection_close() if request.head else head)
    try:
        await up_w.drain()
    except OSError:
        pass
    try:
        resp_head = await asyncio.wait_for(_read_head(up_r), timeout=20)
    except (asyncio.TimeoutError, ValueError, OSError):
        resp_head = b""
    if not resp_head:
        _respond(writer, 503, b"upstream gave no response\n")
        writer.close()
        up_w.close()
        return
    status = 0
    try:
        status = int(resp_head.split(b" ", 2)[1])
    except (IndexError, ValueError):
        status = 0
    if status == 401:
        token = current_token()
        up_w.close()
        if not token:
            log("上游 401 但 state/url.txt 与 web.log 都没有令牌 ⇒ 503（先跑 bin/web.sh start）")
            _respond(writer, 503, b"no launch token on server; run bin/web.sh start\n")
        else:
            log(f"上游 401 ⇒ 303 /?token=…（{request.path}，自动换 cookie）")
            _respond(writer, 303, headers={"location": f"/?token={token}"})
        writer.close()
        return
    writer.write(resp_head)
    await _pipe(up_r, writer)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                  target: tuple[str, int]) -> None:
    ip = _client_ip(writer)
    try:
        head = await asyncio.wait_for(_read_head(reader), timeout=30)
    except (asyncio.TimeoutError, ValueError, OSError):
        writer.close()
        return
    if not head:
        writer.close()
        return
    try:
        request = Request(head)
    except ValueError:
        await _forward_raw(head, reader, writer, target)
        return

    mode = read_mode()
    if mode == MODE_OFF:
        await _forward_raw(head, reader, writer, target)
        return

    path = request.path
    if path == "/logout":
        log(f"{ip} 退出登录")
        _respond(writer, 303, headers={
            "set-cookie": f"{GATE_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
            "location": "/login"})
        writer.close()
        return

    if path == "/login":
        if request.method == "POST":
            await _login(reader, writer, request, ip)
        else:
            _respond(writer, 200, login_page("" if not request.query.get("e") else "用户名或口令不对"),
                     {"content-type": "text/html; charset=utf-8"})
        writer.close()
        return

    user = cookie_user(request.header("cookie"))
    if mode == MODE_PASSWORD and user is None:
        if path.startswith("/api"):
            _respond(writer, 401, b"dsh-gate: login required\n",
                     {"content-type": "text/plain; charset=utf-8"})
        else:
            _respond(writer, 303, headers={"location": "/login"})
        writer.close()
        return

    if request.method in ("GET", "HEAD") and path in ("/", "/index.html"):
        await _document(head, reader, writer, request, target)
        return

    await _forward_raw(head, reader, writer, target)


async def _login(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 request: Request, ip: str) -> None:
    if rate_limited(ip):
        log(f"{ip} 登录被限速（{FAIL_LIMIT} 次/{FAIL_WINDOW_SECONDS}s 内失败）")
        _respond(writer, 429, b"too many failed attempts; wait 5 minutes\n",
                 {"content-type": "text/plain; charset=utf-8", "retry-after": str(FAIL_WINDOW_SECONDS)})
        return
    try:
        length = int(request.header("content-length") or "0")
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_FORM:
        _respond(writer, 400, b"bad form\n")
        return
    try:
        body = request.body_prefix[:length]
        if len(body) < length:
            body += await asyncio.wait_for(reader.readexactly(length - len(body)), timeout=10)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError):
        _respond(writer, 400, b"short body\n")
        return
    form = urllib.parse.parse_qs(body.decode("utf-8", "replace"))
    username = (form.get("username") or [""])[0].strip()
    password = (form.get("password") or [""])[0]
    if any(c in password for c in "\r\n\x00"):
        password = ""
    if username not in ALLOWED_USERS:
        note_failure(ip)
        log(f"{ip} 登录被拒：用户名 {username!r} 不在白名单（root 亦不可）")
        _respond(writer, 303, headers={"location": "/login?e=1"})
        return
    ok = await asyncio.to_thread(verify_linux_password, username, password)
    await asyncio.sleep(0)  # 让事件循环喘口气
    if not ok:
        note_failure(ip)
        log(f"{ip} 登录失败：用户 {username}（系统口令不对）")
        _respond(writer, 303, headers={"location": "/login?e=1"})
        return
    note_success(ip)
    log(f"{ip} 登录成功：{username}")
    _respond(writer, 303, headers={
        "set-cookie": (f"{GATE_COOKIE}={make_gate_cookie(username)}; Path=/; "
                       f"Max-Age={COOKIE_TTL_SECONDS}; HttpOnly; SameSite=Lax"),
        "location": "/"})


async def _serve(listen_host: str, listen_port: int, target: tuple[str, int]) -> None:
    handler = functools.partial(_handle, target=target)
    try:
        server = await asyncio.start_server(handler, listen_host, listen_port)
    except OSError as exc:
        log(f"监听 {listen_host}:{listen_port} 失败：{exc}")
        raise SystemExit(3) from exc
    log(f"listening {listen_host}:{listen_port} -> {target[0]}:{target[1]} mode={read_mode()}")
    async with server:
        await server.serve_forever()


def main() -> None:
    global STATE_DIR
    ap = argparse.ArgumentParser(description="DSH web 入口鉴权门（Tailscale 门面）")
    ap.add_argument("--listen-host", required=True)
    ap.add_argument("--listen-port", type=int, required=True)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, required=True)
    ap.add_argument("--state-dir", default=os.environ.get("DSH_GATE_STATE_DIR", "."))
    args = ap.parse_args()
    STATE_DIR = args.state_dir
    target = (args.target_host, args.target_port)
    try:
        asyncio.run(_serve(args.listen_host, args.listen_port, target))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

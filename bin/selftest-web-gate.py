#!/usr/bin/env python3
"""`bin/web-gate.py` 的自测：假 DSH 上游 + 真门 + 桩口令校验。

跑法：
    python3 bin/selftest-web-gate.py            # 末行 __SELFTEST__ <断言数> <失败数>
    python3 bin/selftest-web-gate.py --verbose  # 连门的日志一起看

覆盖：
  * tailnet 模式：文档 401 ⇒ 303 /?token=<令牌> ⇒ 带 cookie 200；/api 原样直通；
    带 body 的 POST 直通；HEAD 也走同一条路；**拿不到令牌时 503 而不是无限跳转**。
  * password 模式：未登录 ⇒ 303 /login；登录页 200；root/陌生用户名直接拒；
    桩口令 False ⇒ /login?e=1；连错 5 次 ⇒ 429；桩口令 True ⇒ 发 cookie ⇒ 之后能进；
    伪造 cookie ⇒ 退回 /login；/api 无 cookie ⇒ 401。
  * split 模式（域名走令牌档 / IP 走口令档）：域名 Host ⇒ 401⇒303 到令牌、/login 直接回首页；
    IP Host ⇒ 303 /login、登录页 200、/api 401；陌生主机名与 IPv6 字面量 ⇒ 一律口令档（失败安全）；
    任意 *.ts.net ⇒ 令牌档；gate.conf 的 token_host 追加项（含 IP）能覆盖默认分流；
    IP 入口口令对 ⇒ 发 cookie ⇒ 带 cookie 再走令牌跳转；伪造 cookie ⇒ 退回 /login。
  * 真口令校验（不打桩，故意用错口令）：longxia / shortstory 必须判否，且都不落日志。
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VERBOSE = "--verbose" in sys.argv

spec = importlib.util.spec_from_file_location("webgate", os.path.join(HERE, "web-gate.py"))
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)

if not VERBOSE:
    gate.log = lambda _msg: None  # noqa: E731

RESULTS: list[tuple[str, bool, str]] = []
STUB_TOKEN = "STUBTOKEN_" + "x" * 32
DSH_COOKIE = "dsh-auth-stub=v1.stub"


def check(name: str, ok: bool, extra: str = "") -> None:
    RESULTS.append((name, bool(ok), extra))
    if VERBOSE:
        print(f"  {'PASS' if ok else 'FAIL'} {name} {extra}")


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def build(method: str, path: str, headers: dict[str, str] | None = None, body: bytes = b"") -> bytes:
    lines = [f"{method} {path} HTTP/1.1", "host: 127.0.0.1", "accept: */*"]
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    if body:
        lines.append(f"content-length: {len(body)}")
    lines.append("connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


async def call(port: int, raw: bytes) -> tuple[int, dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = b""
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            break
        data += chunk
    writer.close()
    head, _, body = data.partition(b"\r\n\r\n")
    status = 0
    headers: dict[str, str] = {}
    if head:
        first = head.split(b"\r\n")[0]
        parts = first.split(b" ")
        if len(parts) > 1:
            try:
                status = int(parts[1])
            except ValueError:
                status = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            headers[name.strip().lower().decode()] = value.strip().decode()
    return status, headers, body


# --------------------------------------------------------------- 假 DSH 上游

async def _stub_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await asyncio.wait_for(gate._read_head(reader), timeout=10)  # noqa: SLF001
    except (asyncio.TimeoutError, ValueError):
        writer.close()
        return
    # ⚠ _read_head 一次读 4 KB 再找 CRLFCRLF ⇒ 首包里可能已经带上了 body 的一部分，
    #   这里必须把它们接住，否则会傻等 readexactly 永远等不到的字节（自测第一版就栽在这）。
    head_part, _, body = head.partition(b"\r\n\r\n")
    text = head_part.decode("iso-8859-1")
    request_line = text.split("\r\n")[0]
    parts = request_line.split(" ")
    method, target = parts[0], parts[1] if len(parts) > 1 else "/"
    length = 0
    for line in text.split("\r\n")[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except ValueError:
                length = 0
    if length > len(body):
        body += await reader.readexactly(length - len(body))

    status, extra, payload = "200 OK", [], b""
    if target.startswith("/api/echo"):
        status, payload = "200 OK", b"echo:" + str(len(body)).encode()
    elif target.startswith("/api"):
        status, payload = "200 OK", b"api-ok"
    elif f"token={STUB_TOKEN}" in target:
        status, extra, payload = "303 See Other", [f"set-cookie: {DSH_COOKIE}"], b""
    elif DSH_COOKIE.split("=")[0] in text.lower():
        status, payload = "200 OK", b"<html>SPA OK</html>"
    else:
        status, payload = "401 Unauthorized", b"dsh web authentication required\n"

    lines = [f"HTTP/1.1 {status}", f"content-length: {len(payload)}", "connection: close", *extra]
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode() + payload)
    try:
        await writer.drain()
    except OSError:
        pass
    writer.close()


# --------------------------------------------------------------- 各档测试

async def run() -> None:
    tmp = tempfile.mkdtemp(prefix="gate-selftest-")
    gate.STATE_DIR = tmp
    gate.FAILS.clear()
    gate._CACHE.clear()  # noqa: SLF001
    stub_port, gate_port = free_port(), free_port()

    def set_mode(mode: str) -> None:
        set_conf(f"mode = {mode}\n")

    def set_conf(text: str) -> None:
        with open(os.path.join(tmp, "gate.conf"), "w", encoding="utf-8") as fh:
            fh.write(text)
        gate._CACHE.pop("conf", None)  # noqa: SLF001

    def set_token(token: str | None) -> None:
        with open(os.path.join(tmp, "url.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"http://100.85.190.17:19387/?token={token}\n" if token else "no token here\n")
        gate._CACHE.pop("token", None)  # noqa: SLF001

    stub = await asyncio.start_server(_stub_handler, "127.0.0.1", stub_port)
    set_mode("tailnet")
    set_token(STUB_TOKEN)
    import functools
    gate_srv = await asyncio.start_server(
        functools.partial(gate._handle, target=("127.0.0.1", stub_port)),  # noqa: SLF001
        "127.0.0.1", gate_port)
    await asyncio.sleep(0.1)

    # ---- 桩：假 DSH 上游自身的行为先自证（否则后面全是假的） ----
    code, _, _ = await call(stub_port, build("GET", "/"))
    check("假 DSH：无 cookie 文档 ⇒ 401", code == 401, f"code={code}")
    code, hdrs, _ = await call(stub_port, build("GET", f"/?token={STUB_TOKEN}"))
    check("假 DSH：带令牌 ⇒ 303 + set-cookie", code == 303 and "set-cookie" in hdrs, f"code={code}")

    # ---- 模式 off：必须与老 ts-proxy 一样纯直通 ----
    set_mode("off")
    code, _, _ = await call(gate_port, build("GET", "/"))
    check("off 模式：原样直通（401 不被改写）", code == 401, f"code={code}")
    code, _, body = await call(gate_port, build("GET", "/api/x"))
    check("off 模式：/api 直通", code == 200 and body == b"api-ok", f"code={code} body={body!r}")

    # ---- 模式 tailnet ----
    set_mode("tailnet")
    code, hdrs, _ = await call(gate_port, build("GET", "/"))
    check("tailnet：文档 401 ⇒ 303 到当前令牌",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""),
          f"code={code} loc={hdrs.get('location')}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"cookie": DSH_COOKIE}))
    check("tailnet：带 cookie ⇒ 200 出 SPA", code == 200, f"code={code}")
    code, hdrs, _ = await call(gate_port, build("HEAD", "/"))
    check("tailnet：HEAD 也走同一条路", code == 303, f"code={code}")
    code, _, body = await call(gate_port, build("GET", "/api/x"))
    check("tailnet：/api 原样直通", code == 200 and body == b"api-ok", f"code={code}")
    payload = b"y" * 5000
    code, _, body = await call(gate_port, build("POST", "/api/echo", body=payload))
    check("tailnet：带 body 的 POST 直通（5000B 不丢）", code == 200 and body == b"echo:5000",
          f"code={code} body={body!r}")
    set_token(None)
    code, _, _ = await call(gate_port, build("GET", "/"))
    check("tailnet：服务器取不到令牌 ⇒ 503（绝不无限跳转）", code == 503, f"code={code}")
    set_token(STUB_TOKEN)

    # ---- 模式 password ----
    set_mode("password")
    gate.FAILS.clear()
    code, hdrs, _ = await call(gate_port, build("GET", "/"))
    check("password：未登录文档 ⇒ 303 /login",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    code, hdrs, body = await call(gate_port, build("GET", "/login"))
    check("password：登录页 200 且有表单",
          code == 200 and b"<form" in body and "text/html" in hdrs.get("content-type", ""),
          f"code={code}")
    code, _, _ = await call(gate_port, build("GET", "/api/x"))
    check("password：/api 无门 cookie ⇒ 401", code == 401, f"code={code}")

    calls: list[tuple[str, str]] = []

    def fake_verify(user: str, password: str) -> bool:
        calls.append((user, password))
        return password == "right-password"

    real_verify = gate.verify_linux_password
    gate.verify_linux_password = fake_verify  # type: ignore[assignment]

    form = b"username=root&password=right-password"
    code, hdrs, _ = await call(gate_port, build("POST", "/login", body=form))
    check("password：root 直接拒且不触校验", hdrs.get("location") == "/login?e=1" and not calls,
          f"loc={hdrs.get('location')} calls={calls}")
    form = b"username=nobody&password=right-password"
    code, _, _ = await call(gate_port, build("POST", "/login", body=form))
    check("password：陌生用户名直接拒且不触校验", not calls, f"calls={calls}")

    form = b"username=longxia&password=wrong"
    code, hdrs, _ = await call(gate_port, build("POST", "/login", body=form))
    check("password：口令不对 ⇒ /login?e=1",
          hdrs.get("location") == "/login?e=1" and calls == [("longxia", "wrong")],
          f"loc={hdrs.get('location')} calls={calls}")

    for _ in range(gate.FAIL_LIMIT):
        await call(gate_port, build("POST", "/login", body=form))
    code, _, _ = await call(gate_port, build("POST", "/login", body=form))
    check(f"password：连错 {gate.FAIL_LIMIT} 次后 ⇒ 429", code == 429, f"code={code}")
    gate.FAILS.clear()

    form = b"username=longxia&password=right-password"
    code, hdrs, _ = await call(gate_port, build("POST", "/login", body=form))
    cookie = hdrs.get("set-cookie", "").split(";")[0]
    check("password：口令对 ⇒ 303 + 发 dsh-gate cookie",
          code == 303 and cookie.startswith(gate.GATE_COOKIE + "=") and hdrs.get("location") == "/",
          f"code={code} cookie={cookie[:24]}…")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"cookie": cookie}))
    check("password：带门 cookie 的文档 ⇒ 303 到令牌（再换 DSH cookie）",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""),
          f"code={code} loc={hdrs.get('location')}")
    code, _, body = await call(gate_port, build("GET", "/api/x", {"cookie": cookie}))
    check("password：带门 cookie 的 /api ⇒ 直通", code == 200 and body == b"api-ok", f"code={code}")
    forged = gate.GATE_COOKIE + "=v1.eyJ1IjoibG9uZ3hpYSIsImV4cCI6NDEwMjQ0NDgwMH0.Zm9yZ2Vk"
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"cookie": forged}))
    check("password：伪造 cookie ⇒ 退回 /login",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    expired = gate.make_gate_cookie("longxia")
    gate._CACHE["secret"] = (time.time(), b"other-secret")  # noqa: SLF001
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"cookie": gate.GATE_COOKIE + "=" + expired}))
    check("password：换密钥后旧 cookie 失效 ⇒ /login",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    gate._CACHE.pop("secret", None)  # noqa: SLF001
    gate.verify_linux_password = real_verify  # type: ignore[assignment]

    # ---- 模式 split：按 Host 分流（Tailscale 域名 ⇒ 令牌档；IP / 陌生名 ⇒ 口令档） ----
    DOMAIN_HOST = "ser542085963120.tailcd1620.ts.net:19387"
    IP_HOST = "100.85.190.17:19387"
    gate.FAILS.clear()
    set_conf("mode = split\n")

    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": DOMAIN_HOST}))
    check("split：域名 Host ⇒ 令牌档（401⇒303 到当前令牌，不出口令页）",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""),
          f"code={code} loc={hdrs.get('location')}")
    code, hdrs, _ = await call(gate_port, build("GET", "/login", {"host": DOMAIN_HOST}))
    check("split：域名 Host 打 /login ⇒ 303 回首页（这条路本来就不要口令）",
          code == 303 and hdrs.get("location") == "/", f"code={code} loc={hdrs.get('location')}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": IP_HOST}))
    check("split：IP Host ⇒ 口令档（303 /login）",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    code, _, body = await call(gate_port, build("GET", "/login", {"host": IP_HOST}))
    check("split：IP Host 的登录页 200 且有表单", code == 200 and b"<form" in body, f"code={code}")
    code, _, _ = await call(gate_port, build("GET", "/api/x", {"host": IP_HOST}))
    check("split：IP Host 无 cookie 打 /api ⇒ 401", code == 401, f"code={code}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": "usavps.internal:19387"}))
    check("split：陌生主机名 ⇒ 口令档（失败安全方向）",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": "[fd7a:115c:a1e0::8931:be12]:19387"}))
    check("split：IPv6 字面量 Host ⇒ 口令档",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": "other-node.lax.ts.net:19387"}))
    check("split：任意 *.ts.net 名 ⇒ 令牌档",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""),
          f"code={code} loc={hdrs.get('location')}")

    set_conf("mode = split\ntoken_host = dsh.internal, 10.0.0.5\n")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": "dsh.internal:19387"}))
    check("split：gate.conf 追加的 token_host 主机名 ⇒ 令牌档",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""), f"code={code}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": "10.0.0.5:19387"}))
    check("split：被显式列为 token_host 的 IP ⇒ 令牌档（配置能覆盖默认分流）",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""), f"code={code}")

    set_conf("mode = split\n")
    calls.clear()
    gate.verify_linux_password = fake_verify  # type: ignore[assignment]
    form = b"username=shortstory&password=right-password"
    code, hdrs, _ = await call(gate_port, build("POST", "/login", {"host": IP_HOST}, body=form))
    split_cookie = hdrs.get("set-cookie", "").split(";")[0]
    check("split：IP 入口口令对 ⇒ 303 + 发门 cookie",
          code == 303 and split_cookie.startswith(gate.GATE_COOKIE + "=")
          and calls == [("shortstory", "right-password")],
          f"code={code} calls={calls}")
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": IP_HOST, "cookie": split_cookie}))
    check("split：IP 入口带门 cookie ⇒ 303 到令牌（再换 DSH cookie）",
          code == 303 and f"token={STUB_TOKEN}" in hdrs.get("location", ""),
          f"code={code} loc={hdrs.get('location')}")
    forged = gate.GATE_COOKIE + "=v1.eyJ1IjoibG9uZ3hpYSIsImV4cCI6NDEwMjQ0NDgwMH0.Zm9yZ2Vk"
    code, hdrs, _ = await call(gate_port, build("GET", "/", {"host": IP_HOST, "cookie": forged}))
    check("split：IP 入口伪造 cookie ⇒ 退回 /login",
          code == 303 and hdrs.get("location") == "/login", f"code={code} loc={hdrs.get('location')}")
    gate.verify_linux_password = real_verify  # type: ignore[assignment]

    gate_srv.close()
    stub.close()
    await asyncio.sleep(0.05)

    # ---- 真口令校验（不打桩，故意错口令；只验证"必须判否"） ----
    for user in ("longxia", "shortstory"):
        ok = gate.verify_linux_password(user, "definitely-not-the-password-" + user)
        check(f"真校验：{user} 错口令必须判否", ok is False, f"got={ok}")
    check("真校验：root 连试都不试", gate.verify_linux_password("root", "x") is False)


def main() -> int:
    started = time.time()
    asyncio.run(run())
    failed = [name for name, ok, _ in RESULTS if not ok]
    for name, ok, extra in RESULTS:
        if not ok:
            print(f"FAIL: {name} {extra}")
        elif VERBOSE:
            print(f"PASS: {name}")
    print(f"（{len(RESULTS)} 条断言，{len(failed)} 条失败，{time.time() - started:.1f}s）")
    print(f"__SELFTEST__ {len(RESULTS)} {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

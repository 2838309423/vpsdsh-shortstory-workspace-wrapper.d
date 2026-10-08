#!/usr/bin/env python3
"""只在指定网卡上监听的 TCP 转发器 —— 给 `dsh web` 当 Tailscale 门面。

为什么需要它：`@deepseek-ai/dsh-host-webserver` 的 `host` **只接受 `127.0.0.1` 与 `0.0.0.0`**
（实测 0.2.0-rc.2：别的值直接 `ValidationError: $.host expected "127.0.0.1" | "0.0.0.0"`），
而它 README 自述「服务器自身不携带 TLS、认证或来源策略」。所以：

    dsh web  --host 127.0.0.1 --port 19387          # 只回环
    ts-proxy --listen-host <tailscale-ip> --listen-port 19387 --target-port 19387

⇒ 只有 Tailscale 网内的设备（甲方手机/电脑）能连上，公网 IP 上**没有**任何监听。
纯标准库、无依赖；listen 绑不上（端口占用）就当场报错退出，不静默降级。

用法：
    python3 ts-proxy.py --listen-host 100.85.190.17 --listen-port 19387 --target-port 19387
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import sys
import time


def log(msg: str) -> None:
    print(f"[ts-proxy] {time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}", flush=True)


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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


async def _handle(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        up_r, up_w = await asyncio.open_connection(target_host, target_port)
    except OSError as exc:
        log(f"连接上游 {target_host}:{target_port} 失败（peer={peer}）：{exc}")
        writer.close()
        return
    await asyncio.gather(_pump(reader, up_w), _pump(up_r, writer))


async def _serve(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    handler = functools.partial(_handle, target_host=target_host, target_port=target_port)
    try:
        server = await asyncio.start_server(handler, listen_host, listen_port)
    except OSError as exc:
        log(f"监听 {listen_host}:{listen_port} 失败：{exc}")
        raise SystemExit(3) from exc
    log(f"listening {listen_host}:{listen_port} -> {target_host}:{target_port}")
    async with server:
        await server.serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description="Tailscale-only TCP forwarder for dsh web")
    ap.add_argument("--listen-host", required=True)
    ap.add_argument("--listen-port", type=int, required=True)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, required=True)
    args = ap.parse_args()
    try:
        asyncio.run(_serve(args.listen_host, args.listen_port, args.target_host, args.target_port))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

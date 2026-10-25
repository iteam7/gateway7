"""Installed CLI for local validation, serving, chatting and a key-free demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import socket
import signal
import sys
import threading
import time
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit
from typing import Any

import httpx
import uvicorn

from gateway7.app import create_app
from gateway7.config import GatewayConfig, load_config
from gateway7.errors import StartupError
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.providers import validate_provider_config


class _ManagedServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        """Defer process exit until the CLI has cleaned up its owned resources."""
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        signals = (signal.SIGINT, signal.SIGTERM)
        previous = {sig: signal.signal(sig, self.handle_exit) for sig in signals}
        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


async def _run_service(coroutine: Coroutine[Any, Any, None]) -> None:
    """Handle termination during startup and cleanup as well as while serving."""
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    interrupted = False

    def terminate(_signal: int, _frame: object) -> None:
        nonlocal interrupted
        if not interrupted and task is not None:
            interrupted = True
            loop.call_soon_threadsafe(task.cancel)

    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, terminate)
    try:
        await coroutine
    except asyncio.CancelledError:
        if not interrupted:
            raise
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


async def _serve(
    config_path: str | None,
    host: str,
    port: int,
    *,
    config: GatewayConfig | None = None,
) -> None:
    app = create_app(config_path, config=config)
    # Own lifespan so Uvicorn cannot print raw startup exceptions or config values.
    server = _ManagedServer(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            lifespan="off",
            access_log=False,
            timeout_graceful_shutdown=10,
        )
    )
    async with app.router.lifespan_context(app):
        await server.serve()


def _demo_config(port: int) -> GatewayConfig:
    return GatewayConfig.model_validate(
        {
            "provider": {
                "kind": "fake",
                "base_url": f"http://127.0.0.1:{port}",
                "key_env": "GATEWAY7_DEMO_KEY",
                "model": "fake",
            },
            "plugins": {
                "guard": {
                    "module": "gateway7.plugins.content_policy",
                    "required": True,
                    "settings": {"terms": ["BLOCK-ME-TEST"], "phase": "request", "action": "block"},
                },
                "phone": {
                    "module": "gateway7.plugins.phone_mask",
                    "required": True,
                    "settings": {"phase": "both"},
                },
                "email": {
                    "module": "gateway7.plugins.email_mask",
                    "required": True,
                    "settings": {"phase": "both"},
                },
                "redact": {
                    "module": "gateway7.plugins.content_policy",
                    "required": True,
                    "settings": {"terms": ["SECRET-TEST"], "phase": "response", "action": "redact"},
                },
            },
            "middleware": ["guard", "phone", "email", "redact"],
        }
    )


async def _demo(host: str, port: int) -> None:
    # The upstream listens only on loopback, retains no request text and has no
    # inspection endpoint. It is a packaged fixture, not a real-provider fallback.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        upstream_port = sock.getsockname()[1]
    key = "gateway7-synthetic-" + secrets.token_hex(24)
    previous_key = os.environ.get("GATEWAY7_DEMO_KEY")
    env = {**os.environ, "GATEWAY7_DEMO_KEY": key}
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "gateway7.demo:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(upstream_port),
            "--no-access-log",
            "--log-level",
            "warning",
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    process = None
    try:
        # Shield creation so cancellation cannot lose ownership of a spawned
        # child before the subprocess transport returns its process handle.
        process = await asyncio.shield(creation)
        async with httpx.AsyncClient(trust_env=False, timeout=0.3) as client:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if process.returncode is not None:
                    raise StartupError("Synthetic demo upstream failed to start")
                try:
                    response = await client.get(f"http://127.0.0.1:{upstream_port}/health")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            else:
                raise StartupError("Synthetic demo upstream did not become ready")
        os.environ["GATEWAY7_DEMO_KEY"] = key
        print("Starting synthetic demo; no real provider is contacted.", file=sys.stderr)
        await _serve(None, host, port, config=_demo_config(upstream_port))
    finally:
        if previous_key is None:
            os.environ.pop("GATEWAY7_DEMO_KEY", None)
        else:
            os.environ["GATEWAY7_DEMO_KEY"] = previous_key
        if process is None:
            process = await creation
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()


async def _chat(url: str, message: str, max_tokens: int) -> int:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise StartupError("--url must be an HTTP(S) origin without credentials, path or query")
    request = ChatRequest(messages=[Message(role="user", content=message)], max_tokens=max_tokens)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=310) as client:
        async with client.stream(
            "POST", url.rstrip("/") + "/chat", json=request.model_dump()
        ) as response:
            if response.status_code != 200:
                print(f"Gateway request failed (HTTP {response.status_code})", file=sys.stderr)
                return 1
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=16384):
                body.extend(chunk)
                if len(body) > 1_048_576:
                    raise StartupError("Gateway response exceeded the CLI size limit")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise StartupError("Invalid gateway response")
    answer = ChatResponse.model_validate({"text": data.get("text"), "usage": data.get("usage")})
    print(json.dumps(answer.model_dump(), ensure_ascii=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gateway7 middleware gateway")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the gateway with a YAML configuration")
    serve.add_argument("--config", default=os.environ.get("GATEWAY_CONFIG"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    validate = subcommands.add_parser(
        "validate", help="Validate config and trusted plugin factories offline"
    )
    validate.add_argument("--config", required=True)
    chat = subcommands.add_parser(
        "chat", help="Send text to a running gateway; omit --message to read stdin"
    )
    chat.add_argument("--url", default="http://127.0.0.1:8000")
    chat.add_argument("--message")
    chat.add_argument("--max-tokens", type=int, default=256)
    demo = subcommands.add_parser(
        "demo", help="Run a synthetic provider and reference middleware without keys"
    )
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original `python -m gateway7 --config ...` entry point.
    if not arguments or arguments[0].startswith("--") and arguments[0] not in ("--help",):
        arguments.insert(0, "serve")
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command in ("serve", "demo") and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.command == "chat" and not 1 <= args.max_tokens <= 4096:
        parser.error("--max-tokens must be between 1 and 4096")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    gateway_logger = logging.getLogger("gateway7")
    gateway_logger.handlers = [handler]
    gateway_logger.setLevel(logging.INFO)
    gateway_logger.propagate = False
    try:
        if args.command == "validate":
            config = load_config(args.config)
            validate_provider_config(config.provider)
            plugins = load_plugins(config)
            print(
                f"Configuration valid: provider={config.provider.kind}; middleware={len(plugins.middleware_chain)}"
            )
            return 0
        if args.command == "serve":
            if args.config is None:
                raise StartupError(
                    "Pass --config PATH or set GATEWAY_CONFIG; use gateway7 demo for a key-free start"
                )
            asyncio.run(_run_service(_serve(args.config, args.host, args.port)))
        elif args.command == "demo":
            asyncio.run(_run_service(_demo(args.host, args.port)))
        else:
            message = args.message if args.message is not None else sys.stdin.read(65537)
            if not message.strip() or len(message.encode("utf-8")) > 65536:
                raise StartupError("Chat input must be nonempty and at most 65536 UTF-8 bytes")
            return asyncio.run(_chat(args.url, message, args.max_tokens))
    except StartupError as error:
        print(f"Gateway startup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(
            "Gateway command failed; check configuration and service availability", file=sys.stderr
        )
        return 1
    return 0

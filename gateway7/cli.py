"""Installed CLI for local validation, serving, chatting and a key-free demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import socket
import signal
import stat
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
from gateway7.auth import _valid_token
from gateway7.config import GatewayConfig, load_config, validate_model_id
from gateway7.errors import StartupError
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.providers import validate_provider_config
from gateway7.offline import print_report, run_offline
from gateway7.scaffold import create_plugin_project
from gateway7.smoke import run_smoke
from gateway7.transport_loader import validate_transport_config
from gateway7.transports.http_proxy import _proxy_url

_SECRETS_FILE_LIMIT = 65536


def _private_regular_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and (
        os.name != "posix" or info.st_uid == os.geteuid() and not info.st_mode & 0o077
    )


def _unique_secret_names(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate secrets file member")
        result[name] = value
    return result


def _read_secrets_file(path: str, config: GatewayConfig) -> dict[str, str]:
    """Read only an explicit, bounded private JSON file of referenced credentials."""
    try:
        before = os.stat(path, follow_symlinks=False)
        if not _private_regular_file(before):
            raise OSError
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as source:
            after = os.fstat(source.fileno())
            if not _private_regular_file(after) or (before.st_dev, before.st_ino) != (
                after.st_dev,
                after.st_ino,
            ):
                raise OSError
            if after.st_size > _SECRETS_FILE_LIMIT:
                raise StartupError("Invalid secrets file")
            content = source.read(_SECRETS_FILE_LIMIT + 1)
    except (OSError, ValueError):
        raise StartupError("Cannot read private secrets file") from None
    try:
        if len(content) > _SECRETS_FILE_LIMIT:
            raise ValueError
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_secret_names)
        if not isinstance(data, dict):
            raise ValueError
        token_names = {client.token_env for client in config.auth.clients.values()}
        allowed = {config.provider.key_env, *token_names}
        proxy_name = None
        transport = config.provider.transport
        if transport is not None and transport.module == "gateway7.transports.http_proxy":
            candidate = transport.settings.get("url_env")
            if isinstance(candidate, str) and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]{0,127}", candidate
            ):
                proxy_name = candidate
                allowed.add(candidate)
        for name, value in data.items():
            if (
                name not in allowed
                or not isinstance(value, str)
                or not value
                or not value.isascii()
                or any(not 33 <= ord(character) <= 126 for character in value)
            ):
                raise ValueError
            if name in token_names and not _valid_token(value):
                raise ValueError
            if name == proxy_name:
                _proxy_url(value)
        return data
    except (ValueError, UnicodeError, RecursionError, StartupError):
        raise StartupError("Invalid secrets file") from None


@contextmanager
def _startup_environment(values: dict[str, str]) -> Iterator[None]:
    added = []
    try:
        for name, value in values.items():
            if name not in os.environ:
                os.environ[name] = value
                added.append(name)
        yield
    finally:
        for name in added:
            os.environ.pop(name, None)


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
    secrets_file: str | None = None,
) -> None:
    values = {}
    if secrets_file is not None:
        if config is None:
            config = load_config(
                config_path
                if config_path is not None
                else os.environ.get("GATEWAY_CONFIG", "config/demo.yaml")
            )
        values = _read_secrets_file(secrets_file, config)
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
    if secrets_file is None:
        async with app.router.lifespan_context(app):
            await server.serve()
    else:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()
        finish: asyncio.Future[BaseException | None] = loop.create_future()

        async def own_lifespan() -> None:
            # Task-local context managers must enter and exit in this same task.
            async with app.router.lifespan_context(app):
                ready.set_result(None)
                error = await finish
                if error is not None:
                    raise error

        lifecycle: asyncio.Task[None] | None = None
        try:
            with _startup_environment(values):
                lifecycle = asyncio.create_task(own_lifespan())
                await asyncio.wait((ready, lifecycle), return_when=asyncio.FIRST_COMPLETED)
                if lifecycle.done():
                    lifecycle.result()
            await server.serve()
            if not finish.done():
                finish.set_result(None)
            await asyncio.shield(lifecycle)
        except BaseException as error:
            if lifecycle is None:
                raise
            # The overlay is already restored before requesting or awaiting cleanup.
            if not finish.done():
                finish.set_result(error)
            if not ready.done():
                lifecycle.cancel()
            while not lifecycle.done():
                try:
                    await asyncio.shield(lifecycle)
                except (Exception, asyncio.CancelledError):
                    pass
            if not lifecycle.cancelled():
                lifecycle.exception()
            raise


def _demo_config(port: int) -> GatewayConfig:
    return GatewayConfig.model_validate(
        {
            "provider": {
                "kind": "fake",
                "base_url": f"http://127.0.0.1:{port}",
                "key_env": "GATEWAY7_DEMO_KEY",
                "model": "fake",
            },
            "auth": {
                "enabled": True,
                "clients": {
                    "demo": {"token_env": "GATEWAY7_DEMO_CLIENT_TOKEN", "models": ["fake"]}
                },
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
    previous_client_token = os.environ.get("GATEWAY7_DEMO_CLIENT_TOKEN")
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
        os.environ["GATEWAY7_DEMO_CLIENT_TOKEN"] = "gateway7-synthetic-client-token"
        print(
            "Starting synthetic demo; no real provider is contacted. Client token: gateway7-synthetic-client-token",
            file=sys.stderr,
        )
        await _serve(None, host, port, config=_demo_config(upstream_port))
    finally:
        if previous_client_token is None:
            os.environ.pop("GATEWAY7_DEMO_CLIENT_TOKEN", None)
        else:
            os.environ["GATEWAY7_DEMO_CLIENT_TOKEN"] = previous_client_token
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


async def _chat(
    url: str,
    message: str,
    max_tokens: int,
    *,
    token_env: str = "GATEWAY7_TOKEN",
    model: str | None = None,
) -> int:
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
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", token_env) is None:
        raise StartupError("--token-env must be an environment variable name")
    token = os.environ.get(token_env)
    if token is not None and (
        not token
        or not token.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
        or len(token) > 512
    ):
        raise StartupError("Gateway token environment variable has an invalid value")
    if model is not None:
        try:
            validate_model_id(model)
        except ValueError:
            raise StartupError("--model must be a valid model identifier") from None
    request = ChatRequest(messages=[Message(role="user", content=message)], max_tokens=max_tokens)
    # The CLI's chat command targets the unchanged native text endpoint.
    payload: dict[str, Any] = {
        "messages": [{"role": item.role, "content": item.content} for item in request.messages],
        "max_tokens": request.max_tokens,
    }
    if model is not None:
        payload["model"] = model
    headers = {} if token is None else {"authorization": "Bearer " + token}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=310) as client:
        async with client.stream(
            "POST", url.rstrip("/") + "/chat", json=payload, headers=headers
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
    answer = ChatResponse.model_validate(
        {
            "text": data.get("text"),
            "usage": data.get("usage"),
            "finish_reason": data.get("finish_reason", "stop"),
        }
    )
    print(json.dumps({"text": answer.text, "usage": answer.usage}, ensure_ascii=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gateway7 middleware gateway")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the gateway with a YAML configuration")
    serve.add_argument("--config", default=os.environ.get("GATEWAY_CONFIG"))
    serve.add_argument(
        "--secrets-file",
        help="Explicit private JSON file of config-referenced credentials; existing environment wins",
    )
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
    chat.add_argument("--model", help="An allowed model ID; omitted uses the server default")
    chat.add_argument(
        "--token-env",
        default="GATEWAY7_TOKEN",
        help="Environment variable holding the gateway bearer token",
    )
    smoke = subcommands.add_parser(
        "smoke",
        help="Check a running authenticated gateway with one potentially billable chat request",
        description=(
            "Check readiness and authentication, then make at most one chat request. "
            "Invoking this command can consume paid provider tokens; it does not verify provider identity."
        ),
    )
    smoke.add_argument("--url", default="http://127.0.0.1:8000")
    smoke.add_argument("--token-env", default="GATEWAY7_TOKEN")
    smoke.add_argument("--model", help="An allowed model ID; omitted uses the server default")
    smoke.add_argument("--max-tokens", type=int, default=256)
    smoke.add_argument(
        "--timeout", type=float, default=90, help="Whole-run limit in seconds (1–300)"
    )
    demo = subcommands.add_parser(
        "demo", help="Run a synthetic provider and reference middleware without keys"
    )
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8000)
    plugin = subcommands.add_parser("plugin", help="Create and test company middleware")
    plugin_commands = plugin.add_subparsers(dest="plugin_command", required=True)
    initialize = plugin_commands.add_parser(
        "init", help="Create an installable plugin project without overwriting"
    )
    initialize.add_argument("name")
    initialize.add_argument(
        "--directory", default=".", help="Existing parent directory for the new project"
    )
    test = plugin_commands.add_parser(
        "test", help="Run synthetic fixtures in a network-disabled worker"
    )
    test.add_argument("--config", required=True)
    test.add_argument("--fixtures", required=True)
    test.add_argument("--json", action="store_true", dest="as_json")
    test.add_argument(
        "--timeout", type=float, default=30, help="Whole-suite wall-clock limit in seconds (1–300)"
    )
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
    if args.command in ("chat", "smoke") and not 1 <= args.max_tokens <= 4096:
        parser.error("--max-tokens must be between 1 and 4096")
    if args.command == "smoke" and not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    if args.command == "plugin" and args.plugin_command == "test" and not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    gateway_logger = logging.getLogger("gateway7")
    gateway_logger.handlers = [handler]
    gateway_logger.setLevel(logging.INFO)
    gateway_logger.propagate = False
    try:
        if args.command == "smoke":
            code, report = asyncio.run(
                run_smoke(
                    args.url,
                    token_env=args.token_env,
                    model=args.model,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                )
            )
            print(json.dumps(report))
            return code
        if args.command == "plugin":
            if args.plugin_command == "init":
                project = create_plugin_project(args.name, args.directory)
                print(f"Created plugin project: {project}")
                print(
                    "Run inside the project: gateway7 plugin test --config gateway.yaml --fixtures fixtures.json"
                )
                return 0
            code, report = run_offline(args.config, args.fixtures, args.timeout)
            print_report(report, as_json=args.as_json)
            return code
        if args.command == "validate":
            config = load_config(args.config)
            validate_provider_config(config.provider)
            validate_transport_config(config.provider.transport)
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
            service = (
                _serve(args.config, args.host, args.port)
                if args.secrets_file is None
                else _serve(args.config, args.host, args.port, secrets_file=args.secrets_file)
            )
            asyncio.run(_run_service(service))
        elif args.command == "demo":
            asyncio.run(_run_service(_demo(args.host, args.port)))
        else:
            message = args.message if args.message is not None else sys.stdin.read(65537)
            if not message.strip() or len(message.encode("utf-8")) > 65536:
                raise StartupError("Chat input must be nonempty and at most 65536 UTF-8 bytes")
            return asyncio.run(
                _chat(
                    args.url, message, args.max_tokens, token_env=args.token_env, model=args.model
                )
            )
    except StartupError as error:
        print(f"Gateway startup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if args.command in ("chat", "smoke"):
            return 130
        if args.command == "plugin" and args.plugin_command == "test":
            print_report(
                {
                    "schema_version": 1,
                    "passed": False,
                    "total": 0,
                    "failed": 0,
                    "cases": [],
                    "error": "Offline fixture execution interrupted",
                },
                as_json=args.as_json,
            )
            return 2
        return 0
    except Exception:
        print(
            "Gateway command failed; check configuration and service availability", file=sys.stderr
        )
        return 1
    return 0

"""Private dev-only source loader and synthetic HTTP provider; never used by serve."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from collections.abc import Iterator
import hmac
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import sys
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
import httpx
from starlette.responses import JSONResponse, Response
import uvicorn

from gateway7.config import GatewayConfig, ProviderConfig, load_config
from gateway7.plugin_project import PluginProject, load_project, validate_project_config
from gateway7._project_source import project_source_imports
from gateway7.providers import HTTPProvider
from gateway7.responses_api import response_json, response_sse
from gateway7.responses_models import ResponsesResponse


class _LoopbackTransport(httpx.AsyncBaseTransport):
    """The actual adapter speaks only to the synthetic server in this child."""

    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.transport = httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        expected_method = "GET" if request.url.path == "/v1/models" else "POST"
        if (
            request.url.scheme != "https"
            or request.url.host != "api.openai.com"
            or request.url.port not in (None, 443)
            or request.url.query
            or request.method != expected_method
            or request.url.path not in {"/v1/models", "/v1/chat/completions", "/v1/responses"}
        ):
            raise httpx.UnsupportedProtocol("Development provider route is unsupported")
        outgoing = httpx.Request(
            request.method,
            self.origin + request.url.raw_path.decode("ascii"),
            headers=request.headers,
            content=await request.aread(),
        )
        return await self.transport.handle_async_request(outgoing)

    async def aclose(self) -> None:
        await self.transport.aclose()


def _last_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_last_text(item) for item in value]
        return next((text for text in reversed(parts) if text), "")
    if isinstance(value, dict):
        return _last_text(value.get("content", value.get("text", "")))
    return ""


def _synthetic_provider() -> FastAPI:
    upstream = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @upstream.get("/health")
    async def health():
        return {"status": "synthetic"}

    @upstream.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": "synthetic-model",
                    "object": "model",
                    "created": 0,
                    "owned_by": "gateway7-dev",
                }
            ],
        }

    async def payload(request: Request) -> dict[str, Any]:
        expected = ("Bearer " + os.environ["GATEWAY7_DEV_PROVIDER_TOKEN"]).encode()
        if not hmac.compare_digest(request.headers.get("authorization", "").encode(), expected):
            raise ValueError("Synthetic authorization failed")
        raw = await request.body()
        if len(raw) > 1048576:
            raise ValueError("Synthetic request too large")
        return json.loads(raw)

    @upstream.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await payload(request)
        text = "pong — " + _last_text(body.get("messages", []))
        identity = "chatcmpl_" + uuid4().hex
        tool_calls = None
        choice = body.get("tool_choice", "auto")
        if (
            body.get("tools")
            and choice != "none"
            and (
                choice == "required"
                or isinstance(choice, dict)
                or not body.get("messages")
                or body["messages"][-1].get("role") != "tool"
            )
        ):
            function = next(
                tool["function"]
                for tool in body["tools"]
                if not isinstance(choice, dict)
                or tool["function"]["name"] == choice["function"]["name"]
            )
            tool_calls = [
                {
                    "id": "call_" + uuid4().hex,
                    "type": "function",
                    "function": {"name": function["name"], "arguments": "{}"},
                }
            ]
            text = ""
        message: dict[str, Any] = {"role": "assistant", "content": text or None}
        if tool_calls is not None:
            message["tool_calls"] = tool_calls
        reason = "tool_calls" if tool_calls else "stop"
        if not body.get("stream"):
            return {
                "id": identity,
                "object": "chat.completion",
                "created": 0,
                "model": "synthetic-model",
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
            }
        delta: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            delta["tool_calls"] = [{"index": 0, **tool_calls[0]}]
        frames = [
            {
                "id": identity,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "synthetic-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            },
            {
                "id": identity,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "synthetic-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
            },
        ]
        encoded = b"".join(b"data: " + json.dumps(frame).encode() + b"\n\n" for frame in frames)
        return Response(encoded + b"data: [DONE]\n\n", media_type="text/event-stream")

    @upstream.post("/v1/responses")
    async def responses(request: Request):
        body = await payload(request)
        choice = body.get("tool_choice", "auto")
        tools = body.get("tools", [])
        functions = []
        for tool in tools:
            if tool["type"] == "function":
                functions.append((None, tool))
            elif tool["type"] == "namespace":
                functions.extend(
                    (tool["name"], child) for child in tool["tools"] if child["type"] == "function"
                )
        selected = None
        if choice == "required":
            selected = next(iter(functions), None)
        elif isinstance(choice, dict) and choice["type"] == "function":
            selected = next(
                (
                    (namespace, function)
                    for namespace, function in functions
                    if namespace == choice.get("namespace") and function["name"] == choice["name"]
                ),
                None,
            )
        output: list[dict[str, Any]]
        if selected is not None:
            namespace, function = selected
            call = {
                "id": "fc_" + uuid4().hex,
                "type": "function_call",
                "call_id": "call_" + uuid4().hex,
                "name": function["name"],
                "arguments": "{}",
                "status": "completed",
            }
            if namespace is not None:
                call["namespace"] = namespace
            output = [call]
        else:
            output = [
                {
                    "id": "msg_" + uuid4().hex,
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "pong — " + _last_text(body.get("input", "")),
                            "annotations": [],
                        }
                    ],
                }
            ]
        result = ResponsesResponse.model_validate(
            {
                "id": "resp_" + uuid4().hex,
                "object": "response",
                "created_at": 0,
                "model": "synthetic-model",
                "status": "completed",
                "parallel_tool_calls": body.get("parallel_tool_calls", True),
                "tool_choice": choice,
                "tools": tools,
                "output": output,
                "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
            }
        )
        if body.get("stream"):
            return Response(response_sse(result), media_type="text/event-stream")
        return JSONResponse(response_json(result))

    return upstream


def _listener(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


class _DevServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # The supervisor stops both servers together instead of installing two
        # competing Uvicorn signal handlers in the same process.
        yield


async def _run(root: str, port: int, status_file: Path) -> None:
    project = load_project(root)
    source = load_config(project.config)
    validate_project_config(project, source)
    # The hook remains active through serving and shutdown: project helpers may
    # be imported lazily by a request hook or a lifecycle callback.
    with project_source_imports(project.root):
        await _serve_project(project, source, port, status_file)


async def _serve_project(
    project: PluginProject, source: GatewayConfig, port: int, status_file: Path
) -> None:
    module = importlib.import_module(project.module)
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str) or not Path(origin).resolve().is_relative_to(project.root):
        raise ValueError("Project module did not resolve to its own source")
    raw = source.model_dump()
    raw["provider"] = {
        "kind": "openai",
        "model": "synthetic-model",
        "key_env": "GATEWAY7_DEV_PROVIDER_TOKEN",
    }
    raw["auth"] = {
        "enabled": True,
        "clients": {
            "development": {"token_env": "GATEWAY7_DEV_CLIENT_TOKEN", "models": ["synthetic-model"]}
        },
    }
    configured = GatewayConfig.model_validate(raw)
    upstream_socket, gateway_socket = _listener(0), None
    servers: list[uvicorn.Server] = []
    tasks: list[asyncio.Task[Any]] = []
    try:
        gateway_socket = _listener(port)
        upstream_url = "http://127.0.0.1:" + str(upstream_socket.getsockname()[1])
        gateway_url = "http://127.0.0.1:" + str(gateway_socket.getsockname()[1])
        import gateway7.app as app_module

        # No production toggle: only this private synthetic worker installs it.
        def build_synthetic(
            config: ProviderConfig, key: str, *, transport: httpx.AsyncBaseTransport | None = None
        ) -> HTTPProvider:
            if transport is not None:
                raise ValueError("Development provider transport must be synthetic")
            return HTTPProvider(config, key, transport=_LoopbackTransport(upstream_url))

        app_module.build_provider = build_synthetic
        applications = (_synthetic_provider(), app_module.create_app(config=configured))
        for application in applications:
            server: uvicorn.Server = _DevServer(
                uvicorn.Config(application, log_config=None, access_log=False)
            )
            servers.append(server)

        def stop(_number=None, _frame=None):
            for server in servers:
                server.should_exit = True

        numbers = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGBREAK"):
            numbers.append(signal.SIGBREAK)
        for number in numbers:
            signal.signal(number, stop)
        tasks = [
            asyncio.create_task(server.serve(sockets=[listener]))
            for server, listener in zip(servers, (upstream_socket, gateway_socket), strict=True)
        ]
        while not all(server.started for server in servers):
            if any(task.done() for task in tasks):
                raise ValueError("Development server startup failed")
            await asyncio.sleep(0.02)
        temporary = status_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"status": "ready", "gateway_url": gateway_url, "upstream_url": upstream_url}
            )
        )
        temporary.replace(status_file)
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for server in servers:
            server.should_exit = True
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        upstream_socket.close()
        if gateway_socket is not None:
            gateway_socket.close()


if __name__ == "__main__":
    try:
        asyncio.run(_run(sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])))
    except BaseException:
        raise SystemExit(2) from None

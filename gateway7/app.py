"""FastAPI application with bounded input, sanitized failures, and safe lifecycle."""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message as ASGIMessage, Receive, Scope, Send

from gateway7.config import load_config, provider_key
from gateway7.errors import GatewayError, StartupError
from gateway7.loader import load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest
from gateway7.pipeline import Pipeline
from gateway7.providers import build_provider

logger = logging.getLogger("gateway7")


def _error_response(code: str, request_id: str) -> JSONResponse:
    error = GatewayError(code)
    return JSONResponse(error.body(request_id), status_code=error.status_code)


class GatewayBoundaryMiddleware:
    """Bound bytes before JSON parsing, including bodies without Content-Length."""

    def __init__(self, app: ASGIApp, owner: FastAPI) -> None:
        self.app = app
        self.owner = owner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        started = time.monotonic()
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False
        status_code = 500

        async def safe_send(message: ASGIMessage) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"x-request-id", request_id.encode())],
                }
            await send(message)

        async def fail(code: str) -> None:
            await _error_response(code, request_id)(scope, receive, safe_send)

        try:
            if not getattr(self.owner.state, "ready", False):
                await fail("unavailable")
                return
            limits = self.owner.state.config.limits
            deadline = started + limits.request_timeout_seconds
            scope["state"]["deadline"] = deadline
            length_headers = [v for k, v in scope.get("headers", []) if k == b"content-length"]
            if len(length_headers) > 1:
                await fail("invalid_request")
                return
            if length_headers:
                try:
                    content_length = int(length_headers[0])
                    if content_length < 0:
                        raise ValueError
                except ValueError:
                    await fail("invalid_request")
                    return
                if content_length > limits.max_body_bytes:
                    await fail("body_too_large")
                    return
            body = bytearray()
            async with asyncio.timeout_at(deadline):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        status_code = 499
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limits.max_body_bytes:
                        await fail("body_too_large")
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
            delivered = False

            async def replay_receive() -> ASGIMessage:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, safe_send)
        except asyncio.CancelledError:
            status_code = 499
            raise
        except TimeoutError:
            if not response_started:
                await fail("timeout")
        except Exception:
            # Framework exceptions and invalid JSON never become traceback,
            # request-body, or provider details in responses or gateway logs.
            if not response_started:
                await fail("internal_error")
        finally:
            logger.info(
                "request_id=%s outcome=http_%d component=http duration_ms=%.3f",
                request_id,
                status_code,
                (time.monotonic() - started) * 1000,
            )


async def _watch_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


async def _run_connected(request: Request, payload: ChatRequest) -> Any:
    pipeline = request.app.state.pipeline
    job = asyncio.create_task(
        pipeline.run(payload, request.state.request_id, deadline=request.state.deadline)
    )
    disconnected = asyncio.create_task(_watch_disconnect(request))
    try:
        done, _ = await asyncio.wait((job, disconnected), return_when=asyncio.FIRST_COMPLETED)
        if job in done:
            return job.result()
        # No subsequent stages may start after cancellation is observed. In-process
        # hooks must cooperate with cancellation; this is not a process sandbox.
        job.cancel()
        return None
    finally:
        for task in (job, disconnected):
            if not task.done():
                task.cancel()
        await asyncio.gather(job, disconnected, return_exceptions=True)


def create_app(config_path: str | Path | None = None) -> FastAPI:
    path = config_path if config_path is not None else os.environ.get("GATEWAY_CONFIG", "config/demo.yaml")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        config = load_config(path)
        key = provider_key(config.provider)
        plugins = load_plugins(config)
        try:
            provider = build_provider(config.provider, key)
        except Exception:
            raise StartupError("Provider initialization failed") from None
        started = False
        try:
            await start_plugins(plugins, config.limits.hook_timeout_seconds)
            started = True
            app.state.config = config
            app.state.pipeline = Pipeline(plugins, provider, config.limits)
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            app.state.pipeline = None
            if started:
                await stop_plugins(plugins, config.limits.hook_timeout_seconds)
            try:
                async with asyncio.timeout(config.limits.hook_timeout_seconds):
                    await provider.aclose()
            except Exception:
                logger.warning("request_id=- outcome=shutdown_error component=provider duration_ms=0")

    app = FastAPI(title="Gateway7", version="0.1.0", lifespan=lifespan)
    app.state.ready = False
    app.add_middleware(GatewayBoundaryMiddleware, owner=app)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error_response("invalid_request", request.state.request_id)

    @app.exception_handler(GatewayError)
    async def gateway_failure(request: Request, error: GatewayError) -> JSONResponse:
        return JSONResponse(error.body(request.state.request_id), status_code=error.status_code)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat")
    async def chat(payload: ChatRequest, request: Request) -> Response:
        response = await _run_connected(request, payload)
        if response is None:
            return Response(status_code=499)
        return JSONResponse({**response.model_dump(), "request_id": request.state.request_id})

    return app

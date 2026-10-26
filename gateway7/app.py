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
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message as ASGIMessage, Receive, Scope, Send

from gateway7.config import GatewayConfig, load_config, provider_key
from gateway7.auth import AccessControl
from gateway7.errors import GatewayError, StartupError
from gateway7.loader import complete_cleanup, load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest
from gateway7.metrics import Metrics
from gateway7.openai_api import (
    NativeChatRequest,
    OpenAIChatRequest,
    completion_response,
    error_body,
)
from gateway7.pipeline import Pipeline
from gateway7.providers import build_provider

logger = logging.getLogger("gateway7")


def _error_response(
    code: str, request_id: str, *, openai: bool = False, parameter: str | None = None
) -> JSONResponse:
    error = GatewayError(code)
    status = 400 if openai and code == "invalid_request" else error.status_code
    headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
    return JSONResponse(
        error_body(error, request_id, parameter) if openai else error.body(request_id),
        status_code=status,
        headers=headers,
    )


def _openai_path(path: str) -> bool:
    return path.startswith("/v1/")


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
        metrics = self.owner.state.metrics
        route = {
            "/chat": "chat",
            "/health": "health",
            "/ready": "ready",
            "/metrics": "metrics",
            "/v1/chat/completions": "openai_chat",
            "/v1/models": "models",
        }.get(scope.get("path", ""), "other")
        metrics.http_in_flight.inc()

        async def safe_send(message: ASGIMessage) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-request-id", request_id.encode()),
                    ],
                }
            await send(message)

        async def fail(code: str) -> None:
            await _error_response(code, request_id, openai=_openai_path(scope.get("path", "")))(
                scope, receive, safe_send
            )

        try:
            if scope.get("method") == "GET" and route in ("health", "ready", "metrics"):
                await self.app(scope, receive, safe_send)
                return
            if not getattr(self.owner.state, "ready", False):
                await fail("unavailable")
                return
            if route in ("chat", "openai_chat", "models"):
                try:
                    scope["state"]["principal"] = self.owner.state.access.authenticate(
                        scope.get("headers", [])
                    )
                except GatewayError as error:
                    await fail(error.code)
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
            metrics.http_in_flight.dec()
            metrics.http_requests.labels(route, str(status_code)).inc()
            metrics.http_duration.labels(route).observe(max(0, time.monotonic() - started))
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


async def _run_connected(request: Request, payload: ChatRequest, selected_model: str) -> Any:
    pipeline = request.app.state.pipeline
    job = asyncio.create_task(
        pipeline.run(
            payload,
            request.state.request_id,
            deadline=request.state.deadline,
            provider_model=selected_model
            if selected_model != request.app.state.config.provider.model
            else None,
        )
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


def create_app(
    config_path: str | Path | None = None,
    *,
    config: GatewayConfig | None = None,
) -> FastAPI:
    path = (
        config_path
        if config_path is not None
        else os.environ.get("GATEWAY_CONFIG", "config/demo.yaml")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        active_config = config if config is not None else load_config(path)
        key = provider_key(active_config.provider)
        access = AccessControl(active_config)
        plugins = load_plugins(active_config)
        try:
            provider = build_provider(active_config.provider, key)
        except Exception:
            raise StartupError("Provider initialization failed") from None
        started = False
        failed = False
        try:
            await start_plugins(plugins, active_config.limits.hook_timeout_seconds)
            started = True
            app.state.config = active_config
            app.state.access = access
            app.state.pipeline = Pipeline(
                plugins,
                provider,
                active_config.limits,
                metrics=app.state.metrics,
                provider_name=active_config.provider.kind,
            )
            app.state.ready = True
            yield
        except BaseException:
            failed = True
            raise
        finally:
            app.state.ready = False
            app.state.pipeline = None
            app.state.access = None

            async def cleanup() -> None:
                try:
                    if started:
                        await stop_plugins(plugins, active_config.limits.hook_timeout_seconds)
                finally:
                    closing_started = time.monotonic()
                    timeout = active_config.limits.hook_timeout_seconds
                    timer = asyncio.timeout(timeout)
                    try:
                        async with timer:
                            await provider.aclose()
                        if timer.expired() or time.monotonic() - closing_started >= timeout:
                            raise TimeoutError
                    except (Exception, asyncio.CancelledError):
                        logger.warning(
                            "request_id=- outcome=shutdown_error component=provider duration_ms=%.3f",
                            (time.monotonic() - closing_started) * 1000,
                        )

            try:
                await complete_cleanup(cleanup())
            except (Exception, asyncio.CancelledError):
                # A cleanup interruption must not replace a startup/body failure.
                if not failed:
                    raise

    app = FastAPI(title="Gateway7", version="0.1.0", lifespan=lifespan, redirect_slashes=False)
    app.state.ready = False
    app.state.metrics = Metrics()
    app.add_middleware(GatewayBoundaryMiddleware, owner=app)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        parameter = None
        # Known option names make rejections actionable. Arbitrary client-supplied
        # field names and every input value remain absent from diagnostics.
        safe_parameters = {
            "model",
            "messages",
            "max_tokens",
            "max_completion_tokens",
            "stream",
            "store",
            "n",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "functions",
            "function_call",
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "stop",
            "seed",
            "logit_bias",
            "logprobs",
            "top_logprobs",
            "response_format",
            "stream_options",
            "reasoning_effort",
            "modalities",
            "audio",
            "prediction",
            "service_tier",
            "web_search_options",
            "user",
            "metadata",
            "safety_identifier",
            "prompt_cache_key",
        }
        for issue in error.errors():
            location = issue.get("loc", ())
            if len(location) > 1 and location[1] in safe_parameters:
                parameter = location[1]
                break
        return _error_response(
            "invalid_request",
            request.state.request_id,
            openai=_openai_path(request.url.path),
            parameter=parameter,
        )

    @app.exception_handler(GatewayError)
    async def gateway_failure(request: Request, error: GatewayError) -> JSONResponse:
        return _error_response(
            error.code, request.state.request_id, openai=_openai_path(request.url.path)
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            error.status_code, "invalid_request"
        )
        return _error_response(
            code, request.state.request_id, openai=_openai_path(request.url.path)
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> Response:
        available = app.state.ready
        return JSONResponse(
            {"status": "ready" if available else "not_ready"}, status_code=200 if available else 503
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            generate_latest(app.state.metrics.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    @app.post("/chat")
    async def chat(payload: NativeChatRequest, request: Request) -> Response:
        selected = request.state.principal.select_model(
            payload.model, app.state.config.provider.model
        )
        response = await _run_connected(request, payload.core_request(), selected)
        if response is None:
            return Response(status_code=499)
        return JSONResponse(
            {"text": response.text, "usage": response.usage, "request_id": request.state.request_id}
        )

    @app.post("/v1/chat/completions")
    async def openai_chat(payload: OpenAIChatRequest, request: Request) -> Response:
        selected = request.state.principal.select_model(
            payload.model, app.state.config.provider.model
        )
        response = await _run_connected(request, payload.core_request(), selected)
        if response is None:
            return Response(status_code=499)
        return JSONResponse(completion_response(response, selected, request.state.request_id))

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": model, "object": "model", "created": 0, "owned_by": "gateway7"}
                for model in request.state.principal.models
            ],
        }

    return app

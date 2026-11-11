"""FastAPI application with bounded input, sanitized failures, and safe lifecycle."""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message as ASGIMessage, Receive, Scope, Send

from gateway7 import __version__
from gateway7.analytics import Analytics
from gateway7.config import GatewayConfig, load_config, provider_key, validate_provider_model
from gateway7.auth import AccessControl
from gateway7.errors import GatewayError, ProviderError, StartupError
from gateway7.loader import complete_cleanup, load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest, ChatResponse
from gateway7.metrics import HTTPRequestOutcome, Metrics
from gateway7.openai_api import (
    EarlyChatEncoder,
    NativeChatRequest,
    OpenAIChatRequest,
    completion_response,
    completion_sse,
    error_body,
)
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import EarlyStreamUnsupported, ResponsesUnsupported
from gateway7.providers import CatalogModel, build_provider
from gateway7.responses_api import EarlyResponsesEncoder, response_json, response_sse
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesCreateRequest, ResponsesResponse
from gateway7.telemetry import Telemetry
from gateway7.transport_loader import create_transport, validate_transport_config

logger = logging.getLogger("gateway7")
_TIMEOUT_RESPONSE_GRACE_SECONDS = 0.1


async def _close_provider_resource(resource: Any, timeout: float) -> None:
    """Close the one resource currently owned by startup or the provider."""
    closing_started = time.monotonic()
    timer = asyncio.timeout(timeout)
    try:
        async with timer:
            await resource.aclose()
        if timer.expired() or time.monotonic() - closing_started >= timeout:
            raise TimeoutError
    except (Exception, asyncio.CancelledError):
        logger.warning(
            "request_id=- outcome=shutdown_error component=provider duration_ms=%.3f",
            (time.monotonic() - closing_started) * 1000,
        )


def _error_response(
    code: str,
    request_id: str,
    *,
    openai: bool = False,
    parameter: str | None = None,
    middleware: object = None,
) -> JSONResponse:
    error = GatewayError(code, middleware=middleware)
    status = 400 if openai and code == "invalid_request" else error.status_code
    headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
    return JSONResponse(
        error_body(error, request_id, parameter) if openai else error.body(request_id),
        status_code=status,
        headers=headers,
    )


def _openai_path(path: str) -> bool:
    return path.startswith("/v1/")


def _stream_mode(headers: list[tuple[bytes, bytes]]) -> Literal["buffered", "early"]:
    values = [value for name, value in headers if name.lower() == b"x-gateway7-stream-mode"]
    if not values:
        return "buffered"
    if len(values) != 1 or values[0] not in (b"buffered", b"early"):
        raise GatewayError("invalid_request")
    return "early" if values[0] == b"early" else "buffered"


def _responses_consent(headers: list[tuple[bytes, bytes]]) -> ResponsesConsent:
    def allowed(name: bytes) -> bool:
        values = [value for key, value in headers if key.lower() == name]
        if not values:
            return False
        if len(values) != 1 or values[0] not in (b"true", b"false"):
            raise GatewayError("invalid_request")
        return values[0] == b"true"

    return ResponsesConsent(
        allow_opaque=allowed(b"x-gateway7-allow-opaque"),
        allow_hosted=allowed(b"x-gateway7-allow-hosted-tools"),
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON member")
        result[name] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("Invalid JSON number")


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
        status_code: int | None = None
        response_completed = False
        error_code: str | None = None
        metrics = self.owner.state.metrics
        route = {
            "/chat": "chat",
            "/health": "health",
            "/ready": "ready",
            "/metrics": "metrics",
            "/v1/chat/completions": "openai_chat",
            "/v1/responses": "openai_responses",
            "/v1/models": "models",
        }.get(scope.get("path", ""), "other")
        analytics = self.owner.state.analytics
        analytics.started(request_id=request_id, route=route)
        metrics.http_in_flight.inc()

        async def safe_send(message: ASGIMessage) -> None:
            nonlocal response_started, response_completed, status_code
            if message["type"] == "http.response.start":
                response_started = True
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-request-id", request_id.encode()),
                    ],
                }
            await send(message)
            if message["type"] == "http.response.start":
                status_code = message["status"]
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_completed = True

        async def fail(code: str) -> None:
            nonlocal error_code
            error_code = code
            scope["state"]["http_outcome"] = code
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
            if route in ("chat", "openai_chat", "openai_responses", "models"):
                try:
                    scope["state"]["principal"] = self.owner.state.access.authenticate(
                        scope.get("headers", [])
                    )
                except GatewayError as error:
                    await fail(error.code)
                    return
            if route in ("chat", "openai_chat", "openai_responses"):
                try:
                    mode = _stream_mode(scope.get("headers", []))
                    if mode == "early" and route == "chat":
                        raise GatewayError("invalid_request")
                    scope["state"]["stream_mode"] = mode
                    if route == "openai_responses":
                        scope["state"]["responses_consent"] = _responses_consent(
                            scope.get("headers", [])
                        )
                except GatewayError:
                    response = _error_response(
                        "invalid_request", request_id, openai=_openai_path(scope.get("path", ""))
                    )
                    response.status_code = 400
                    await response(scope, receive, safe_send)
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
                        scope["state"]["http_outcome"] = "cancelled"
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
            scope["state"]["http_outcome"] = "cancelled"
            raise
        except TimeoutError:
            scope["state"]["http_outcome"] = "timeout"
            if not response_started:
                await fail("timeout")
        except Exception:
            scope["state"]["http_outcome"] = "internal_error"
            # Framework exceptions and invalid JSON never become traceback,
            # request-body, or provider details in responses or gateway logs.
            if not response_started:
                await fail("internal_error")
        finally:
            # One monotonic measurement feeds the Prometheus histogram, the local log
            # line and the exported log point and histogram, so they cannot disagree.
            duration = max(0.0, time.monotonic() - started)
            metrics.http_in_flight.dec()
            if status_code is not None:
                metrics.http_requests.labels(route, str(status_code)).inc()
            outcome = HTTPRequestOutcome.normalize(
                scope["state"].get(
                    "stream_outcome",
                    scope["state"].get("http_outcome", HTTPRequestOutcome.from_status(status_code)),
                )
            )
            if outcome == HTTPRequestOutcome.SUCCESS and not response_completed:
                outcome = HTTPRequestOutcome.CANCELLED
            metrics.observe_http_outcome(route, outcome)
            metrics.http_duration.labels(route).observe(duration)
            if error_code is None:
                error_code = scope["state"].get("error_code")
            terminal_status = status_code if response_completed and status_code is not None else 499
            if outcome == HTTPRequestOutcome.CANCELLED:
                terminal_status = 499
            elif outcome != HTTPRequestOutcome.SUCCESS:
                error_code = outcome.value
                terminal_status = (
                    400
                    if outcome == HTTPRequestOutcome.INVALID_REQUEST and status_code == 400
                    else GatewayError(outcome.value).status_code
                )
            logger.info(
                "request_id=%s outcome=%s component=http route=%s duration_ms=%.3f",
                request_id,
                scope["state"].get(
                    "stream_outcome",
                    "http_" + str(status_code) if status_code is not None else outcome.value,
                ),
                route,
                duration * 1000,
            )
            analytics.completed(
                request_id=request_id,
                route=route,
                status=terminal_status,
                duration_ms=duration * 1000,
            )
            telemetry = getattr(self.owner.state, "telemetry", None)
            if telemetry is not None:
                telemetry.record(
                    request_id=request_id,
                    route=route,
                    status=terminal_status,
                    error_code=error_code,
                    duration_ms=duration * 1000,
                )


class _PipelineAdmission:
    """App-local, event-loop-owned capacity; no waiting queue or early release."""

    def __init__(self, metrics: Metrics) -> None:
        self.limit = 64
        self.active = 0
        self.metrics = metrics
        self._tasks: set[asyncio.Task[Any]] = set()

    def acquire(self) -> None:
        # This check and increment contain no await, so another request cannot
        # acquire the same last slot on this application's event loop.
        if self.active >= self.limit:
            self.metrics.admission_rejections.inc()
            raise GatewayError("overloaded")
        self.active += 1
        self.metrics.active_pipelines.inc()

    def release_unstarted(self) -> None:
        # Only task-creation failure uses this rollback: no pipeline exists yet.
        self.active -= 1
        self.metrics.active_pipelines.dec()

    def track(self, task: asyncio.Task[Any]) -> None:
        # Retain tasks even if their HTTP caller has already been cancelled.
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[Any]) -> None:
        # An abandoned HTTP caller may never await its terminal exception.
        # Retrieving it prevents task-warning tracebacks without changing what
        # callers that still await the task receive.
        if not task.cancelled():
            task.exception()
        self._tasks.remove(task)
        self.active -= 1
        self.metrics.active_pipelines.dec()


async def _watch_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


def _select_model(request: Request, requested: str | None) -> str:
    config = request.app.state.config.provider
    selected = request.state.principal.select_model(requested, config.model)
    try:
        return validate_provider_model(config.kind, selected)
    except (TypeError, ValueError):
        raise GatewayError("invalid_request") from None


async def _run_connected(
    request: Request, payload: ChatRequest, selected_model: str, *, provider_stream: bool = False
) -> Any:
    pipeline = request.app.state.pipeline

    def operation() -> Coroutine[Any, Any, ChatResponse]:
        return pipeline.run(
            payload,
            request.state.request_id,
            deadline=request.state.deadline,
            provider_model=selected_model
            if selected_model != request.app.state.config.provider.model
            else None,
            **({"provider_stream": True} if provider_stream else {}),
        )

    return await _run_connected_operation(request, operation)


PipelineResult = TypeVar("PipelineResult")


async def _run_connected_operation(
    request: Request, operation: Callable[[], Coroutine[Any, Any, PipelineResult]]
) -> PipelineResult | None:
    """Share one admission lease and disconnect guard across native API shapes."""
    admission = request.app.state.admission
    admission.acquire()
    work = None
    try:
        work = operation()
        job = asyncio.create_task(work)
    except BaseException:
        admission.release_unstarted()
        if work is not None:
            work.close()
        raise
    admission.track(job)
    disconnected = None
    disconnect_work = None
    try:
        disconnect_work = _watch_disconnect(request)
        disconnected = asyncio.create_task(disconnect_work)
        done, _ = await asyncio.wait((job, disconnected), return_when=asyncio.FIRST_COMPLETED)
        if job in done:
            return job.result()
        # No subsequent stages may start after cancellation is observed. In-process
        # hooks must cooperate with cancellation; this is not a process sandbox.
        job.cancel()
        return None
    finally:
        if disconnected is None and disconnect_work is not None:
            disconnect_work.close()
        tasks = (job,) if disconnected is None else (job, disconnected)
        for task in tasks:
            if not task.done():
                task.cancel()

        async def reap() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)

        await complete_cleanup(reap())


class _CheckedBody(Response):
    """A fully serialized, policy-approved body with a bounded send."""

    def __init__(
        self,
        body: bytes,
        deadline: float,
        *,
        media_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body, media_type=media_type, headers=headers)
        self.deadline = deadline

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if time.monotonic() >= self.deadline:
            raise TimeoutError
        timer = asyncio.timeout_at(self.deadline)
        try:
            async with timer:
                await super().__call__(scope, receive, send)
        except TimeoutError:
            raise
        except OSError:
            # ASGI reports a closed downstream connection through send(). Do
            # not replace an already started response or retry a failed start.
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError from None
            if timer.expired() or time.monotonic() >= self.deadline:
                raise TimeoutError from None
            scope.setdefault("state", {})["http_outcome"] = "cancelled"


class _CheckedSSE(_CheckedBody):
    """A fully serialized, policy-approved SSE body with a bounded send."""

    def __init__(self, body: bytes, deadline: float) -> None:
        super().__init__(
            body,
            deadline,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


TextSink = Callable[[str], Awaitable[None]]
StreamResult = TypeVar("StreamResult")
EncoderResult = TypeVar("EncoderResult", contravariant=True)
EarlyOperation = Callable[[TextSink], Awaitable[StreamResult]]


class _EarlyStreamEncoder(Protocol[EncoderResult]):
    """Packet framing belongs to the route, not the protected ASGI lifecycle."""

    def text(self, text: str) -> bytes: ...

    def complete(self, response: EncoderResult) -> bytes: ...

    def error(self, error: GatewayError) -> bytes: ...


class _EarlySSE(Response, Generic[StreamResult]):
    """One admitted job owns generation, direct sends, and awaited cleanup.

    Other streaming routes supply an operation and packet encoder, without
    duplicating deadline, disconnect, admission, or error handling.
    """

    def __init__(
        self,
        request: Request,
        run: EarlyOperation[StreamResult],
        encoder: _EarlyStreamEncoder[StreamResult],
    ) -> None:
        super().__init__(
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self.raw_headers = [
            (name, value) for name, value in self.raw_headers if name != b"content-length"
        ]
        self.request = request
        self.run = run
        self.encoder = encoder
        self.closed = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = self.request
        deadline = request.state.deadline
        started = False
        send_failed = False

        def checkpoint(until: float = deadline) -> None:
            task = asyncio.current_task()
            if self.closed or (task is not None and task.cancelling()):
                raise asyncio.CancelledError
            if time.monotonic() >= until:
                raise TimeoutError

        async def send_until(message: ASGIMessage, until: float) -> None:
            nonlocal send_failed
            checkpoint(until)
            try:
                async with asyncio.timeout_at(until):
                    await send(message)
                checkpoint(until)
            except asyncio.CancelledError:
                send_failed = True
                self.closed = True
                raise
            except Exception:
                send_failed = True
                self.closed = True
                # The transport is dead, not the upstream provider. Cancel the
                # inline operation and await its resource cleanup before release.
                raise asyncio.CancelledError from None

        async def bounded_send(message: ASGIMessage) -> None:
            await send_until(message, deadline)

        async def packet(body: bytes, *, final: bool = False) -> None:
            nonlocal started
            checkpoint()
            if not started:
                started = True
                await bounded_send(
                    {"type": "http.response.start", "status": 200, "headers": self.raw_headers}
                )
            await bounded_send({"type": "http.response.body", "body": body, "more_body": not final})

        async def on_text(text: str) -> None:
            checkpoint()
            if text:
                # No queue or producer task: an upstream read cannot advance
                # until the actual downstream ASGI send finishes.
                await packet(self.encoder.text(text))

        async def serve() -> None:
            try:
                async with asyncio.timeout_at(deadline):
                    checkpoint()
                    response = await self.run(on_text)
                    checkpoint()
                    terminal = self.encoder.complete(response)
                    await packet(terminal, final=True)
                request.state.stream_outcome = "complete"
            except asyncio.CancelledError:
                request.state.stream_outcome = (
                    "timeout" if time.monotonic() >= deadline else "cancelled"
                )
                raise
            except Exception as failure:
                task = asyncio.current_task()
                if self.closed or (task is not None and task.cancelling()):
                    request.state.stream_outcome = (
                        "timeout" if time.monotonic() >= deadline else "cancelled"
                    )
                    raise asyncio.CancelledError from None
                error = (
                    GatewayError("timeout")
                    if time.monotonic() >= deadline or isinstance(failure, TimeoutError)
                    else failure
                    if isinstance(failure, GatewayError)
                    else GatewayError(
                        "invalid_request"
                        if isinstance(failure, EarlyStreamUnsupported)
                        else "internal_error"
                    )
                )
                request.state.stream_outcome = error.code
                if send_failed or (started and time.monotonic() >= deadline):
                    return
                try:
                    if started:
                        await packet(self.encoder.error(error), final=True)
                    else:
                        # Report a pre-header timeout as 504, even though its
                        # generation deadline has just expired. Only this JSON
                        # control response gets a bounded delivery allowance;
                        # generation and post-header packets never get more time.
                        error_deadline = (
                            time.monotonic() + _TIMEOUT_RESPONSE_GRACE_SECONDS
                            if time.monotonic() >= deadline
                            else deadline
                        )

                        async def error_send(message: ASGIMessage) -> None:
                            await send_until(message, error_deadline)

                        await _error_response(
                            error.code,
                            request.state.request_id,
                            openai=True,
                            middleware=error.middleware,
                        )(scope, receive, error_send)
                except asyncio.CancelledError:
                    request.state.stream_outcome = (
                        "timeout" if time.monotonic() >= deadline else "cancelled"
                    )
                    raise
                except Exception:
                    # A failed error delivery cannot trigger a second response.
                    request.state.stream_outcome = (
                        "timeout" if time.monotonic() >= deadline else "cancelled"
                    )

        admission = request.app.state.admission
        admission.acquire()
        work = serve()
        try:
            job = asyncio.create_task(work)
        except BaseException:
            work.close()
            admission.release_unstarted()
            raise
        admission.track(job)
        disconnected = None
        disconnect_work = None
        try:
            disconnect_work = _watch_disconnect(request)
            disconnected = asyncio.create_task(disconnect_work)
            done, _ = await asyncio.wait((job, disconnected), return_when=asyncio.FIRST_COMPLETED)
            if job in done and not (job.cancelled() and send_failed):
                job.result()
            elif job not in done:
                request.state.stream_outcome = "cancelled"
        finally:
            # Pin closure before cancellation: resistant in-process code must
            # never resume forwarding or sending after a dead connection.
            self.closed = True
            if disconnected is None and disconnect_work is not None:
                disconnect_work.close()
            tasks = (job,) if disconnected is None else (job, disconnected)
            for task in tasks:
                if not task.done():
                    task.cancel()

            async def reap() -> None:
                await asyncio.gather(*tasks, return_exceptions=True)

            await complete_cleanup(reap())


def create_app(
    config_path: str | Path | None = None,
    *,
    config: GatewayConfig | None = None,
    telemetry: Telemetry | None = None,
    analytics: Analytics | None = None,
) -> FastAPI:
    path = (
        config_path
        if config_path is not None
        else os.environ.get("GATEWAY_CONFIG", "config/demo.yaml")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_telemetry = telemetry if telemetry is not None else Telemetry.from_environment()
        app.state.telemetry = active_telemetry
        active_analytics = Analytics.disabled()
        try:
            active_analytics = analytics if analytics is not None else Analytics.from_environment()
            await active_analytics.start()
            app.state.analytics = active_analytics
            async with gateway_lifespan(app):
                yield
        finally:
            app.state.analytics = Analytics.disabled()
            try:
                await active_analytics.shutdown()
            finally:
                app.state.telemetry = Telemetry.disabled()
                # Flushing performs blocking HTTP export with its own timeout.
                await asyncio.to_thread(active_telemetry.shutdown)

    @asynccontextmanager
    async def gateway_lifespan(app: FastAPI):
        app.state.ready = False
        active_config = config if config is not None else load_config(path)
        key = provider_key(active_config.provider)
        access = AccessControl(active_config)
        validated_transport = validate_transport_config(active_config.provider.transport)
        plugins = load_plugins(active_config)
        transport = create_transport(validated_transport)
        try:
            if transport is None:
                provider = build_provider(active_config.provider, key)
            else:
                provider = build_provider(active_config.provider, key, transport=transport)
        except BaseException as error:
            if transport is not None:
                try:
                    await complete_cleanup(
                        _close_provider_resource(
                            transport, active_config.limits.hook_timeout_seconds
                        )
                    )
                except (Exception, asyncio.CancelledError):
                    # Preserve the initialization failure after owned cleanup.
                    pass
            if not isinstance(error, Exception):
                raise
            raise StartupError("Provider initialization failed") from None
        started = False
        failed = False
        try:
            await start_plugins(plugins, active_config.limits.hook_timeout_seconds)
            started = True
            app.state.config = active_config
            app.state.admission.limit = active_config.limits.max_concurrent_requests
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
                    await _close_provider_resource(
                        provider, active_config.limits.hook_timeout_seconds
                    )

            try:
                await complete_cleanup(cleanup())
            except (Exception, asyncio.CancelledError):
                # A cleanup interruption must not replace a startup/body failure.
                if not failed:
                    raise

    app = FastAPI(title="Gateway7", version=__version__, lifespan=lifespan, redirect_slashes=False)
    app.state.ready = False
    app.state.metrics = Metrics()
    app.state.admission = _PipelineAdmission(app.state.metrics)
    app.state.telemetry = Telemetry.disabled()
    app.state.analytics = Analytics.disabled()
    app.add_middleware(GatewayBoundaryMiddleware, owner=app)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        request.state.http_outcome = "invalid_request"
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
        request.state.error_code = "invalid_request"
        return _error_response(
            "invalid_request",
            request.state.request_id,
            openai=_openai_path(request.url.path),
            parameter=parameter,
        )

    @app.exception_handler(GatewayError)
    async def gateway_failure(request: Request, error: GatewayError) -> JSONResponse:
        request.state.http_outcome = error.code
        request.state.error_code = error.code
        return _error_response(
            error.code,
            request.state.request_id,
            openai=_openai_path(request.url.path),
            middleware=error.middleware,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            error.status_code, "invalid_request"
        )
        request.state.http_outcome = code
        request.state.error_code = code
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
        selected = _select_model(request, payload.model)
        response = await _run_connected(request, payload.core_request(), selected)
        if response is None:
            return Response(status_code=499)
        return JSONResponse(
            {"text": response.text, "usage": response.usage, "request_id": request.state.request_id}
        )

    @app.post("/v1/chat/completions")
    async def openai_chat(payload: OpenAIChatRequest, request: Request) -> Response:
        selected = _select_model(request, payload.model)
        if app.state.config.provider.kind != "openai" and payload.needs_openai_provider():
            raise GatewayError("invalid_request")
        if request.state.stream_mode == "early":
            pipeline = app.state.pipeline
            if (
                not payload.stream
                or app.state.config.provider.kind != "openai"
                or not callable(getattr(pipeline, "run_early", None))
                or not callable(
                    getattr(getattr(pipeline, "provider", None), "complete_early", None)
                )
            ):
                raise GatewayError("invalid_request")

            async def run(on_text: TextSink) -> ChatResponse:
                return await pipeline.run_early(
                    payload.core_request(),
                    request.state.request_id,
                    on_text=on_text,
                    deadline=request.state.deadline,
                    provider_model=selected
                    if selected != app.state.config.provider.model
                    else None,
                )

            return _EarlySSE(
                request,
                run,
                EarlyChatEncoder(
                    selected,
                    request.state.request_id,
                    include_usage=payload.stream_options is not None
                    and payload.stream_options.include_usage,
                ),
            )
        response = await _run_connected(
            request, payload.core_request(), selected, provider_stream=payload.stream
        )
        if response is None:
            return Response(status_code=499)
        if payload.stream:
            body = completion_sse(
                response,
                selected,
                request.state.request_id,
                include_usage=payload.stream_options is not None
                and payload.stream_options.include_usage,
            )
            if time.monotonic() >= request.state.deadline:
                raise GatewayError("timeout")
            return _CheckedSSE(body, request.state.deadline)
        return JSONResponse(completion_response(response, selected, request.state.request_id))

    @app.post("/v1/responses")
    async def responses(request: Request) -> Response:
        consent = request.state.responses_consent
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if (
            content_type
            and content_type != "application/json"
            and not (content_type.startswith("application/") and content_type.endswith("+json"))
        ):
            raise GatewayError("invalid_request")
        try:
            body = json.loads(
                await request.body(),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            payload = ResponsesCreateRequest.model_validate(body, context={"consent": consent})
            core = payload.core_request(consent=consent)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise GatewayError("invalid_request") from None
        selected = _select_model(request, payload.model)
        if app.state.config.provider.kind != "openai":
            raise GatewayError("invalid_request")
        if request.state.stream_mode == "early":
            pipeline = app.state.pipeline
            if (
                not payload.stream
                or not callable(getattr(pipeline, "run_responses_early", None))
                or not callable(
                    getattr(getattr(pipeline, "provider", None), "complete_responses_early", None)
                )
            ):
                raise GatewayError("invalid_request")
            encoder = EarlyResponsesEncoder()

            async def run(on_text: TextSink) -> ResponsesResponse:
                async def forward(delta: ResponsesTextDelta) -> None:
                    text = encoder.stage_text(delta)
                    if text is not None:
                        await on_text(text)

                try:
                    return await pipeline.run_responses_early(
                        core,
                        request.state.request_id,
                        on_text_delta=forward,
                        deadline=request.state.deadline,
                        provider_model=selected,
                        consent=consent,
                    )
                except ResponsesUnsupported:
                    raise GatewayError("invalid_request") from None

            return _EarlySSE(request, run, encoder)
        try:
            response = await _run_connected_operation(
                request,
                lambda: app.state.pipeline.run_responses(
                    core,
                    request.state.request_id,
                    deadline=request.state.deadline,
                    provider_model=selected,
                    stream=payload.stream,
                    consent=consent,
                ),
            )
        except ResponsesUnsupported:
            raise GatewayError("invalid_request") from None
        if response is None:
            return Response(status_code=499)
        try:
            encoded = (
                response_sse(response)
                if payload.stream
                else json.dumps(response_json(response), ensure_ascii=True, allow_nan=False).encode(
                    "ascii"
                )
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise GatewayError("provider_error") from None
        if time.monotonic() >= request.state.deadline:
            raise GatewayError("timeout")
        if payload.stream:
            return _CheckedSSE(encoded, request.state.deadline)
        return _CheckedBody(encoded, request.state.deadline, media_type="application/json")

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        permitted = request.state.principal.models
        if permitted is not None:
            catalog = tuple(CatalogModel(model, 0, "gateway7") for model in permitted)
        elif app.state.config.provider.kind != "openai":
            # These adapters have no discovery API. The seed describes local
            # configuration, not verified capability of the provider account.
            catalog = (CatalogModel(app.state.config.provider.model, 0, "gateway7"),)
        else:

            async def discover() -> tuple[CatalogModel, ...]:
                try:
                    async with asyncio.timeout_at(request.state.deadline):
                        result = await app.state.pipeline.provider.get_models(
                            deadline=request.state.deadline
                        )
                    if time.monotonic() >= request.state.deadline:
                        raise TimeoutError
                    return result
                except TimeoutError:
                    raise GatewayError("timeout") from None
                except ProviderError:
                    raise GatewayError("unavailable") from None

            discovered = await _run_connected_operation(request, discover)
            if discovered is None:
                request.state.http_outcome = "cancelled"
                return Response(status_code=499)
            catalog = discovered
        body = {
            "object": "list",
            "data": [
                {
                    "id": model.id,
                    "object": model.object,
                    "created": model.created,
                    "owned_by": model.owned_by,
                }
                for model in catalog
            ],
        }
        return _CheckedBody(
            json.dumps(body, ensure_ascii=True, allow_nan=False).encode("ascii"),
            request.state.deadline,
            media_type="application/json",
        )

    return app

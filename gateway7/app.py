"""FastAPI application with bounded input, sanitized failures, and safe lifecycle."""

import asyncio
import json
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match, Route
from starlette.types import ASGIApp, Message as ASGIMessage, Receive, Scope, Send

from gateway7 import __version__
from gateway7.analytics import Analytics
from gateway7.client_policies import build_client_pipelines
from gateway7.config import GatewayConfig, load_config, provider_key
from gateway7.auth import AccessControl
from gateway7.errors import GatewayError, StartupError
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
from gateway7.operator_console import CONSOLE_HEADERS, OPERATOR_PATHS, console_asset, operator_state
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import EarlyStreamUnsupported, ResponsesUnsupported
from gateway7.providers import build_provider
from gateway7.responses_api import EarlyResponsesEncoder, response_json, response_sse
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesCreateRequest, ResponsesResponse
from gateway7.telemetry import Telemetry
from gateway7.transport_loader import create_transport, validate_transport_config
from gateway7.usage import OperatorAccess, UsageLedger

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
    retry_after: object = None,
) -> JSONResponse:
    error = GatewayError(code, middleware=middleware, retry_after=retry_after)
    status = 400 if openai and code == "invalid_request" else error.status_code
    headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else {}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
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


def _validate_json_scalars(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Invalid JSON number")


class _StrictJSONRequest(Request):
    """Parse the DTO routes once without ambiguous members or JSON extensions."""

    async def json(self) -> Any:
        if not hasattr(self, "_json"):
            try:
                value = json.loads(
                    (await self.body()).decode("utf-8"),
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
                _validate_json_scalars(value)
                self._json = value
            except (ValueError, UnicodeError, RecursionError):
                # FastAPI normally handles malformed JSON; our stricter parser
                # also rejects duplicate members and unsupported byte encodings.
                raise StarletteHTTPException(status_code=400) from None
        return self._json


class _StrictJSONRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def strict_json(request: Request) -> Response:
            return await handle(_StrictJSONRequest(request.scope, request.receive))

        return strict_json


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
        scope["state"]["admission_delivery_owner"] = True
        response_started = False
        status_code: int | None = None
        response_completed = False
        operator_path = scope.get("path", "").startswith("/operator/")
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
                headers = message.get("headers", [])
                if operator_path:
                    owned = {
                        name.lower().encode("ascii"): value.encode("ascii")
                        for name, value in CONSOLE_HEADERS.items()
                    }
                    headers = [
                        (name, value) for name, value in headers if name.lower() not in owned
                    ] + list(owned.items())
                message = {
                    **message,
                    "headers": [
                        *headers,
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
            if scope.get("path") in OPERATOR_PATHS:
                try:
                    access = self.owner.state.operator_access
                    if scope.get("path") in {"/operator/usage", "/operator/state"}:
                        access.authenticate(scope.get("headers", []))
                    elif not access.enabled:
                        raise GatewayError("not_found")
                except GatewayError as error:
                    await fail(error.code)
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
            lease = scope["state"].pop("admission_lease", None)
            if lease is not None:
                self.owner.state.admission.release_delivery(lease)
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


@dataclass(frozen=True, eq=False)
class _AdmissionLease:
    client_id: str | None


@dataclass
class _RateBucket:
    capacity: int
    tokens: float
    updated: float


class _PipelineAdmission:
    """App-local, event-loop-owned capacity; no waiting queue or early release."""

    def __init__(self, metrics: Metrics, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = 64
        self.active = 0
        self.metrics = metrics
        self._tasks: dict[asyncio.Task[Any], _AdmissionLease] = {}
        self._leases: set[_AdmissionLease] = set()
        self._global_pending: set[_AdmissionLease] = set()
        self._delivery_pending: set[_AdmissionLease] = set()
        self._tracked: set[_AdmissionLease] = set()
        self._client_limits: dict[str, int | None] = {}
        self._client_active: dict[str, int] = {}
        self._authenticated = False
        self._clock = clock
        self._rate_buckets: dict[str, _RateBucket] = {}
        self._rate_debits: set[_AdmissionLease] = set()

    def configure(self, config: GatewayConfig) -> None:
        if self._leases:
            raise StartupError("Cannot configure admission while requests are active")
        self.limit = config.limits.max_concurrent_requests
        self._authenticated = config.auth.enabled
        self._client_limits = {
            name: client.limits.max_concurrent_requests
            for name, client in config.auth.clients.items()
            if client.enabled
        }
        self._client_active = {name: 0 for name in self._client_limits}
        now = self._clock()
        self._rate_buckets = {
            name: _RateBucket(limit, float(limit), now)
            for name, client in config.auth.clients.items()
            if client.enabled and (limit := client.limits.requests_per_minute) is not None
        }

    def _debit_rate(self, client_id: str | None) -> bool:
        bucket = self._rate_buckets.get(client_id) if client_id is not None else None
        if bucket is None:
            return False
        now = max(bucket.updated, self._clock())
        bucket.tokens = min(
            float(bucket.capacity),
            bucket.tokens + (now - bucket.updated) * bucket.capacity / 60,
        )
        bucket.updated = now
        if bucket.tokens < 1:
            self.metrics.rate_limit_rejections.inc()
            retry_after = max(1, min(60, math.ceil((1 - bucket.tokens) * 60 / bucket.capacity)))
            raise GatewayError("rate_limited", retry_after=retry_after)
        bucket.tokens -= 1
        return True

    def acquire(
        self, client_id: str | None = None, *, hold_delivery: bool = False
    ) -> _AdmissionLease:
        # This check and increment contain no await, so another request cannot
        # acquire the same global or client slot on this application's event loop.
        if (
            self._authenticated
            and client_id is None
            or (client_id is not None and client_id not in self._client_limits)
        ):
            raise GatewayError("unauthorized")
        if self.active >= self.limit:
            self.metrics.admission_rejections.inc()
            raise GatewayError("overloaded")
        if client_id is not None:
            limit = self._client_limits[client_id]
            if limit is not None and self._client_active[client_id] >= limit:
                self.metrics.admission_rejections.inc()
                raise GatewayError("client_overloaded")
        rate_debited = self._debit_rate(client_id)
        lease = _AdmissionLease(client_id)
        self._leases.add(lease)
        self._global_pending.add(lease)
        if hold_delivery:
            self._delivery_pending.add(lease)
        if rate_debited:
            self._rate_debits.add(lease)
        if client_id is not None:
            self._client_active[client_id] += 1
        self.active += 1
        self.metrics.active_pipelines.inc()
        return lease

    def release_unstarted(self, lease: _AdmissionLease) -> None:
        # Only task-creation failure uses this rollback: no pipeline exists yet.
        if lease not in self._global_pending or lease in self._tracked:
            raise ValueError("Admission lease is not an unstarted owned request")
        self.rollback_start(lease)
        self._global_pending.remove(lease)
        self._delivery_pending.discard(lease)
        self.active -= 1
        self.metrics.active_pipelines.dec()
        self._release_client(lease)

    def rollback_start(self, lease: _AdmissionLease) -> None:
        """Refund admission setup failure, without releasing running cleanup."""
        if lease not in self._leases:
            raise ValueError("Admission lease is not owned by this application")
        if lease in self._rate_debits:
            self._rate_debits.remove(lease)
            assert lease.client_id is not None
            bucket = self._rate_buckets[lease.client_id]
            bucket.tokens = min(float(bucket.capacity), bucket.tokens + 1)

    def track(self, task: asyncio.Task[Any], lease: _AdmissionLease) -> None:
        # Retain tasks even if their HTTP caller has already been cancelled.
        if lease not in self._global_pending or lease in self._tracked or task in self._tasks:
            raise ValueError("Admission lease is not available for tracking")
        self._tasks[task] = lease
        self._tracked.add(lease)
        task.add_done_callback(self._finished)

    def release_delivery(self, lease: _AdmissionLease) -> None:
        if lease not in self._delivery_pending:
            raise ValueError("Admission lease has no owned delivery")
        self._delivery_pending.remove(lease)
        if lease not in self._global_pending:
            self._release_client(lease)

    def _release_client(self, lease: _AdmissionLease) -> None:
        self._leases.remove(lease)
        if lease.client_id is not None:
            self._client_active[lease.client_id] -= 1

    def _finished(self, task: asyncio.Task[Any]) -> None:
        # An abandoned HTTP caller may never await its terminal exception.
        # Retrieving it prevents task-warning tracebacks without changing what
        # callers that still await the task receive.
        if not task.cancelled():
            task.exception()
        lease = self._tasks.pop(task)
        self._rate_debits.discard(lease)
        self._tracked.remove(lease)
        self._global_pending.remove(lease)
        self.active -= 1
        self.metrics.active_pipelines.dec()
        if lease not in self._delivery_pending:
            self._release_client(lease)


def _admit_request(request: Request) -> _AdmissionLease:
    principal = getattr(request.state, "principal", None)
    lease = request.app.state.admission.acquire(
        None if principal is None else principal.client_id,
        hold_delivery=getattr(request.state, "admission_delivery_owner", False),
    )
    if getattr(request.state, "admission_delivery_owner", False):
        request.state.admission_lease = lease
    return lease


async def _watch_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


def _client_pipeline(request: Request) -> Pipeline:
    if not request.app.state.config.auth.enabled:
        return request.app.state.pipeline
    client_id = request.state.principal.client_id
    pipeline = request.app.state.client_pipelines.get(client_id)
    if pipeline is None:
        # An authenticated client must never fall back to a less restrictive chain.
        raise GatewayError("unavailable")
    return pipeline


async def _run_connected(
    request: Request, payload: ChatRequest, selected_model: str, *, provider_stream: bool = False
) -> Any:
    pipeline = _client_pipeline(request)

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
    lease = _admit_request(request)
    work = None
    try:
        work = operation()
        job = asyncio.create_task(work)
    except BaseException:
        admission.release_unstarted(lease)
        request.scope["state"].pop("admission_lease", None)
        if work is not None:
            work.close()
        raise
    admission.track(job, lease)
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
    except BaseException:
        if disconnected is None:
            admission.rollback_start(lease)
        raise
    finally:
        if disconnected is None and disconnect_work is not None:
            disconnect_work.close()
        tasks = (job,) if disconnected is None else (job, disconnected)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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
            if timer.expired() or time.monotonic() >= self.deadline:
                raise TimeoutError
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
                            retry_after=error.retry_after,
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
        lease = _admit_request(request)
        work = serve()
        try:
            job = asyncio.create_task(work)
        except BaseException:
            work.close()
            admission.release_unstarted(lease)
            request.scope["state"].pop("admission_lease", None)
            raise
        admission.track(job, lease)
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
        except BaseException:
            if disconnected is None:
                admission.rollback_start(lease)
            raise
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
        operator_access = OperatorAccess(active_config)
        usage_ledger = UsageLedger(active_config.auth.clients)
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
            app.state.admission.configure(active_config)
            app.state.access = access
            app.state.operator_access = operator_access
            app.state.usage_ledger = usage_ledger
            app.state.pipeline = Pipeline(
                plugins,
                provider,
                active_config.limits,
                metrics=app.state.metrics,
                provider_name=active_config.provider.kind,
            )
            app.state.client_pipelines = build_client_pipelines(
                active_config, plugins, app.state.pipeline, usage_ledger
            )
            app.state.ready = True
            yield
        except BaseException:
            failed = True
            raise
        finally:
            app.state.ready = False
            app.state.pipeline = None
            app.state.client_pipelines = {}
            app.state.access = None
            app.state.operator_access = None
            app.state.usage_ledger = None

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
    app.router.route_class = _StrictJSONRoute
    app.state.ready = False
    app.state.metrics = Metrics()
    app.state.admission = _PipelineAdmission(app.state.metrics)
    app.state.operator_access = None
    app.state.usage_ledger = None
    app.state.telemetry = Telemetry.disabled()
    app.state.analytics = Analytics.disabled()
    app.state.client_pipelines = {}
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
            retry_after=error.retry_after,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            error.status_code, "invalid_request"
        )
        request.state.http_outcome = code
        request.state.error_code = code
        response = _error_response(
            code, request.state.request_id, openai=_openai_path(request.url.path)
        )
        if error.status_code == 405:
            allowed: set[str] = set()
            for route in app.router.routes:
                if isinstance(route, Route):
                    match, _ = route.matches(request.scope)
                    if match != Match.NONE:
                        allowed.update(route.methods or ())
            if allowed and request.method not in allowed:
                methods = sorted(allowed)
                if all(
                    method
                    in {
                        "GET",
                        "HEAD",
                        "POST",
                        "PUT",
                        "PATCH",
                        "DELETE",
                        "OPTIONS",
                        "TRACE",
                        "CONNECT",
                    }
                    for method in methods
                ):
                    # The matched route owns this protocol value. Exception
                    # headers can contain input or private details, so do not
                    # copy them into the sanitized error response.
                    response.headers["Allow"] = ", ".join(methods)
        return response

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

    @app.get("/operator/usage", include_in_schema=False)
    async def operator_usage() -> JSONResponse:
        return JSONResponse(
            app.state.usage_ledger.snapshot(), headers={"Cache-Control": "no-store"}
        )

    @app.get("/operator/state", include_in_schema=False)
    async def operator_snapshot() -> JSONResponse:
        snapshot = operator_state(
            app.state.config,
            app.state.pipeline,
            app.state.client_pipelines,
            ready=app.state.ready,
        )
        snapshot["usage"] = app.state.usage_ledger.snapshot()
        return JSONResponse(snapshot, headers=CONSOLE_HEADERS)

    @app.get("/operator/console", include_in_schema=False)
    async def operator_console() -> Response:
        return console_asset("index.html")

    @app.get("/operator/assets/console.css", include_in_schema=False)
    async def operator_console_styles() -> Response:
        return console_asset("console.css")

    @app.get("/operator/assets/console.js", include_in_schema=False)
    async def operator_console_script() -> Response:
        return console_asset("console.js")

    @app.post("/chat")
    async def chat(payload: NativeChatRequest, request: Request) -> Response:
        selected = request.state.principal.select_model(
            payload.model, app.state.config.provider.model
        )
        response = await _run_connected(request, payload.core_request(), selected)
        if response is None:
            return Response(status_code=499)
        body = bytes(
            JSONResponse(
                {
                    "text": response.text,
                    "usage": response.usage,
                    "request_id": request.state.request_id,
                }
            ).body
        )
        return _CheckedBody(body, request.state.deadline, media_type="application/json")

    @app.post("/v1/chat/completions")
    async def openai_chat(payload: OpenAIChatRequest, request: Request) -> Response:
        selected = request.state.principal.select_model(
            payload.model, app.state.config.provider.model
        )
        if app.state.config.provider.kind != "openai" and payload.needs_openai_provider():
            raise GatewayError("invalid_request")
        if request.state.stream_mode == "early":
            pipeline = _client_pipeline(request)
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
        body = bytes(
            JSONResponse(completion_response(response, selected, request.state.request_id)).body
        )
        return _CheckedBody(body, request.state.deadline, media_type="application/json")

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
        selected = request.state.principal.select_model(
            payload.model, app.state.config.provider.model
        )
        if app.state.config.provider.kind != "openai":
            raise GatewayError("invalid_request")
        pipeline = _client_pipeline(request)
        if request.state.stream_mode == "early":
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
                lambda: pipeline.run_responses(
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
    async def models(request: Request) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": model, "object": "model", "created": 0, "owned_by": "gateway7"}
                for model in request.state.principal.models
            ],
        }

    return app

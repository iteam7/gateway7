"""FastAPI application with bounded input, sanitized failures, and safe lifecycle."""

import asyncio
import json
import logging
import math
import hashlib
import os
import time
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.datastructures import URL
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match, Route
from starlette.types import ASGIApp, Message as ASGIMessage, Receive, Scope, Send

from gateway7 import __version__
from gateway7.analytics import Analytics
from gateway7.admin_runtime import ClientPolicy, CreateClient
from gateway7.client_policies import build_client_pipelines
from gateway7.config import GatewayConfig, load_config, provider_key, validate_provider_model
from gateway7.auth import AccessControl
from gateway7.errors import GatewayError, ProviderError, StartupError
from gateway7.loader import complete_cleanup, load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest, ChatResponse
from gateway7.metrics import HTTPRequestOutcome, Metrics
from gateway7.management_store import open_management_store
from gateway7.db_execution import DBExecutor
from gateway7.accounting import AccountingService
from gateway7.control_store import ControlConflict
from gateway7.identity_admin import (
    AccountRequest,
    IdentityAdmin,
    KeyRequest,
    OperatorRequest,
    OperatorUpdate,
)
from gateway7.operator_sessions import COOKIE_NAME, OperatorSessions, PasswordRequest, SessionLogin
from gateway7.policy_admin import (
    PolicyAdmin,
    PolicyAssignments,
    PolicyPreview,
    PolicySpec,
    restore_policy_config,
)
from gateway7.openai_api import (
    EarlyChatEncoder,
    NativeChatRequest,
    OpenAIChatRequest,
    completion_response,
    completion_sse,
    error_body,
)
from gateway7.operator_console import CONSOLE_HEADERS, STATIC_ASSETS, console_asset, operator_state
from gateway7.provider_admin import (
    ProviderAdmin,
    ProviderUpdate,
    get_provider_aliases,
    resolve_model_alias,
    restore_provider_config,
    validate_provider_credential,
)
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import EarlyStreamUnsupported, ResponsesUnsupported
from gateway7.providers import CatalogModel, build_provider
from gateway7.responses_api import EarlyResponsesEncoder, response_json, response_sse
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesCreateRequest, ResponsesResponse
from gateway7.telemetry import Telemetry
from gateway7.transport_loader import create_transport, validate_transport_config
from gateway7.usage import OperatorAccess, PersistentUsageLedger, UsageLedger

logger = logging.getLogger("gateway7")
_TIMEOUT_RESPONSE_GRACE_SECONDS = 0.1
_OPERATOR_HEADERS: ContextVar[list[tuple[bytes, bytes]]] = ContextVar(
    "gateway7_operator_headers", default=[]
)


def _public_operator_path(path: str) -> bool:
    return path == "/operator/console" or (
        path.startswith("/operator/assets/")
        and path.removeprefix("/operator/assets/") in STATIC_ASSETS - {"index.html"}
    )


def _expected_revision(headers: list[tuple[bytes, bytes]]) -> int:
    values = [value for name, value in headers if name.lower() == b"if-match"]
    if len(values) != 1:
        raise GatewayError("invalid_request")
    value = values[0].decode("ascii", errors="replace")
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value.isascii() or not value.isdecimal() or len(value) > 18:
        raise GatewayError("invalid_request")
    return int(value)


async def _owned_mutation(
    app: FastAPI, request: Request, operation: Callable[[Any, int], Awaitable[Any]]
) -> Any:
    """Finish the complete commit/publication even if its HTTP caller leaves."""

    async def run() -> Any:
        context = _OPERATOR_HEADERS.set(request.scope.get("headers", []))
        try:
            await _authenticate_operator(app, request.scope)
            actor = app.state.validate_operator(getattr(request.state, "operator", None))
            return await operation(actor, request.state.expected_revision)
        finally:
            _OPERATOR_HEADERS.reset(context)

    task = asyncio.create_task(run(), name="gateway7-owned-management-mutation")
    app.state.management_tasks.add(task)
    task.add_done_callback(app.state.management_tasks.discard)
    cancellation = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancellation = cancellation or error
        except Exception:
            break
    try:
        return task.result()
    finally:
        if cancellation is not None:
            raise cancellation


async def _authenticate_operator(app: FastAPI, scope: Scope) -> Any:
    headers = scope.get("headers", [])
    sessions = getattr(app.state, "operator_sessions", None)
    if sessions is None:
        return app.state.operator_access.authenticate(headers)
    return await sessions.authenticate(headers, scope=scope)


async def _domain(operation: Awaitable[Any]) -> Any:
    try:
        return await operation
    except ControlConflict:
        raise GatewayError("conflict") from None
    except (ValueError, TypeError):
        raise GatewayError("invalid_request") from None
    except StartupError:
        raise GatewayError("unavailable") from None


async def _periodic_retention(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await app.state.accounting.purge()
        except Exception:
            logger.warning("request_id=- outcome=retention_error component=accounting")


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


def _check_operator_write(scope: Scope) -> None:
    headers = scope.get("headers", [])
    marker = [value for name, value in headers if name.lower() == b"x-gateway7-operator"]
    origins = [value for name, value in headers if name.lower() == b"origin"]
    fetch_sites = [value for name, value in headers if name.lower() == b"sec-fetch-site"]
    if marker != [b"true"] or len(origins) > 1 or len(fetch_sites) > 1:
        raise GatewayError("invalid_request")
    if fetch_sites and fetch_sites[0] not in (b"same-origin", b"none"):
        raise GatewayError("invalid_request")
    if origins:
        url = URL(scope=scope)
        expected = f"{url.scheme}://{url.netloc}".encode("ascii")
        if origins[0] != expected:
            raise GatewayError("invalid_request")


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
        started_at = datetime.now(timezone.utc).isoformat()
        scope.setdefault("state", {})["request_id"] = request_id
        scope["state"]["started_at"] = started_at
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
            if route == "ready" and self.owner.state.admin_store is not None:
                try:
                    await _ensure_management_available(self.owner)
                except GatewayError:
                    await fail("unavailable")
                    return
            if scope.get("method") == "GET" and route in ("health", "ready", "metrics"):
                await self.app(scope, receive, safe_send)
                return
            if not getattr(self.owner.state, "ready", False):
                await fail("unavailable")
                return
            if self.owner.state.admin_store is not None and (
                route in ("chat", "openai_chat", "openai_responses", "models")
                or operator_path
                and not _public_operator_path(scope.get("path", ""))
            ):
                try:
                    await _ensure_management_available(self.owner)
                except GatewayError as error:
                    await fail(error.code)
                    return
            if operator_path:
                try:
                    access = self.owner.state.operator_access
                    session_login = (
                        scope.get("path") == "/operator/session" and scope.get("method") == "POST"
                    )
                    session_logout = (
                        scope.get("path") == "/operator/session" and scope.get("method") == "DELETE"
                    )
                    if session_login:
                        if self.owner.state.admin_store is None:
                            raise GatewayError("not_found")
                        _check_operator_write(scope)
                        self.owner.state.operator_sessions.check_transport(scope)
                    elif not _public_operator_path(scope.get("path", "")):
                        actor = await _authenticate_operator(self.owner, scope)
                        scope["state"]["operator"] = actor
                    elif not access.enabled:
                        raise GatewayError("not_found")
                    mutation_path = scope.get("path", "")
                    writable_route = mutation_path.startswith(
                        ("/operator/clients", "/operator/operators")
                    ) or mutation_path in {
                        "/operator/provider",
                        "/operator/provider/test",
                        "/operator/pricing",
                        "/operator/budgets",
                        "/operator/retention",
                    }
                    if scope.get("method") in {"POST", "PUT", "PATCH", "DELETE"} and (
                        self.owner.state.admin_store is not None or writable_route
                    ):
                        if self.owner.state.admin_store is None:
                            raise GatewayError("not_found")
                        if not session_login:
                            _check_operator_write(scope)
                            sessions = self.owner.state.operator_sessions
                            if sessions is not None:
                                sessions.check_csrf(scope.get("headers", []))
                            if not session_logout:
                                actor.require_admin()
                                scope["state"]["expected_revision"] = _expected_revision(
                                    scope.get("headers", [])
                                )
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
            principal = scope["state"].get("principal")
            accounting = getattr(self.owner.state, "accounting", None)
            if accounting is not None and principal is not None and principal.client_id is not None:

                async def persist_diagnostic() -> None:
                    try:
                        await accounting.record_http(
                            client_id=principal.client_id,
                            key_id=getattr(principal, "key_id", None),
                            model=scope["state"].get("selected_model"),
                            started_at=started_at,
                            outcome=outcome.value,
                            duration_ms=int(duration * 1000),
                            request_id=request_id,
                            route=route,
                        )
                    except Exception:
                        self.owner.state.ready = False
                        metrics.ready.set(0)
                        logger.warning(
                            "request_id=%s outcome=diagnostic_storage_error component=accounting",
                            request_id,
                        )

                await complete_cleanup(persist_diagnostic())


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
        self._rate_enabled = set(self._rate_buckets)

    def update(self, config: GatewayConfig) -> None:
        """Replace future policy without releasing active or delivery-owned slots."""
        self.limit = config.limits.max_concurrent_requests
        self._authenticated = config.auth.enabled
        self._client_limits = {
            name: client.limits.max_concurrent_requests
            for name, client in config.auth.clients.items()
            if client.enabled
        }
        for name in self._client_limits:
            self._client_active.setdefault(name, 0)
        now = self._clock()
        for name, client in config.auth.clients.items():
            capacity = client.limits.requests_per_minute
            if not client.enabled or capacity is None:
                continue
            bucket = self._rate_buckets.get(name)
            if bucket is None:
                self._rate_buckets[name] = _RateBucket(capacity, float(capacity), now)
            elif bucket.capacity != capacity:
                elapsed = max(0.0, now - bucket.updated)
                available = min(
                    float(bucket.capacity), bucket.tokens + elapsed * bucket.capacity / 60
                )
                bucket.tokens = min(float(capacity), available)
                bucket.capacity = capacity
                bucket.updated = now
        # Retain retired buckets while leases can still refund their debit.
        self._rate_enabled = {
            name
            for name, client in config.auth.clients.items()
            if client.enabled and client.limits.requests_per_minute is not None
        }

    def _debit_rate(self, client_id: str | None) -> bool:
        bucket = self._rate_buckets.get(client_id) if client_id is not None else None
        if hasattr(self, "_rate_enabled") and client_id not in self._rate_enabled:
            bucket = None
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


async def _select_model(request: Request, requested: str | None) -> str:
    if request.app.state.admin_store is not None:
        await _ensure_management_available(request.app)
        # Body delivery can await while a user is suspended or their token rotates.
        request.state.principal = request.app.state.access.authenticate(
            request.scope.get("headers", [])
        )
    config = request.app.state.config.provider
    default = getattr(request.state.principal, "default_model", None) or config.model
    canonical = resolve_model_alias(
        default if requested is None else requested,
        getattr(request.app.state, "provider_aliases", {}),
    )
    try:
        selected = validate_provider_model(config.kind, canonical)
        request.state.selected_model = selected
        request.state.principal.select_model(selected, default)
        return selected
    except (TypeError, ValueError):
        raise GatewayError("invalid_request") from None


async def _ensure_management_available(app: FastAPI) -> None:
    store = app.state.admin_store
    if store is not None:
        try:
            await app.state.db.call(store.ensure_available)
            app.state.metrics.management_database_available.set(1)
        except StartupError:
            app.state.ready = False
            app.state.metrics.ready.set(0)
            app.state.metrics.management_database_available.set(0)
            raise GatewayError("unavailable") from None


def _client_pipeline(request: Request) -> Pipeline:
    if not request.app.state.config.auth.enabled:
        return request.app.state.pipeline
    client_id = request.state.principal.client_id
    pipeline = request.app.state.client_pipelines.get(client_id)
    if pipeline is None:
        # An authenticated client must never fall back to a less restrictive chain.
        raise GatewayError("unavailable")
    if request.app.state.admin_store is not None:
        before, observer = request.app.state.accounting.bind(
            client_id,
            request.state.selected_model,
            key_id=getattr(request.state.principal, "key_id", None),
            request_id=request.state.request_id,
            route=request.url.path,
        )
        return Pipeline(
            pipeline.plugins,
            pipeline.provider,
            pipeline.limits,
            metrics=pipeline.metrics,
            provider_name=pipeline.provider_name,
            provider_before=before,
            provider_observer=observer,
        )
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
    request: Request,
    operation: Callable[[], Coroutine[Any, Any, PipelineResult]],
    *,
    admit: bool = True,
) -> PipelineResult | None:
    """Own connected work and cleanup, with optional generation admission."""
    admission = request.app.state.admission
    lease = _admit_request(request) if admit else None
    work = None
    try:
        work = operation()
        job = asyncio.create_task(work)
    except BaseException:
        if lease is not None:
            admission.release_unstarted(lease)
            request.scope["state"].pop("admission_lease", None)
        if work is not None:
            work.close()
        raise
    if lease is not None:
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
        if disconnected is None and lease is not None:
            admission.rollback_start(lease)
        raise
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
        app.state.db = DBExecutor()
        active_telemetry = (
            telemetry
            if telemetry is not None
            else Telemetry.from_environment(metrics=app.state.metrics)
        )
        app.state.telemetry = active_telemetry
        active_analytics = Analytics.disabled()
        try:
            active_analytics = (
                analytics
                if analytics is not None
                else Analytics.from_environment(metrics=app.state.metrics)
            )
            await active_analytics.start()
            app.state.analytics = active_analytics
            async with gateway_lifespan(app):
                yield
        finally:
            app.state.analytics = Analytics.disabled()
            try:
                await active_analytics.shutdown()
            finally:
                try:
                    if app.state.operator_sessions is not None:
                        await complete_cleanup(app.state.operator_sessions.passwords.close())
                        app.state.operator_sessions = None
                    if app.state.admin_store is not None:
                        await app.state.db.call(app.state.admin_store.close)
                        app.state.admin_store = None
                    await app.state.db.close()
                finally:
                    app.state.telemetry = Telemetry.disabled()
                    # Flushing performs blocking HTTP export with its own timeout.
                    await asyncio.to_thread(active_telemetry.shutdown)

    @asynccontextmanager
    async def gateway_lifespan(app: FastAPI):
        app.state.ready = False
        active_config = config if config is not None else load_config(path)
        token_digests = None
        if active_config.auth.management_enabled:
            opened = []

            def open_store():
                opened.append(open_management_store(active_config))

            try:
                await app.state.db.call(open_store)
            finally:
                if opened:
                    app.state.admin_store = opened[0]
            store = app.state.admin_store
            clients, token_digests = await app.state.db.call(store.load_clients)
            app.state.control = await app.state.db.call(store.read_control)
            active_config, key = restore_provider_config(
                active_config, app.state.control, clients=clients
            )
            active_config = restore_policy_config(active_config, app.state.control)
            validate_provider_credential(active_config, key, app.state.control, token_digests)
            app.state.provider_aliases = get_provider_aliases(app.state.control)
            usage_ledger: UsageLedger | PersistentUsageLedger = await app.state.db.call(
                PersistentUsageLedger, store, clients
            )
            app.state.accounting = AccountingService(store, app.state.db)
            app.state.accounting.authorize = lambda: app.state.validate_operator()
        else:
            usage_ledger = UsageLedger(active_config.auth.clients)
            key = provider_key(active_config.provider)
        access = AccessControl(active_config, token_digests=token_digests)
        operator_access = OperatorAccess(active_config, token_digests=token_digests)
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
            app.state.token_digests = token_digests or {}
            app.state.provider_credential_digest = hashlib.sha256(key.encode("ascii")).digest()
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
            if active_config.auth.management_enabled:
                await IdentityAdmin(app.state).initialize()
                app.state.operator_sessions = OperatorSessions(app.state)
                await app.state.accounting.purge()
                app.state.retention_task = asyncio.create_task(
                    _periodic_retention(app), name="gateway7-retention"
                )
            app.state.metrics.management_database_available.set(1)
            app.state.ready = True
            app.state.metrics.ready.set(1)
            yield
        except BaseException:
            failed = True
            raise
        finally:
            app.state.ready = False
            app.state.metrics.ready.set(0)
            if app.state.retention_task is not None:
                app.state.retention_task.cancel()
                await asyncio.gather(app.state.retention_task, return_exceptions=True)
                app.state.retention_task = None
            while app.state.management_tasks:
                await asyncio.gather(*app.state.management_tasks, return_exceptions=True)
            if app.state.retired_provider_tasks:
                await asyncio.gather(*app.state.retired_provider_tasks, return_exceptions=True)
            active_pipeline = getattr(app.state, "pipeline", None)
            active_provider = active_pipeline.provider if active_pipeline is not None else provider
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
                        active_provider, active_config.limits.hook_timeout_seconds
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
    app.state.operator_sessions = None
    app.state.usage_ledger = None
    app.state.admin_store = None
    app.state.token_digests = {}
    app.state.telemetry = Telemetry.disabled()
    app.state.analytics = Analytics.disabled()
    app.state.client_pipelines = {}
    app.state.control = {"revision": 0, "data": {}}
    app.state.accounting = None
    app.state.provider_aliases = {}
    app.state.provider_health = {"status": "not_checked"}
    app.state.management_mutation_lock = asyncio.Lock()
    app.state.management_lock = app.state.management_mutation_lock
    app.state.management_tasks = set()
    app.state.retired_provider_tasks = set()
    app.state.retention_task = None

    def validate_operator(expected=None):
        sessions = app.state.operator_sessions
        actor = (
            sessions.authenticate_cached(_OPERATOR_HEADERS.get())
            if sessions is not None
            else app.state.operator_access.authenticate(_OPERATOR_HEADERS.get())
        )
        actor.require_admin()
        if expected is not None and actor.id != expected.id:
            raise GatewayError("operator_forbidden")
        return actor

    app.state.validate_operator = validate_operator

    def retire_provider(provider):
        leases = set(app.state.admission._leases)

        async def retire():
            while leases & app.state.admission._leases:
                await asyncio.sleep(0.01)
            await _close_provider_resource(provider, app.state.config.limits.hook_timeout_seconds)

        task = asyncio.create_task(retire(), name="gateway7-retired-provider")
        app.state.retired_provider_tasks.add(task)
        task.add_done_callback(app.state.retired_provider_tasks.discard)

    app.state.retire_provider = retire_provider
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

    def require_accounting():
        if app.state.accounting is None:
            raise GatewayError("not_found")
        return app.state.accounting

    async def identity_change(request, method, *args):
        return await _domain(
            _owned_mutation(
                app,
                request,
                lambda actor, revision: method(
                    *args,
                    actor=actor,
                    expected_revision=revision,
                    request_id=request.state.request_id,
                ),
            )
        )

    async def accounting_change(request, field, value):
        async def change(actor, revision):
            async with app.state.management_mutation_lock:
                actor = app.state.validate_operator(actor)
                audit = {
                    "actor": actor.id,
                    "action": "accounting." + field,
                    "target": field,
                    "diff": {"fields": [field]},
                    "request_id": request.state.request_id,
                }
                method = getattr(require_accounting(), "update_" + field)
                result = await method(revision, value, audit)
                app.state.control = await app.state.db.call(app.state.admin_store.read_control)
                return result

        return await _domain(_owned_mutation(app, request, change))

    @app.post("/operator/session", include_in_schema=False)
    async def operator_login(payload: SessionLogin, request: Request):
        require_accounting()
        sessions = app.state.operator_sessions
        token, session = await _domain(
            sessions.login(payload, (request.client.host if request.client else "unknown"))
        )
        cookie_headers = [(b"cookie", (COOKIE_NAME + "=" + token).encode("ascii"))]
        response = JSONResponse(
            sessions.view(cookie_headers, sessions._principal(session)), headers=CONSOLE_HEADERS
        )
        maximum = max(
            0,
            int(
                (
                    datetime.fromisoformat(session["expires_at"]) - datetime.now(timezone.utc)
                ).total_seconds()
            ),
        )
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=maximum if payload.remember else None,
            path="/operator",
            secure=app.state.config.auth.session_cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/operator/session", include_in_schema=False)
    async def operator_session(request: Request):
        require_accounting()
        return JSONResponse(
            app.state.operator_sessions.view(
                request.scope.get("headers", []), request.state.operator
            ),
            headers=CONSOLE_HEADERS,
        )

    @app.delete("/operator/session", include_in_schema=False, status_code=204)
    async def operator_logout(request: Request):
        require_accounting()
        await _authenticate_operator(app, request.scope)
        await _domain(app.state.operator_sessions.logout(request.scope.get("headers", [])))
        response = Response(status_code=204, headers=CONSOLE_HEADERS)
        response.delete_cookie(
            COOKIE_NAME,
            path="/operator",
            secure=app.state.config.auth.session_cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.post("/operator/accounts", include_in_schema=False, status_code=201)
    async def operator_create_account(payload: AccountRequest, request: Request):
        return await identity_change(request, IdentityAdmin(app.state).create_account, payload)

    @app.put("/operator/accounts/{operator_id}/password", include_in_schema=False)
    async def operator_reset_password(operator_id: str, payload: PasswordRequest, request: Request):
        return await identity_change(
            request, IdentityAdmin(app.state).reset_password, operator_id, payload
        )

    @app.get("/operator/policies", include_in_schema=False)
    async def operator_policies():
        require_accounting()
        return await _domain(PolicyAdmin(app.state).snapshot())

    @app.post("/operator/policies", include_in_schema=False, status_code=201)
    async def operator_create_policy(payload: PolicySpec, request: Request):
        return await identity_change(request, PolicyAdmin(app.state).create, payload)

    @app.put("/operator/policies/{policy_id}", include_in_schema=False)
    async def operator_update_policy(policy_id: str, payload: PolicySpec, request: Request):
        return await identity_change(request, PolicyAdmin(app.state).update, policy_id, payload)

    @app.delete("/operator/policies/{policy_id}", include_in_schema=False, status_code=204)
    async def operator_delete_policy(policy_id: str, request: Request):
        await identity_change(request, PolicyAdmin(app.state).delete, policy_id)
        return Response(status_code=204)

    @app.put("/operator/policy-assignments", include_in_schema=False)
    async def operator_policy_assignments(payload: PolicyAssignments, request: Request):
        return await identity_change(request, PolicyAdmin(app.state).assignments, payload)

    @app.post("/operator/policy-preview", include_in_schema=False)
    async def operator_policy_preview(payload: PolicyPreview):
        require_accounting()
        return PolicyAdmin.preview(payload)

    @app.get("/operator/usage", include_in_schema=False)
    async def operator_usage(
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
        bucket: str = "day",
        offset: int = 0,
        limit: int = 50,
    ):
        if app.state.accounting is None:
            return JSONResponse(app.state.usage_ledger.snapshot(), headers=CONSOLE_HEADERS)
        return await _domain(
            app.state.accounting.report(
                client_id=client_id,
                model=model,
                start=start,
                end=end,
                bucket=bucket,
                offset=offset,
                limit=limit,
            )
        )

    @app.get("/operator/usage/export", include_in_schema=False)
    async def operator_usage_export(
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ):
        accounting = require_accounting()
        filters = dict(client_id=client_id, model=model, start=start, end=end)
        await _domain(accounting.history(**filters, limit=1))
        return StreamingResponse(
            accounting.iter_csv(**filters),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="gateway7-usage.csv"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/operator/state", include_in_schema=False)
    async def operator_snapshot(request: Request):
        snapshot = operator_state(
            app.state.config, app.state.pipeline, app.state.client_pipelines, ready=app.state.ready
        )
        if app.state.admin_store is not None:
            snapshot.update(
                await _domain(IdentityAdmin(app.state).snapshot(request.state.operator))
            )
            snapshot["usage"] = await _domain(app.state.accounting.report())
        else:
            snapshot["usage"] = app.state.usage_ledger.snapshot()
        return JSONResponse(snapshot, headers=CONSOLE_HEADERS)

    @app.get("/operator/clients", include_in_schema=False)
    async def operator_clients(
        q: str = "",
        search: str = "",
        owner: str = "",
        tag: str = "",
        status: str = "",
        offset: int = 0,
        limit: int = 50,
    ):
        require_accounting()
        return await _domain(
            IdentityAdmin(app.state).list_users(
                q=q or search, owner=owner, tag=tag, status=status, offset=offset, limit=limit
            )
        )

    @app.post("/operator/clients", include_in_schema=False, status_code=201)
    async def operator_create_client(payload: CreateClient, request: Request):
        return await identity_change(request, IdentityAdmin(app.state).create, payload)

    @app.put("/operator/clients/{client_id}", include_in_schema=False)
    async def operator_update_client(client_id: str, payload: ClientPolicy, request: Request):
        return await identity_change(request, IdentityAdmin(app.state).update, client_id, payload)

    @app.post("/operator/clients/{client_id}/token", include_in_schema=False)
    async def operator_rotate_token(client_id: str, request: Request):
        return await identity_change(request, IdentityAdmin(app.state).rotate, client_id)

    @app.delete("/operator/clients/{client_id}/token", include_in_schema=False, status_code=204)
    async def operator_revoke_token(client_id: str, request: Request):
        await identity_change(request, IdentityAdmin(app.state).revoke, client_id)
        return Response(status_code=204)

    @app.delete("/operator/clients/{client_id}", include_in_schema=False, status_code=204)
    async def operator_delete_client(client_id: str, request: Request):
        await identity_change(request, IdentityAdmin(app.state).delete, client_id)
        return Response(status_code=204)

    @app.get("/operator/clients/{client_id}/keys", include_in_schema=False)
    async def operator_client_keys(client_id: str):
        require_accounting()
        return await _domain(IdentityAdmin(app.state).list_keys(client_id))

    @app.post("/operator/clients/{client_id}/keys", include_in_schema=False, status_code=201)
    async def operator_create_key(client_id: str, payload: KeyRequest, request: Request):
        return await identity_change(
            request, IdentityAdmin(app.state).create_key, client_id, payload
        )

    @app.post("/operator/clients/{client_id}/keys/{key_id}/rotate", include_in_schema=False)
    async def operator_rotate_key(
        client_id: str, key_id: str, payload: KeyRequest, request: Request
    ):
        return await identity_change(
            request, IdentityAdmin(app.state).rotate_key, client_id, key_id, payload
        )

    @app.delete(
        "/operator/clients/{client_id}/keys/{key_id}", include_in_schema=False, status_code=204
    )
    async def operator_revoke_key(client_id: str, key_id: str, request: Request):
        await identity_change(request, IdentityAdmin(app.state).revoke_key, client_id, key_id)
        return Response(status_code=204)

    @app.get("/operator/operators", include_in_schema=False)
    async def operator_operators():
        require_accounting()
        return await _domain(IdentityAdmin(app.state).list_operators())

    @app.post("/operator/operators", include_in_schema=False, status_code=201)
    async def operator_create_operator(payload: OperatorRequest, request: Request):
        return await identity_change(request, IdentityAdmin(app.state).create_operator, payload)

    @app.put("/operator/operators/{operator_id}", include_in_schema=False)
    async def operator_update_operator(operator_id: str, payload: OperatorUpdate, request: Request):
        return await identity_change(
            request, IdentityAdmin(app.state).update_operator, operator_id, payload
        )

    @app.delete("/operator/operators/{operator_id}", include_in_schema=False, status_code=204)
    async def operator_revoke_operator(operator_id: str, request: Request):
        await identity_change(request, IdentityAdmin(app.state).revoke_operator, operator_id)
        return Response(status_code=204)

    @app.post("/operator/operators/{operator_id}/token", include_in_schema=False)
    async def operator_rotate_operator(operator_id: str, payload: KeyRequest, request: Request):
        return await identity_change(
            request, IdentityAdmin(app.state).rotate_operator, operator_id, payload
        )

    @app.get("/operator/audit", include_in_schema=False)
    async def operator_audit(
        actor: str | None = None,
        action: str | None = None,
        target: str | None = None,
        start: str | None = None,
        end: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        require_accounting()
        return await _domain(
            app.state.db.call(
                app.state.admin_store.list_audit,
                actor=actor,
                action=action,
                target=target,
                start=start,
                end=end,
                offset=offset,
                limit=limit,
            )
        )

    @app.get("/operator/provider", include_in_schema=False)
    async def operator_provider():
        require_accounting()
        return await _domain(ProviderAdmin(app.state).snapshot())

    @app.put("/operator/provider", include_in_schema=False)
    async def operator_update_provider(payload: ProviderUpdate, request: Request):
        return await _domain(
            _owned_mutation(
                app,
                request,
                lambda actor, revision: ProviderAdmin(app.state).update(
                    payload, revision, actor, request_id=request.state.request_id
                ),
            )
        )

    @app.post("/operator/provider/test", include_in_schema=False)
    async def operator_test_provider(request: Request, payload: ProviderUpdate | None = None):
        return await _domain(
            _owned_mutation(
                app, request, lambda actor, revision: ProviderAdmin(app.state).test(payload, actor)
            )
        )

    @app.get("/operator/models", include_in_schema=False)
    async def operator_models(refresh: bool = False):
        require_accounting()
        return await _domain(ProviderAdmin(app.state).models(refresh=refresh))

    @app.get("/operator/accounting", include_in_schema=False)
    async def operator_accounting():
        return await _domain(require_accounting().policies())

    @app.put("/operator/pricing", include_in_schema=False)
    async def operator_pricing(payload: dict[str, Any], request: Request):
        if set(payload) != {"prices"}:
            raise GatewayError("invalid_request")
        return await accounting_change(request, "pricing", payload["prices"])

    @app.put("/operator/budgets", include_in_schema=False)
    async def operator_budgets(payload: dict[str, Any], request: Request):
        if set(payload) != {"rules"}:
            raise GatewayError("invalid_request")
        return await accounting_change(request, "budgets", payload["rules"])

    @app.get("/operator/budgets/status", include_in_schema=False)
    async def operator_budget_status(client_id: str | None = None, model: str | None = None):
        return await _domain(require_accounting().budget_status(client_id, model))

    @app.put("/operator/retention", include_in_schema=False)
    async def operator_retention(payload: dict[str, Any], request: Request):
        if set(payload) != {"days"}:
            raise GatewayError("invalid_request")
        result = await accounting_change(request, "retention", payload["days"])
        await _domain(require_accounting().purge())
        return result

    @app.get("/operator/diagnostics", include_in_schema=False)
    async def operator_diagnostics(
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        result = await _domain(
            require_accounting().diagnostics(
                client_id=client_id, model=model, start=start, end=end, offset=offset, limit=limit
            )
        )
        admission = app.state.admission
        result["active_requests"] = dict(admission._client_active)
        now = admission._clock()
        result["rate_remaining"] = {
            identity: min(
                bucket.capacity,
                int(bucket.tokens + max(0, now - bucket.updated) * bucket.capacity / 60),
            )
            for identity, bucket in admission._rate_buckets.items()
            if identity in admission._rate_enabled
        }
        return result

    @app.get("/operator/console", include_in_schema=False)
    async def operator_console() -> Response:
        return console_asset("index.html")

    @app.get("/operator/assets/{name}", include_in_schema=False)
    async def operator_console_asset(name: str) -> Response:
        return console_asset(name)

    @app.post("/chat")
    async def chat(payload: NativeChatRequest, request: Request) -> Response:
        selected = await _select_model(request, payload.model)
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
        selected = await _select_model(request, payload.model)
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
                    provider_model=selected,
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
        selected = await _select_model(request, payload.model)
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

            discovered = await _run_connected_operation(request, discover, admit=False)
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

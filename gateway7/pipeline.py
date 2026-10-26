"""Nested async middleware with safe, terminal failures and owned budgets."""

import asyncio
import logging
import time
from typing import Any, Literal, TypeVar

from gateway7.config import LimitsConfig
from gateway7.errors import GatewayError, ProviderError, ProviderErrorReason
from gateway7.loader import LoadedPlugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import Deny, PluginContext

logger = logging.getLogger("gateway7")
Payload = TypeVar("Payload", ChatRequest, ChatResponse)


def _checkpoint(deadline: float) -> None:
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError
    if time.monotonic() >= deadline:
        raise GatewayError("timeout")


def _validated(payload: object, expected: type[Payload]) -> Payload:
    if not isinstance(payload, expected):
        raise ValueError("Invalid payload type")
    # model_copy(update=...) can add undeclared attributes even with extra=forbid;
    # model_dump omits them. Reject such edits instead of silently discarding a
    # plugin's attempted model/control-field injection.
    if set(vars(payload)) - expected.model_fields.keys():
        raise ValueError("Unexpected payload fields")
    # model_copy/model_construct can bypass validation, including mutable children.
    return expected.model_validate(payload.model_dump(mode="python", warnings=False), strict=True)


def _log(
    request_id: str,
    outcome: str,
    component: str,
    phase: str,
    duration: float,
    *,
    reason: ProviderErrorReason | None = None,
) -> None:
    detail = "" if reason is None else " reason=" + ProviderErrorReason.normalize(reason).value
    logger.info(
        "request_id=%s outcome=%s component=%s phase=%s duration_ms=%.3f%s",
        request_id,
        outcome,
        component,
        phase,
        max(duration, 0) * 1000,
        detail,
    )


class Pipeline:
    def __init__(
        self,
        plugins: LoadedPlugins,
        provider: Any,
        limits: LimitsConfig,
        *,
        metrics: Metrics | None = None,
        provider_name: str = "fake",
    ) -> None:
        self.plugins = plugins
        self.provider = provider
        self.limits = limits
        self.metrics = metrics
        self.provider_name = provider_name

    async def run(
        self,
        request: ChatRequest,
        request_id: str,
        *,
        deadline: float | None = None,
        provider_model: str | None = None,
    ) -> ChatResponse:
        deadline = (
            deadline
            if deadline is not None
            else time.monotonic() + self.limits.request_timeout_seconds
        )
        contexts = {
            name: PluginContext(request_id, deadline, {}, instance_name=name)
            for name in self.plugins.instances
        }
        provider_called = False
        provider_usage = None
        provider_finish_reason: Literal["stop", "length"] = "stop"

        async def dispatch(index: int, incoming: ChatRequest) -> ChatResponse:
            nonlocal provider_called, provider_usage, provider_finish_reason
            _checkpoint(deadline)
            if index == len(self.plugins.middleware_chain):
                if provider_called:
                    raise GatewayError("plugin_error")
                provider_called = True
                started = time.monotonic()
                _log(request_id, "start", "provider", "provider", 0)
                try:
                    # Authenticated routing is pinned outside plugin-visible
                    # payloads; concurrent requests never mutate the adapter.
                    response = (
                        await self.provider.complete(incoming)
                        if provider_model is None
                        else await self.provider.complete(incoming, model=provider_model)
                    )
                    try:
                        result = _validated(response, ChatResponse)
                    except (TypeError, ValueError):
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE) from None
                except asyncio.CancelledError:
                    if self.metrics is not None:
                        self.metrics.observe_provider(
                            self.provider_name, "cancelled", time.monotonic() - started
                        )
                    _log(
                        request_id, "cancelled", "provider", "provider", time.monotonic() - started
                    )
                    raise
                except Exception as error:
                    reason = ProviderErrorReason.normalize(
                        error.reason if isinstance(error, ProviderError) else None
                    )
                    if self.metrics is not None:
                        self.metrics.observe_provider(
                            self.provider_name,
                            "provider_error",
                            time.monotonic() - started,
                            error_reason=reason,
                        )
                    _log(
                        request_id,
                        "provider_error",
                        "provider",
                        "provider",
                        time.monotonic() - started,
                        reason=reason,
                    )
                    raise GatewayError("provider_error") from None
                # Snapshot before any middleware can mutate the returned object.
                provider_usage = None if result.usage is None else dict(result.usage)
                provider_finish_reason = result.finish_reason
                if self.metrics is not None:
                    self.metrics.observe_provider(
                        self.provider_name, "complete", time.monotonic() - started, provider_usage
                    )
                _checkpoint(deadline)
                _log(request_id, "complete", "provider", "provider", time.monotonic() - started)
                return result

            plugin = self.plugins.middleware_chain[index]
            context = contexts[plugin.name]
            owner = asyncio.current_task()
            active = True
            called = False
            completed = False
            violation = False
            downstream_failure: BaseException | None = None
            phase = "request"
            remaining = self.limits.hook_timeout_seconds
            segment_started = time.monotonic()
            timer = asyncio.timeout_at(min(deadline, segment_started + remaining))
            _log(request_id, "start", plugin.name, phase, 0)

            def budget_checkpoint() -> None:
                # Checking expired(), not only the monotonic clock, refuses
                # results after an early event-loop timer (notably on Windows).
                if timer.expired():
                    raise GatewayError("timeout")
                _checkpoint(deadline)
                if time.monotonic() - segment_started >= remaining:
                    raise GatewayError("timeout")

            async def call_next(next_request: ChatRequest) -> ChatResponse:
                nonlocal called, completed, violation, downstream_failure
                nonlocal remaining, segment_started, phase
                if (
                    not active
                    or asyncio.current_task() is not owner
                    or called
                    or violation
                    or downstream_failure is not None
                ):
                    violation = True
                    raise GatewayError("plugin_error")
                called = True
                try:
                    budget_checkpoint()
                    validated = _validated(next_request, ChatRequest)
                    budget_checkpoint()
                except BaseException as error:
                    downstream_failure = (
                        error
                        if isinstance(error, (GatewayError, asyncio.CancelledError))
                        else GatewayError("plugin_error")
                    )
                    raise downstream_failure from None
                elapsed = time.monotonic() - segment_started
                remaining -= elapsed
                if remaining <= 0:
                    downstream_failure = GatewayError("timeout")
                    raise downstream_failure
                _log(request_id, "continue", plugin.name, "request", elapsed)
                if self.metrics is not None:
                    self.metrics.observe_middleware(plugin.name, "request", "continue", elapsed)
                timer.reschedule(None)
                try:
                    result = await dispatch(index + 1, validated)
                    completed = True
                    phase = "response"
                    _log(request_id, "start", plugin.name, phase, 0)
                    return result
                except BaseException as error:
                    # An outer plugin cannot turn a failed inner policy/plugin
                    # or provider into success by catching its exception.
                    downstream_failure = error
                    phase = "response"
                    raise
                finally:
                    segment_started = time.monotonic()
                    if not timer.expired():
                        timer.reschedule(min(deadline, segment_started + remaining))

            try:
                try:
                    async with timer:
                        result = await plugin.handle(incoming, context, call_next)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if downstream_failure is not None:
                        raise downstream_failure
                    raise GatewayError("timeout" if timer.expired() else "plugin_error") from None
                if downstream_failure is not None:
                    raise downstream_failure
                budget_checkpoint()
                if violation:
                    raise GatewayError("plugin_error")
                if type(result) is Deny:
                    raise GatewayError("policy_denied")
                if not called or not completed:
                    raise GatewayError("plugin_error")
                try:
                    response = _validated(result, ChatResponse)
                except Exception:
                    raise GatewayError("plugin_error") from None
                budget_checkpoint()
                _log(request_id, "complete", plugin.name, phase, time.monotonic() - segment_started)
                if self.metrics is not None:
                    self.metrics.observe_middleware(
                        plugin.name, phase, "complete", time.monotonic() - segment_started
                    )
                return response
            except asyncio.CancelledError:
                if self.metrics is not None:
                    self.metrics.observe_middleware(
                        plugin.name, phase, "cancelled", time.monotonic() - segment_started
                    )
                _log(
                    request_id, "cancelled", plugin.name, phase, time.monotonic() - segment_started
                )
                raise
            except GatewayError as error:
                if self.metrics is not None:
                    outcome = (
                        "downstream_error"
                        if downstream_failure is not None and phase == "response"
                        else error.code
                    )
                    self.metrics.observe_middleware(
                        plugin.name, phase, outcome, time.monotonic() - segment_started
                    )
                _log(request_id, error.code, plugin.name, phase, time.monotonic() - segment_started)
                raise
            finally:
                active = False

        try:
            total_timer = asyncio.timeout_at(deadline)
            async with total_timer:
                try:
                    request = _validated(request, ChatRequest)
                except Exception:
                    raise GatewayError("invalid_request") from None
                response = await dispatch(0, request)
            if total_timer.expired():
                raise GatewayError("timeout")
            _checkpoint(deadline)
            return ChatResponse(
                text=response.text, usage=provider_usage, finish_reason=provider_finish_reason
            )
        except TimeoutError:
            raise GatewayError("timeout") from None
        finally:
            for context in contexts.values():
                context.state.clear()

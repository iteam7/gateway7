"""Nested async middleware with safe, terminal failures and owned budgets."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar

from gateway7.config import LimitsConfig
from gateway7.errors import (
    GatewayError,
    ProviderError,
    ProviderErrorReason,
    normalized_usage,
    observed_error_usage,
    retain_observed_usage,
)
from gateway7.loader import LoadedPlugin, LoadedPlugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse, NamedToolChoice, StrictPayload
from gateway7.plugin_api import (
    Deny,
    EarlyStreamUnsupported,
    PluginContext,
    ResponsesContext,
    ResponsesUnsupported,
)
from gateway7.responses_events import ResponsesTextDelta, ResponsesTextSink
from gateway7.responses_models import (
    ResponsesConsent,
    ResponsesRequest,
    ResponsesResponse,
    ResponsesUsage,
    _revalidated_state,
    validate_request,
    validate_response,
)
from gateway7.responses_policy import protected_snapshot
from gateway7.usage import ProviderObserver

logger = logging.getLogger("gateway7")
Payload = TypeVar("Payload", ChatRequest, ChatResponse)


def _error_usage(error: BaseException) -> dict[str, int] | None:
    """Take only validated numeric source accounting, including native cancellation."""
    try:
        native = getattr(error, "responses_usage", None)
        if native is not None:
            if type(native) is not ResponsesUsage:
                return None
            native = _revalidated_state(native, ResponsesUsage)
            reported = [native.input_tokens, native.output_tokens]
            if native.input_tokens_details is not None:
                reported.extend(
                    (
                        native.input_tokens_details.cached_tokens,
                        native.input_tokens_details.cache_write_tokens,
                    )
                )
            if native.output_tokens_details is not None:
                reported.append(native.output_tokens_details.reasoning_tokens)
            if native.total_tokens is not None and any(
                count is not None and count > native.total_tokens for count in reported
            ):
                return None
            return normalized_usage(
                {"input_tokens": native.input_tokens, "output_tokens": native.output_tokens}
            )
    except Exception:
        return None
    return observed_error_usage(error)


def _checkpoint(deadline: float) -> None:
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError
    if time.monotonic() >= deadline:
        raise GatewayError("timeout")


def _payload_state(value: Any, ancestors: frozenset[int] = frozenset()) -> Any:
    """Read recursive actual DTO state without serializers or dropped extras."""
    if not isinstance(value, (StrictPayload, dict, list, tuple)):
        return value
    if id(value) in ancestors:
        raise ValueError("Cyclic payload state")
    ancestors = ancestors | {id(value)}
    if isinstance(value, StrictPayload):
        actual = vars(value)
        if set(actual) - type(value).model_fields.keys() or value.__pydantic_extra__:
            raise ValueError("Unexpected payload fields")
        return {name: _payload_state(child, ancestors) for name, child in actual.items()}
    if isinstance(value, dict):
        return {key: _payload_state(child, ancestors) for key, child in value.items()}
    if isinstance(value, tuple):
        return tuple(_payload_state(child, ancestors) for child in value)
    return [_payload_state(child, ancestors) for child in value]


def _validated(payload: object, expected: type[Payload]) -> Payload:
    if not isinstance(payload, expected):
        raise ValueError("Invalid payload type")
    # Copies, constructed instances and mutable children bypass normal validation.
    return expected.model_validate(_payload_state(payload), strict=True)


def _response_contract(incoming: ChatRequest, outgoing: ChatResponse) -> None:
    names = {tool.function.name for tool in incoming.tools}
    old_ids = {call.id for message in incoming.messages for call in message.tool_calls}
    if any(call.function.name not in names or call.id in old_ids for call in outgoing.tool_calls):
        raise ValueError("Provider returned an unadvertised or reused tool call")
    if outgoing.tool_calls and incoming.tool_choice == "none":
        raise ValueError("Tool calls were disabled")
    if isinstance(incoming.tool_choice, NamedToolChoice) and any(
        call.function.name != incoming.tool_choice.function.name for call in outgoing.tool_calls
    ):
        raise ValueError("Provider returned a different named tool")
    if (
        (incoming.tool_choice == "required" or isinstance(incoming.tool_choice, NamedToolChoice))
        and not outgoing.tool_calls
        and outgoing.finish_reason != "length"
    ):
        raise ValueError("Provider omitted a required tool call")


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
        provider_observer: ProviderObserver | None = None,
    ) -> None:
        self.plugins = plugins
        self.provider = provider
        self.limits = limits
        self.metrics = metrics
        self.provider_name = provider_name
        self.provider_observer = provider_observer

    def _observe_provider(
        self,
        outcome: str,
        duration: float,
        usage: dict[str, int] | None = None,
        *,
        error_reason: object = ProviderErrorReason.UNKNOWN,
    ) -> None:
        if self.metrics is not None:
            self.metrics.observe_provider(
                self.provider_name, outcome, duration, usage, error_reason=error_reason
            )
        if self.provider_observer is not None:
            self.provider_observer(outcome, normalized_usage(usage))

    def _tool_capability(self, request: ChatRequest) -> None:
        if request.requires_tools and any(
            not plugin.descriptor.supports_tools for plugin in self.plugins.middleware_chain
        ):
            raise GatewayError("invalid_request")

    async def run(
        self,
        request: ChatRequest,
        request_id: str,
        *,
        deadline: float | None = None,
        provider_model: str | None = None,
        provider_stream: bool = False,
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
        provider_finish_reason: Literal["stop", "length", "tool_calls"] = "stop"
        provider_calls: tuple[tuple[str, str], ...] = ()

        async def dispatch(index: int, incoming: ChatRequest) -> ChatResponse:
            nonlocal provider_called, provider_usage, provider_finish_reason, provider_calls
            _checkpoint(deadline)
            self._tool_capability(incoming)
            if index == len(self.plugins.middleware_chain):
                if provider_called:
                    raise GatewayError("plugin_error")
                provider_called = True
                started = time.monotonic()
                attempt_usage = None
                _log(request_id, "start", "provider", "provider", 0)
                try:
                    # Authenticated routing is pinned outside plugin-visible
                    # payloads; concurrent requests never mutate the adapter.
                    options: dict[str, Any] = {}
                    if provider_model is not None:
                        options["model"] = provider_model
                    if provider_stream:
                        options["stream"] = True
                    response = await self.provider.complete(incoming, **options)
                    if isinstance(response, ChatResponse):
                        attempt_usage = normalized_usage(response.usage)
                    _checkpoint(deadline)
                    if total_timer.expired():
                        raise GatewayError("timeout")
                    try:
                        result = _validated(response, ChatResponse)
                        _response_contract(incoming, result)
                        if result.tool_calls and any(
                            not plugin.descriptor.supports_tools
                            for plugin in self.plugins.middleware_chain
                        ):
                            raise ValueError("Middleware does not support tool payloads")
                    except (TypeError, ValueError):
                        rejected = ProviderError(
                            ProviderErrorReason.INVALID_RESPONSE,
                            usage=attempt_usage,
                        )
                        retain_observed_usage(rejected, attempt_usage)
                        raise rejected from None
                except asyncio.CancelledError as error:
                    self._observe_provider(
                        "cancelled",
                        time.monotonic() - started,
                        _error_usage(error) or attempt_usage,
                    )
                    _log(
                        request_id, "cancelled", "provider", "provider", time.monotonic() - started
                    )
                    raise
                except Exception as error:
                    # A provider can suppress cancellation or return after its
                    # deadline. Account once without converting that interruption.
                    try:
                        _checkpoint(deadline)
                        if total_timer.expired():
                            raise GatewayError("timeout")
                    except (asyncio.CancelledError, GatewayError):
                        self._observe_provider(
                            "cancelled",
                            time.monotonic() - started,
                            _error_usage(error) or attempt_usage,
                        )
                        _log(
                            request_id,
                            "cancelled",
                            "provider",
                            "provider",
                            time.monotonic() - started,
                        )
                        raise
                    reason = ProviderErrorReason.normalize(
                        error.reason if isinstance(error, ProviderError) else None
                    )
                    self._observe_provider(
                        "provider_error",
                        time.monotonic() - started,
                        _error_usage(error),
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
                provider_calls = tuple((call.id, call.function.name) for call in result.tool_calls)
                self._observe_provider("complete", time.monotonic() - started, provider_usage)
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
                    raise GatewayError("policy_denied", middleware=plugin.name)
                if not called or not completed:
                    raise GatewayError("plugin_error")
                try:
                    response = _validated(result, ChatResponse)
                    if (
                        tuple((call.id, call.function.name) for call in response.tool_calls)
                        != provider_calls
                    ):
                        raise ValueError("Middleware changed tool call identity")
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
                text=response.text,
                usage=provider_usage,
                finish_reason=provider_finish_reason,
                tool_calls=response.tool_calls,
            )
        except TimeoutError:
            raise GatewayError("timeout") from None
        finally:
            for context in contexts.values():
                context.state.clear()

    async def run_responses(
        self,
        request: ResponsesRequest,
        request_id: str = "-",
        *,
        deadline: float | None = None,
        provider_model: str | None = None,
        stream: bool = False,
        consent: ResponsesConsent = ResponsesConsent(),
    ) -> ResponsesResponse:
        return await self._run_responses(
            request,
            request_id,
            deadline=deadline,
            provider_model=provider_model,
            stream=stream,
            consent=consent,
            on_text=None,
        )

    async def run_responses_early(
        self,
        request: ResponsesRequest,
        request_id: str = "-",
        *,
        on_text: Callable[[str], Awaitable[None]] | None = None,
        on_text_delta: ResponsesTextSink | None = None,
        deadline: float | None = None,
        provider_model: str | None = None,
        stream: bool = True,
        consent: ResponsesConsent = ResponsesConsent(),
    ) -> ResponsesResponse:
        if stream is not True:
            raise ResponsesUnsupported
        sink = on_text if on_text is not None else on_text_delta
        if (on_text is None) == (on_text_delta is None) or not callable(sink):
            raise GatewayError("invalid_request")
        return await self._run_responses(
            request,
            request_id,
            deadline=deadline,
            provider_model=provider_model,
            stream=stream,
            consent=consent,
            on_text=on_text,
            on_text_delta=on_text_delta,
        )

    async def _run_responses(
        self,
        request: ResponsesRequest,
        request_id: str,
        *,
        deadline: float | None,
        provider_model: str | None,
        stream: bool,
        consent: ResponsesConsent,
        on_text: Callable[[str], Awaitable[None]] | None,
        on_text_delta: ResponsesTextSink | None = None,
    ) -> ResponsesResponse:
        deadline = (
            deadline
            if deadline is not None
            else time.monotonic() + self.limits.request_timeout_seconds
        )
        early = on_text is not None or on_text_delta is not None
        contexts = {
            name: ResponsesContext(request_id, deadline, {}, instance_name=name)
            for name in self.plugins.instances
        }
        remaining = {name: self.limits.hook_timeout_seconds for name in contexts}
        try:
            total_timer = asyncio.timeout_at(deadline)
            async with total_timer:

                def checkpoint(
                    timer: asyncio.Timeout | None = None, own_deadline: float | None = None
                ) -> None:
                    _checkpoint(deadline)
                    if total_timer.expired() or timer is not None and timer.expired():
                        raise GatewayError("timeout")
                    if own_deadline is not None and time.monotonic() >= own_deadline:
                        raise GatewayError("timeout")

                checkpoint()
                hooks: tuple[str, ...] = ("prepare_responses", "check_responses")
                if early:
                    hooks += ("prepare_early_responses",)
                if any(
                    not callable(getattr(plugin, name))
                    for plugin in self.plugins.middleware_chain
                    for name in hooks
                ):
                    raise ResponsesUnsupported
                method = "complete_responses_early" if early else "complete_responses"
                complete = getattr(self.provider, method, None)
                if (
                    self.provider_name != "openai"
                    or getattr(self.provider, "_kind", "openai") != "openai"
                    or not callable(complete)
                ):
                    raise ResponsesUnsupported
                try:
                    if type(consent) is not ResponsesConsent or type(stream) is not bool:
                        raise ValueError("Invalid native authority")
                    # Snapshot authority outside every plugin-visible object.
                    consent = ResponsesConsent.model_validate(consent)
                    request = validate_request(request, consent=consent)
                    request_snapshot = protected_snapshot(request)
                except Exception:
                    checkpoint()
                    raise GatewayError("invalid_request") from None

                def checked_request(value: Any) -> ResponsesRequest:
                    checked = validate_request(value, consent=consent)
                    if protected_snapshot(checked) != request_snapshot:
                        raise ValueError("Middleware changed protected native request data")
                    return checked

                async def run_hook(
                    plugin: LoadedPlugin,
                    hook_name: str,
                    value: Any,
                    phase: str,
                    validate: Callable[[Any], Any],
                ) -> Any:
                    checkpoint()
                    started = time.monotonic()
                    own_deadline = min(deadline, started + remaining[plugin.name])
                    timer = asyncio.timeout_at(own_deadline)
                    outcome = "continue" if phase == "request" else "complete"
                    _log(request_id, "start", plugin.name, phase, 0)
                    try:
                        try:
                            checkpoint(timer, own_deadline)
                            async with timer:
                                result = await getattr(plugin, hook_name)(
                                    value, contexts[plugin.name]
                                )
                        except asyncio.CancelledError:
                            raise
                        except Exception as error:
                            checkpoint(timer, own_deadline)
                            if isinstance(error, ResponsesUnsupported):
                                raise ResponsesUnsupported from None
                            raise GatewayError("plugin_error") from None
                        checkpoint(timer, own_deadline)
                        if type(result) is Deny:
                            raise GatewayError("policy_denied")
                        try:
                            result = validate(result)
                        except Exception:
                            checkpoint(timer, own_deadline)
                            raise GatewayError("plugin_error") from None
                        checkpoint(timer, own_deadline)
                        return result
                    except asyncio.CancelledError:
                        outcome = "cancelled"
                        raise
                    except ResponsesUnsupported:
                        outcome = "invalid_request"
                        raise
                    except GatewayError as error:
                        outcome = error.code
                        raise
                    finally:
                        elapsed = time.monotonic() - started
                        remaining[plugin.name] -= elapsed
                        _log(request_id, outcome, plugin.name, phase, elapsed)
                        if self.metrics is not None:
                            self.metrics.observe_middleware(plugin.name, phase, outcome, elapsed)

                request_hook = "prepare_early_responses" if early else "prepare_responses"
                for plugin in self.plugins.middleware_chain:
                    request = await run_hook(
                        plugin, request_hook, request, "request", checked_request
                    )
                checkpoint()
                outgoing = validate_request(request, consent=consent)
                checkpoint()
                started = time.monotonic()
                active = True
                _log(request_id, "start", "provider", "provider", 0)

                async def forward_text(text: str) -> None:
                    checkpoint()
                    if not active or type(text) is not str or on_text is None:
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                    await on_text(text)
                    checkpoint()

                async def forward_text_delta(record: ResponsesTextDelta) -> None:
                    checkpoint()
                    if (
                        not active
                        or type(record) is not ResponsesTextDelta
                        or on_text_delta is None
                    ):
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                    await on_text_delta(record)
                    checkpoint()

                def record_provider(
                    outcome: str,
                    usage: dict[str, int] | None = None,
                    reason: ProviderErrorReason | None = None,
                ) -> None:
                    elapsed = time.monotonic() - started
                    self._observe_provider(outcome, elapsed, usage, error_reason=reason)
                    _log(request_id, outcome, "provider", "provider", elapsed, reason=reason)

                try:
                    options: dict[str, Any] = {"consent": consent}
                    if provider_model is not None:
                        options["model"] = provider_model
                    if not early:
                        options["stream"] = stream
                    elif on_text_delta is not None:
                        options["on_text_delta"] = forward_text_delta
                    else:
                        options["on_text"] = forward_text
                    raw_response = await complete(outgoing, **options)
                    checkpoint()
                    validated_usage = None
                    try:
                        if type(raw_response) is not ResponsesResponse:
                            raise ValueError("Expected a native Responses response")
                        # Validate all actual DTO state before reading accounting.
                        # A later request-relative tool check can reject paid output.
                        response = _revalidated_state(raw_response, ResponsesResponse)
                        validated_usage = response.accounting_usage()
                        response = validate_response(request, response, consent=consent)
                    except (ValueError, TypeError):
                        rejected = ProviderError(
                            ProviderErrorReason.INVALID_RESPONSE, usage=validated_usage
                        )
                        retain_observed_usage(rejected, validated_usage)
                        raise rejected from None
                    checkpoint()
                except asyncio.CancelledError as error:
                    record_provider("cancelled", _error_usage(error))
                    raise
                except Exception as error:
                    try:
                        checkpoint()
                    except (asyncio.CancelledError, GatewayError):
                        record_provider("cancelled", _error_usage(error))
                        raise
                    if isinstance(error, GatewayError) and error.code == "timeout":
                        record_provider("cancelled", _error_usage(error))
                        raise
                    reason = ProviderErrorReason.normalize(
                        error.reason if isinstance(error, ProviderError) else None
                    )
                    record_provider(
                        "provider_error",
                        _error_usage(error),
                        reason,
                    )
                    raise GatewayError("provider_error") from None
                finally:
                    active = False
                record_provider("complete", validated_usage)
                response_snapshot = protected_snapshot(response)

                def checked_response(value: Any) -> ResponsesResponse:
                    checked = validate_response(request, value, consent=consent)
                    if protected_snapshot(checked) != response_snapshot:
                        raise ValueError("Middleware changed protected native response data")
                    return checked

                if not early:
                    for plugin in reversed(self.plugins.middleware_chain):
                        response = await run_hook(
                            plugin, "check_responses", response, "response", checked_response
                        )
                checkpoint()
                return response
        except TimeoutError:
            raise GatewayError("timeout") from None
        finally:
            for context in contexts.values():
                context.state.clear()

    async def run_early(
        self,
        request: ChatRequest,
        request_id: str = "-",
        *,
        on_text: Callable[[str], Awaitable[None]],
        deadline: float | None = None,
        provider_model: str | None = None,
    ) -> ChatResponse:
        """Prepare an explicitly compatible request chain before emitting text."""
        deadline = (
            deadline
            if deadline is not None
            else time.monotonic() + self.limits.request_timeout_seconds
        )
        contexts = {
            name: PluginContext(request_id, deadline, {}, instance_name=name)
            for name in self.plugins.instances
        }
        try:
            total_timer = asyncio.timeout_at(deadline)
            async with total_timer:
                _checkpoint(deadline)
                # Inspect the whole chain before executing any request hook. A
                # legacy handle remains valid for buffered runs, not this path.
                if any(
                    plugin.prepare_early_stream is None for plugin in self.plugins.middleware_chain
                ):
                    raise EarlyStreamUnsupported
                complete_early = getattr(self.provider, "complete_early", None)
                if self.provider_name != "openai" or not callable(complete_early):
                    raise EarlyStreamUnsupported
                try:
                    request = _validated(request, ChatRequest)
                except Exception:
                    raise GatewayError("invalid_request") from None
                self._tool_capability(request)

                for plugin in self.plugins.middleware_chain:
                    _checkpoint(deadline)
                    started = time.monotonic()
                    hook_deadline = min(deadline, started + self.limits.hook_timeout_seconds)
                    timer = asyncio.timeout_at(hook_deadline)
                    _log(request_id, "start", plugin.name, "request", 0)

                    def budget_checkpoint() -> None:
                        if timer.expired():
                            raise GatewayError("timeout")
                        _checkpoint(deadline)
                        if time.monotonic() >= hook_deadline:
                            raise GatewayError("timeout")

                    outcome = "continue"
                    try:
                        try:
                            async with timer:
                                hook = plugin.prepare_early_stream
                                assert hook is not None
                                result = await hook(request, contexts[plugin.name])
                        except asyncio.CancelledError:
                            raise
                        except Exception as error:
                            budget_checkpoint()
                            if isinstance(error, EarlyStreamUnsupported):
                                raise EarlyStreamUnsupported from None
                            raise GatewayError("plugin_error") from None
                        budget_checkpoint()
                        if type(result) is Deny:
                            raise GatewayError("policy_denied", middleware=plugin.name)
                        try:
                            request = _validated(result, ChatRequest)
                        except Exception:
                            budget_checkpoint()
                            raise GatewayError("plugin_error") from None
                        budget_checkpoint()
                        self._tool_capability(request)
                        budget_checkpoint()
                    except asyncio.CancelledError:
                        outcome = "cancelled"
                        raise
                    except EarlyStreamUnsupported:
                        outcome = "invalid_request"
                        raise
                    except GatewayError as error:
                        outcome = error.code
                        raise
                    finally:
                        duration = time.monotonic() - started
                        _log(request_id, outcome, plugin.name, "request", duration)
                        if self.metrics is not None:
                            self.metrics.observe_middleware(
                                plugin.name, "request", outcome, duration
                            )

                _checkpoint(deadline)
                started = time.monotonic()
                _log(request_id, "start", "provider", "provider", 0)
                stream_active = True

                async def forward_text(text: str) -> None:
                    _checkpoint(deadline)
                    if not stream_active or type(text) is not str:
                        raise ProviderError(ProviderErrorReason.INVALID_RESPONSE)
                    await on_text(text)
                    _checkpoint(deadline)

                def record_provider(
                    outcome: str,
                    usage: dict[str, int] | None = None,
                    reason: ProviderErrorReason | None = None,
                ) -> None:
                    duration = time.monotonic() - started
                    self._observe_provider(outcome, duration, usage, error_reason=reason)
                    _log(request_id, outcome, "provider", "provider", duration, reason=reason)

                try:
                    options: dict[str, Any] = {}
                    if provider_model is not None:
                        options["model"] = provider_model
                    response = await complete_early(request, on_text=forward_text, **options)
                    try:
                        validated = _validated(response, ChatResponse)
                        _response_contract(request, validated)
                        if validated.tool_calls and any(
                            not plugin.descriptor.supports_tools
                            for plugin in self.plugins.middleware_chain
                        ):
                            raise ValueError("Middleware does not support tool payloads")
                    except (TypeError, ValueError):
                        rejected = ProviderError(
                            ProviderErrorReason.INVALID_RESPONSE,
                            usage=response.usage if isinstance(response, ChatResponse) else None,
                        )
                        retain_observed_usage(
                            rejected, response.usage if isinstance(response, ChatResponse) else None
                        )
                        raise rejected from None
                except asyncio.CancelledError as error:
                    record_provider("cancelled", _error_usage(error))
                    raise
                except Exception as error:
                    # A provider or callback may replace cancellation with an
                    # ordinary exception; the request's interruption still wins.
                    try:
                        _checkpoint(deadline)
                        if total_timer.expired():
                            raise GatewayError("timeout")
                    except (asyncio.CancelledError, GatewayError):
                        record_provider("cancelled", _error_usage(error))
                        raise
                    if isinstance(error, GatewayError) and error.code == "timeout":
                        record_provider("cancelled", _error_usage(error))
                        raise
                    reason = ProviderErrorReason.normalize(
                        error.reason if isinstance(error, ProviderError) else None
                    )
                    record_provider(
                        "provider_error",
                        _error_usage(error),
                        reason,
                    )
                    raise GatewayError("provider_error") from None
                finally:
                    stream_active = False
                usage = None if validated.usage is None else dict(validated.usage)
                record_provider("complete", usage)
                _checkpoint(deadline)
                response = ChatResponse(
                    text=validated.text,
                    usage=usage,
                    finish_reason=validated.finish_reason,
                    tool_calls=validated.tool_calls,
                )
            if total_timer.expired():
                raise GatewayError("timeout")
            _checkpoint(deadline)
            return response
        except TimeoutError:
            raise GatewayError("timeout") from None
        finally:
            for context in contexts.values():
                context.state.clear()

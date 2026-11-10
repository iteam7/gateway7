"""One-attempt native Responses transport on the gateway's owned HTTP client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import math
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import TypeAdapter

from gateway7.config import ModelId
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.provider_stream import OwnedCloseStream
from gateway7.responses_events import ResponsesTextDelta, ResponsesTextSink
from gateway7.responses_models import (
    ResponseFunctionTool,
    ResponseFunctionToolEchoes,
    ResponseNamespaceTool,
    ResponsesConsent,
    ResponsesModel,
    ResponsesRequest,
    ResponsesResponse,
    ResponsesUsage,
    _revalidated_state,
    project_provider_response,
    validate_request,
    validate_response,
)
from gateway7.responses_stream import MAX_RESPONSE_BYTES, ResponsesStream

if TYPE_CHECKING:
    from gateway7.providers import HTTPProvider

_MODEL = TypeAdapter(ModelId)


def _reported_usage(value: object) -> ResponsesUsage | None:
    try:
        usage = ResponsesUsage.model_validate(value)
    except (ValueError, TypeError):
        return None
    counts = [usage.input_tokens, usage.output_tokens, usage.total_tokens]
    if usage.input_tokens_details is not None:
        counts.extend(
            (
                usage.input_tokens_details.cached_tokens,
                usage.input_tokens_details.cache_write_tokens,
            )
        )
    if usage.output_tokens_details is not None:
        counts.append(usage.output_tokens_details.reasoning_tokens)
    return usage if any(count is not None for count in counts) else None


def _accounting(usage: ResponsesUsage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    counts = {
        name: count
        for name in ("input_tokens", "output_tokens")
        if (count := getattr(usage, name)) is not None
    }
    return counts or None


class ResponsesProviderError(ProviderError):
    """Safe native failure, including source-reported partial and detailed usage."""

    def __init__(self, reason: object, *, usage: ResponsesUsage | None = None) -> None:
        super().__init__(reason)
        self._responses_usage = None if usage is None else usage.model_copy(deep=True)

    @property
    def responses_usage(self) -> ResponsesUsage | None:
        return (
            None if self._responses_usage is None else self._responses_usage.model_copy(deep=True)
        )

    @property
    def usage(self) -> dict[str, int] | None:
        return _accounting(self._responses_usage)


def _callback_usage(error: BaseException, usage: ResponsesUsage | None) -> None:
    """Keep exception identity while exposing a detached native accounting snapshot."""
    snapshot = None if usage is None else usage.model_copy(deep=True)
    if isinstance(error, ResponsesProviderError):
        error._responses_usage = snapshot
    else:
        try:
            setattr(error, "responses_usage", snapshot)
        except Exception:
            # A callback exception can forbid attributes; it still owns precedence.
            pass


def _http_reason(status: int) -> ProviderErrorReason:
    if status in (401, 403):
        return ProviderErrorReason.AUTHENTICATION
    if status == 429:
        return ProviderErrorReason.RATE_LIMIT
    if 500 <= status < 600:
        return ProviderErrorReason.UNAVAILABLE
    return ProviderErrorReason.REJECTED


def _failure_reason(code: str) -> ProviderErrorReason:
    return {
        "rate_limit_exceeded": ProviderErrorReason.RATE_LIMIT,
        "insufficient_quota": ProviderErrorReason.RATE_LIMIT,
        "server_error": ProviderErrorReason.UNAVAILABLE,
        "server_is_overloaded": ProviderErrorReason.UNAVAILABLE,
        "invalid_prompt": ProviderErrorReason.REJECTED,
        "context_length_exceeded": ProviderErrorReason.REJECTED,
        "bio_policy": ProviderErrorReason.REJECTED,
        "cyber_policy": ProviderErrorReason.REJECTED,
    }.get(code, ProviderErrorReason.INVALID_RESPONSE)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON object key")
        result[name] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("Invalid JSON number")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Invalid JSON number")
    return result


def _json_body(body: bytearray) -> dict[str, Any]:
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ResponsesProviderError(ProviderErrorReason.INVALID_RESPONSE) from None


def _control_snapshot(value: Any) -> str:
    def snapshot(item: ResponsesModel) -> dict[str, Any]:
        # Compare request authority only; wire/head/final snapshots keep all echoes.
        if isinstance(item, ResponseFunctionTool):
            checked = _revalidated_state(item, ResponseFunctionTool)
            return checked.model_dump(
                mode="json", by_alias=True, exclude=set(ResponseFunctionToolEchoes.model_fields)
            )
        if isinstance(item, ResponseNamespaceTool):
            checked_namespace = _revalidated_state(item, ResponseNamespaceTool)
            result = checked_namespace.model_dump(mode="json", by_alias=True)
            result["tools"] = [snapshot(child) for child in checked_namespace.tools]
            return result
        return item.model_dump(mode="json", by_alias=True)

    if isinstance(value, ResponsesModel):
        value = snapshot(value)
    elif isinstance(value, (list, tuple)):
        value = [snapshot(item) for item in value]
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def _check_text_delta(
    record: ResponsesTextDelta,
    controls: dict[str, str],
    history_ids: set[str],
) -> None:
    try:
        if type(record) is not ResponsesTextDelta:
            raise ValueError
        checked = ResponsesTextDelta.model_validate(record)
        if checked.item_id in history_ids:
            raise ValueError
        for name, expected in controls.items():
            actual = getattr(checked.head, name)
            if actual is not None and _control_snapshot(actual) != expected:
                raise ValueError
    except (ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
        raise ResponsesProviderError(ProviderErrorReason.INVALID_RESPONSE) from None


async def complete_responses_early(
    provider: HTTPProvider,
    request: ResponsesRequest,
    *,
    model: str | None = None,
    consent: ResponsesConsent = ResponsesConsent(),
    on_text: Callable[[str], Awaitable[None]] | None = None,
    on_text_delta: ResponsesTextSink | None = None,
) -> ResponsesResponse:
    sink = on_text if on_text is not None else on_text_delta
    if (on_text is None) == (on_text_delta is None) or not callable(sink):
        raise ResponsesProviderError(ProviderErrorReason.REJECTED)
    return await complete_responses(
        provider,
        request,
        model=model,
        stream=True,
        consent=consent,
        on_text=on_text,
        on_text_delta=on_text_delta,
    )


async def complete_responses(
    provider: HTTPProvider,
    request: ResponsesRequest,
    *,
    model: str | None = None,
    stream: bool = False,
    consent: ResponsesConsent = ResponsesConsent(),
    on_text: Callable[[str], Awaitable[None]] | None = None,
    on_text_delta: ResponsesTextSink | None = None,
) -> ResponsesResponse:
    """Preserve native DTOs; callbacks contain only event-validated output text.

    Callback failures/cancellation retain their identity and receive a
    ``responses_usage`` snapshot. All other failures use ResponsesProviderError.
    Routing and consent are snapshotted before the single outbound request.
    """
    if provider._kind != "openai" or type(stream) is not bool:
        raise ResponsesProviderError(ProviderErrorReason.REJECTED)
    try:
        bound_consent = ResponsesConsent.model_validate(consent)
        incoming = validate_request(request, consent=bound_consent)
        bound_model = _MODEL.validate_python(
            provider._model if model is None else model, strict=True
        )
    except (ValueError, TypeError, RecursionError):
        raise ResponsesProviderError(ProviderErrorReason.REJECTED) from None
    payload = {**incoming.wire_dict(), "model": bound_model, "stream": stream, "store": False}
    controls: dict[str, str] = {}
    history_ids: set[str] = set()
    if on_text is not None or on_text_delta is not None:
        controls = {
            name: _control_snapshot(getattr(incoming, name))
            for name in ("parallel_tool_calls", "tool_choice", "tools")
        }
        history = incoming.input if isinstance(incoming.input, list) else []
        history_ids = {item.id for item in history if item.id is not None}
    streamed = ResponsesStream() if stream else None
    body = bytearray()
    usage: ResponsesUsage | None = None
    primary_error: BaseException | None = None
    callback_active = False
    try:
        async with provider._client.stream(
            "POST",
            provider._origin + "/v1/responses",
            json=payload,
            headers=provider._headers,
        ) as wire:
            try:
                if not isinstance(wire.stream, httpx.AsyncByteStream):
                    raise ResponsesProviderError(ProviderErrorReason.INVALID_RESPONSE)
                wire.stream = OwnedCloseStream(wire.stream)
                if wire.status_code != 200:
                    raise ResponsesProviderError(_http_reason(wire.status_code))
                media_type = wire.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if media_type != ("text/event-stream" if stream else "application/json"):
                    raise ResponsesProviderError(ProviderErrorReason.INVALID_RESPONSE)
                if streamed is not None:
                    async for chunk in wire.aiter_bytes():
                        streamed.feed(chunk)
                        if on_text is not None or on_text_delta is not None:
                            for record in streamed.drain_text_deltas():
                                _check_text_delta(record, controls, history_ids)
                                callback_active = True
                                if on_text_delta is not None:
                                    await on_text_delta(record)
                                else:
                                    assert on_text is not None
                                    await on_text(record.delta)
                                callback_active = False
                    data = streamed.finish()
                else:
                    async for chunk in wire.aiter_bytes():
                        if len(chunk) > MAX_RESPONSE_BYTES - len(body):
                            raise ResponsesProviderError(ProviderErrorReason.INVALID_RESPONSE)
                        body.extend(chunk)
                    data = _json_body(body)
                usage = _reported_usage(data.get("usage"))
                try:
                    if streamed is None:
                        data = project_provider_response(data)
                    answer = validate_response(
                        incoming,
                        ResponsesResponse.model_validate(data),
                        consent=bound_consent,
                    )
                except (ValueError, TypeError, RecursionError, UnicodeError):
                    raise ResponsesProviderError(
                        ProviderErrorReason.INVALID_RESPONSE, usage=usage
                    ) from None
                if answer.status == "failed":
                    assert answer.error is not None
                    raise ResponsesProviderError(_failure_reason(answer.error.code), usage=usage)
            except BaseException as body_error:
                primary_error = body_error
                raise
        return answer
    except BaseException as caught_error:
        error = primary_error if primary_error is not None else caught_error
        if streamed is not None:
            usage = _reported_usage(streamed.native_usage)
        elif usage is None and body:
            try:
                usage = _reported_usage(_json_body(body).get("usage"))
            except ResponsesProviderError:
                pass
        if callback_active or not isinstance(error, Exception):
            _callback_usage(error, usage)
            raise error from None
        if isinstance(error, ProviderError):
            reason = error.reason
        elif isinstance(error, httpx.TimeoutException):
            reason = ProviderErrorReason.TIMEOUT
        elif isinstance(error, httpx.DecodingError):
            reason = ProviderErrorReason.INVALID_RESPONSE
        elif isinstance(error, httpx.TransportError):
            reason = ProviderErrorReason.TRANSPORT
        else:
            reason = ProviderErrorReason.UNKNOWN
        raise ResponsesProviderError(reason, usage=usage) from None

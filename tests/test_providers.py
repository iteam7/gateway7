"""Adapter checks use mock HTTP transports, never live provider credentials."""

import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from gateway7.config import ProviderConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.models import ChatRequest, Message
from gateway7.providers import MAX_RESPONSE_BYTES, build_provider, validate_provider_config


KEY = "gateway7-synthetic-test-only"
REQUEST = ChatRequest(messages=[Message(role="user", content="ping")])


@asynccontextmanager
async def mocked_provider(handler, *, kind="fake"):
    config = ProviderConfig(
        kind=kind,
        model="configured-test-model",
    )
    provider = build_provider(config, KEY)
    await provider.aclose()
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False
    )
    try:
        yield provider
    finally:
        await provider.aclose()


async def test_fake_sends_header_key_and_normalized_body_once():
    requests = []

    def handle(request):
        requests.append(request)
        assert str(request.url) == "http://127.0.0.1:8001/chat"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert KEY not in request.content.decode() and KEY not in str(request.url)
        assert json.loads(request.content) == REQUEST.model_dump(mode="json")
        return httpx.Response(200, json={"text": "pong", "usage": {"input_tokens": 3, "output_tokens": 1}})

    async with mocked_provider(handle) as provider:
        answer = await provider.complete(REQUEST)
        assert answer.text == "pong"
        assert answer.usage == {"input_tokens": 3, "output_tokens": 1}
    assert len(requests) == 1
    assert provider._client.is_closed


async def test_claude_messages_headers_system_and_response_normalization():
    seen = []

    def handle(request):
        seen.append(request)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == KEY
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        assert KEY not in request.content.decode()
        assert json.loads(request.content) == {
            "model": "configured-test-model", "max_tokens": 32,
            "system": "first system\n\nsecond system",
            "messages": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "reply"}],
        }
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 4, "service_tier": "standard"},
        })

    request = ChatRequest(messages=[
        Message(role="system", content="first system"),
        Message(role="user", content="hello"),
        Message(role="system", content="second system"),
        Message(role="assistant", content="reply"),
    ], max_tokens=32)
    async with mocked_provider(handle, kind="claude") as provider:
        answer = await provider.complete(request)
    assert answer.text == "hello world"
    assert answer.usage == {"input_tokens": 12, "output_tokens": 4}
    assert len(seen) == 1


@pytest.mark.parametrize("usage", [None, "unknown", {"input_tokens": True}, {"output_tokens": -1}, {"input_tokens": "12"}])
@pytest.mark.parametrize("kind", ["fake", "claude"])
async def test_unavailable_or_invalid_usage_is_unknown(kind, usage):
    body = {"text": "pong", "content": [{"type": "text", "text": "pong"}], "stop_reason": "end_turn", "usage": usage}
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind=kind) as provider:
        assert (await provider.complete(REQUEST)).usage is None


@pytest.mark.parametrize("status,body", [
    (500, KEY.encode()), (401, KEY.encode()), (302, b"redirect"),
    (200, b"not-json"), (200, b"[]"), (200, b'{"text": 42}'), (200, b'{"text": ""}'),
    (200, b"x" * (MAX_RESPONSE_BYTES + 1)),
], ids=[
    "500-echoes-key", "401-echoes-key", "302-redirect",
    "200-not-json", "200-array", "200-non-string-text", "200-empty-text",
    # A derived ID would hold the whole body and exceed Windows' environment-variable limit.
    "200-oversized",
])
async def test_upstream_failures_are_safe_bounded_and_never_retried(status, body):
    attempts = 0

    def handle(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, content=body, headers={"location": "https://untrusted.invalid"})

    async with mocked_provider(handle) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
    assert str(caught.value) == "Provider request failed"
    assert KEY not in str(caught.value)
    assert attempts == 1


@pytest.mark.parametrize("body", [
    {}, {"content": []}, {"content": [{"type": "text", "text": 1}]},
    {"content": [{"type": "tool_use", "name": "unknown"}]},
])
async def test_claude_invalid_content_is_a_safe_error(body):
    body = {**body, "stop_reason": "end_turn"}
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="claude") as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)


async def test_network_error_does_not_expose_raw_exception_or_retry():
    attempts = 0

    def handle(request):
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("untrusted upstream error " + KEY, request=request)

    async with mocked_provider(handle) as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)
    assert attempts == 1


async def test_cancellation_reaches_transport_without_retry():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handle(_):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async with mocked_provider(handle) as provider:
        task = asyncio.create_task(provider.complete(REQUEST))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()


@pytest.mark.parametrize("kind,url", [
    ("fake", "http://example.com"), ("fake", "https://127.0.0.1"),
    ("fake", "http://127.0.0.1/path"), ("fake", "http://127.0.0.1?key=secret"),
    ("fake", "http://key:secret@127.0.0.1"), ("fake", "http://127.0.0.1#fragment"),
    ("claude", "http://api.anthropic.com"), ("claude", "https://other.example"),
    ("claude", "https://api.anthropic.com.evil.example"),
    ("claude", "https://api.anthropic.com:444"),
    ("claude", "https://api.anthropic.com/v1/messages"),
])
def test_only_fixed_real_origin_or_literal_loopback_fake_is_allowed(kind, url):
    with pytest.raises(ValueError, match="^Invalid provider origin$"):
        build_provider(ProviderConfig(kind=kind, base_url=url), KEY)


@pytest.mark.parametrize("key", ["", "with space", "line\nbreak", "non-ascii-ключ"])
def test_invalid_key_values_have_a_constant_safe_error(key):
    with pytest.raises(ValueError, match="^Invalid provider key$"):
        build_provider(ProviderConfig(), key)


def openai_reply(**overrides):
    return {
        "choices": [{
            "message": {"role": "assistant", "content": "pong", "refusal": None},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        **overrides,
    }


def gemini_reply(**overrides):
    return {
        "candidates": [{
            "content": {"role": "model", "parts": [{"text": "pong"}]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4},
        **overrides,
    }


async def test_openai_headers_payload_history_and_usage():
    seen = []
    request = ChatRequest(messages=[
        Message(role="system", content="use short answers"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="hello"),
        Message(role="user", content="ping"),
    ], max_tokens=17)

    def handle(wire):
        seen.append(wire)
        assert str(wire.url) == "https://api.openai.com/v1/chat/completions"
        assert wire.headers["authorization"] == "Bearer " + KEY
        assert "x-api-key" not in wire.headers and "x-goog-api-key" not in wire.headers
        assert KEY not in wire.content.decode() and KEY not in str(wire.url)
        assert json.loads(wire.content) == {
            "model": "configured-test-model",
            "messages": [message.model_dump() for message in request.messages],
            "max_completion_tokens": 17,
            "stream": False,
            "store": False,
        }
        return httpx.Response(200, json=openai_reply())

    async with mocked_provider(handle, kind="openai") as provider:
        answer = await provider.complete(request)
    assert len(seen) == 1
    assert answer.text == "pong"
    assert answer.usage == {"input_tokens": 3, "output_tokens": 1}


async def test_gemini_system_history_headers_and_usage_with_thinking():
    seen = []
    request = ChatRequest(messages=[
        Message(role="system", content="first instruction"),
        Message(role="user", content="hello"),
        Message(role="user", content="more context"),
        Message(role="assistant", content="hi"),
        Message(role="system", content="second instruction"),
        Message(role="user", content="ping"),
    ], max_tokens=42)

    def handle(wire):
        seen.append(wire)
        assert str(wire.url) == "https://generativelanguage.googleapis.com/v1beta/models/configured-test-model:generateContent"
        assert wire.headers["x-goog-api-key"] == KEY
        assert "authorization" not in wire.headers and "x-api-key" not in wire.headers
        assert KEY not in wire.content.decode() and KEY not in str(wire.url)
        assert json.loads(wire.content) == {
            "systemInstruction": {"parts": [{"text": "first instruction\n\nsecond instruction"}]},
            "contents": [
                {"role": "user", "parts": [{"text": "hello"}, {"text": "more context"}]},
                {"role": "model", "parts": [{"text": "hi"}]},
                {"role": "user", "parts": [{"text": "ping"}]},
            ],
            "generationConfig": {"maxOutputTokens": 42, "candidateCount": 1},
        }
        return httpx.Response(200, json=gemini_reply(
            candidates=[{
                "content": {"role": "model", "parts": [
                    {"text": "internal thought", "thought": True},
                    {"text": "po", "thought": False},
                    {"text": "ng", "thoughtSignature": "opaque-not-returned"},
                ]},
                "finishReason": "STOP",
            }],
            usageMetadata={"promptTokenCount": 12, "candidatesTokenCount": 2, "thoughtsTokenCount": 7},
        ))

    async with mocked_provider(handle, kind="gemini") as provider:
        answer = await provider.complete(request)
    assert len(seen) == 1
    assert answer.text == "pong"
    assert answer.usage == {"input_tokens": 12, "output_tokens": 9}


async def test_claude_recognized_thinking_is_not_exposed():
    body = {
        "content": [
            {"type": "thinking", "thinking": "hidden thought", "signature": "opaque-signature"},
            {"type": "redacted_thinking", "data": "opaque-redacted"},
            {"type": "text", "text": "pong"},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 30},
    }
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="claude") as provider:
        answer = await provider.complete(REQUEST)
    assert answer.text == "pong"
    assert answer.usage == {"input_tokens": 10, "output_tokens": 30}


@pytest.mark.parametrize("kind", ["openai", "gemini"])
@pytest.mark.parametrize("usage", [None, {}, "unknown", True, {"bad": 4}])
async def test_new_provider_missing_or_invalid_usage_stays_unknown(kind, usage):
    body = openai_reply(usage=usage) if kind == "openai" else gemini_reply(usageMetadata=usage)
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind=kind) as provider:
        assert (await provider.complete(REQUEST)).usage is None


@pytest.mark.parametrize("kind,input_name,output_name,reply,key", [
    ("openai", "prompt_tokens", "completion_tokens", openai_reply, "usage"),
    ("gemini", "promptTokenCount", "candidatesTokenCount", gemini_reply, "usageMetadata"),
])
@pytest.mark.parametrize("value", [True, -1, 1.5, "2", None])
@pytest.mark.parametrize("invalid_field", ["input", "output"])
async def test_new_provider_counts_are_strict_nonnegative_integers(kind, input_name, output_name, reply, key, value, invalid_field):
    usage = {input_name: 3, output_name: 1}
    usage[input_name if invalid_field == "input" else output_name] = value
    async with mocked_provider(lambda _: httpx.Response(200, json=reply(**{key: usage})), kind=kind) as provider:
        assert (await provider.complete(REQUEST)).usage is None


@pytest.mark.parametrize("value", [True, -1, 1.5, "2", None])
async def test_gemini_invalid_thinking_usage_is_unknown(value):
    body = gemini_reply(usageMetadata={"promptTokenCount": 3, "candidatesTokenCount": 1, "thoughtsTokenCount": value})
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="gemini") as provider:
        assert (await provider.complete(REQUEST)).usage is None


@pytest.mark.parametrize("body", [
    {}, openai_reply(choices=[]), openai_reply(choices=[{}, {}]),
    openai_reply(choices=[{"finish_reason": "content_filter", "message": {"role": "assistant", "content": "blocked"}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "text", "refusal": "refused"}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "text", "tool_calls": [{"function": "foo"}]}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "text", "function_call": {"name": "foo"}}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "text", "audio": {"data": "bad"}}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": []}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "user", "content": "wrong role"}}]),
    openai_reply(choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]),
])
async def test_openai_unsupported_or_invalid_output_fails_closed(body):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="openai") as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)


@pytest.mark.parametrize("body", [
    {}, gemini_reply(candidates=[]), gemini_reply(candidates=[{}, {}]),
    gemini_reply(promptFeedback={"blockReason": "SAFETY"}),
    gemini_reply(candidates=[{"finishReason": "SAFETY", "content": {"role": "model", "parts": [{"text": "blocked"}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "user", "parts": [{"text": "wrong role"}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": "thought only", "thought": True}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": "bad thought", "thought": "true"}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "model", "parts": [{"inlineData": {"data": "bad"}}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": "text", "functionCall": {"name": "foo"}}]}}]),
    gemini_reply(candidates=[{"finishReason": "STOP", "content": {"role": "model", "parts": []}}]),
])
async def test_gemini_unsupported_or_invalid_output_fails_closed(body):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="gemini") as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)


@pytest.mark.parametrize("body", [
    {"content": [{"type": "text", "text": "blocked"}], "stop_reason": "refusal"},
    {"content": [{"type": "thinking", "thinking": "no final answer"}], "stop_reason": "end_turn"},
    {"content": [{"type": "thinking", "thinking": 42}, {"type": "text", "text": "answer"}], "stop_reason": "end_turn"},
    {"content": [{"type": "redacted_thinking", "data": 42}, {"type": "text", "text": "answer"}], "stop_reason": "end_turn"},
])
async def test_claude_refusal_or_invalid_thinking_fails_closed(body):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind="claude") as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)


@pytest.mark.parametrize("kind", ["claude", "openai", "gemini"])
@pytest.mark.parametrize("status,reason", [
    (301, "rejected"), (307, "rejected"), (400, "rejected"),
    (401, "authentication"), (403, "authentication"), (429, "rate_limit"),
    (500, "unavailable"), (503, "unavailable"), (529, "unavailable"),
])
async def test_all_real_provider_http_failures_are_safe_and_single_attempt(kind, status, reason):
    attempts = 0

    def handle(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, content=(KEY + " upstream raw details").encode(), headers={"location": "https://evil.invalid", "retry-after": "1"})

    async with mocked_provider(handle, kind=kind) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
    assert str(error.value) == "Provider request failed"
    assert error.value.reason == reason
    assert error.value.__suppress_context__
    assert attempts == 1


@pytest.mark.parametrize("kind", ["claude", "openai", "gemini"])
@pytest.mark.parametrize("failure,reason", [
    (httpx.ConnectError, "transport"), (httpx.ReadError, "transport"),
    (httpx.RemoteProtocolError, "transport"), (httpx.ReadTimeout, "timeout"),
    (httpx.ConnectTimeout, "timeout"), (httpx.WriteTimeout, "timeout"),
    (httpx.PoolTimeout, "timeout"), (httpx.DecodingError, "invalid_response"),
    (RuntimeError, "unknown"),
])
async def test_real_provider_transport_failures_are_safe_and_single_attempt(kind, failure, reason):
    attempts = 0

    def handle(wire):
        nonlocal attempts
        attempts += 1
        raise failure(KEY + " transport details " + str(wire.url))

    async with mocked_provider(handle, kind=kind) as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$") as error:
            await provider.complete(REQUEST)
    assert error.value.reason == reason
    assert error.value.__suppress_context__
    assert attempts == 1


@pytest.mark.parametrize("kind", ["claude", "openai", "gemini"])
@pytest.mark.parametrize("body", [b"not-json", b"\xff", b"[]", b"{}", b"x" * (MAX_RESPONSE_BYTES + 1)], ids=["not-json", "invalid-encoding", "array", "invalid-payload", "oversized"])
async def test_real_provider_bodies_are_bounded_and_safe(kind, body):
    async with mocked_provider(lambda _: httpx.Response(200, content=body), kind=kind) as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$") as error:
            await provider.complete(REQUEST)
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize("reason", [KEY, "unknown-new-category", None, [], {}, 429, True])
def test_arbitrary_provider_error_reasons_become_unknown(reason):
    error = ProviderError(reason)
    assert error.reason is ProviderErrorReason.UNKNOWN
    assert str(error) == "Provider request failed"


@pytest.mark.parametrize("reason", list(ProviderErrorReason))
def test_provider_error_accepts_only_documented_reason_values(reason):
    assert ProviderError(reason).reason is reason
    assert ProviderError(reason.value).reason is reason


@pytest.mark.parametrize("kind", ["claude", "gemini"])
async def test_system_only_request_never_calls_provider(kind):
    attempts = 0

    def handle(_):
        nonlocal attempts
        attempts += 1
        raise AssertionError("system-only input must not be sent")

    async with mocked_provider(handle, kind=kind) as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(ChatRequest(messages=[Message(role="system", content="system only")]))
    assert attempts == 0


@pytest.mark.parametrize("kind,origin,environment", [
    ("claude", "https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    ("openai", "https://api.openai.com", "OPENAI_API_KEY"),
    ("gemini", "https://generativelanguage.googleapis.com", "GEMINI_API_KEY"),
])
def test_kind_defaults_and_offline_validation_need_no_client_or_key(kind, origin, environment, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("validation must not create HTTP clients")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    config = ProviderConfig(kind=kind, model="configured-test-model")
    assert config.base_url == origin and config.key_env == environment
    validate_provider_config(config)
    with pytest.raises(ValueError, match="^Real provider requires an explicit model$"):
        validate_provider_config(ProviderConfig(kind=kind))


@pytest.mark.parametrize("kind,origin", [
    ("openai", "https://api.openai.com"),
    ("gemini", "https://generativelanguage.googleapis.com"),
])
@pytest.mark.parametrize("suffix", [".evil.invalid", ":444", "/v1", "?key=secret", "#fragment", "?", "#", "\n"])
def test_new_provider_origins_cannot_redirect_keys(kind, origin, suffix):
    with pytest.raises(ValueError, match="^Invalid provider origin$"):
        validate_provider_config(ProviderConfig(kind=kind, base_url=origin + suffix, model="safe-model"))


@pytest.mark.parametrize("model", ["", "../model", "model?key=secret", "model:otherOperation", "models/model", "a" * 129, "with space"])
def test_model_identifier_cannot_escape_gemini_path(model):
    with pytest.raises(ValueError):
        ProviderConfig(kind="gemini", model=model)


@pytest.mark.parametrize("value", [0, -1, 301, float("inf"), float("nan"), "30", True])
def test_provider_timeout_is_strict_and_bounded(value):
    with pytest.raises(ValueError):
        ProviderConfig(timeout_seconds=value)


async def test_configured_timeout_is_used_by_http_client():
    provider = build_provider(ProviderConfig(timeout_seconds=3.5), KEY)
    try:
        assert provider._client.timeout.read == 3.5
        assert provider._client.timeout.connect == 3.5
    finally:
        await provider.aclose()


@pytest.mark.parametrize("kind,body", [
    ("fake", {"text": "pong", "usage": {"input_tokens": 2**1024, "output_tokens": 1}}),
    ("claude", {"content": [{"type": "text", "text": "pong"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 2**1024}}),
    ("openai", openai_reply(usage={"prompt_tokens": 2**63, "completion_tokens": 1})),
    ("gemini", gemini_reply(usageMetadata={"promptTokenCount": 1, "candidatesTokenCount": 2**63})),
    ("gemini", gemini_reply(usageMetadata={"promptTokenCount": 1, "candidatesTokenCount": 1, "thoughtsTokenCount": 2**63 - 1})),
])
async def test_extreme_usage_and_gemini_sum_overflow_stay_unknown(kind, body):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind=kind) as provider:
        assert (await provider.complete(REQUEST)).usage is None


@pytest.mark.parametrize("kind,body,expected", [
    ("fake", {"text": "pong"}, "stop"),
    ("fake", {"text": "partial", "finish_reason": "length"}, "length"),
    ("claude", {"content": [{"type": "text", "text": "pong"}], "stop_reason": "end_turn"}, "stop"),
    ("claude", {"content": [{"type": "text", "text": "pong"}], "stop_reason": "stop_sequence"}, "stop"),
    ("claude", {"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"}, "length"),
    ("openai", openai_reply(), "stop"),
    ("openai", openai_reply(choices=[{"finish_reason": "length", "message": {"role": "assistant", "content": "partial"}}]), "length"),
    ("gemini", gemini_reply(), "stop"),
    ("gemini", gemini_reply(candidates=[{"finishReason": "MAX_TOKENS", "content": {"role": "model", "parts": [{"text": "partial"}]}}]), "length"),
])
async def test_provider_finish_reasons_are_normalized_without_changing_usage(kind, body, expected):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind=kind) as provider:
        answer = await provider.complete(REQUEST)
    assert answer.finish_reason == expected
    if kind in ("fake", "claude"):
        assert answer.usage is None


@pytest.mark.parametrize("kind,body", [
    ("fake", {"text": "pong", "finish_reason": None}),
    ("fake", {"text": "pong", "finish_reason": "unknown"}),
    ("claude", {"content": [{"type": "text", "text": "pong"}]}),
    ("claude", {"content": [{"type": "text", "text": "pong"}], "stop_reason": None}),
    ("claude", {"content": [{"type": "text", "text": "pong"}], "stop_reason": "unknown"}),
    ("openai", openai_reply(choices=[{"message": {"role": "assistant", "content": "pong"}}])),
    ("gemini", gemini_reply(candidates=[{"content": {"role": "model", "parts": [{"text": "pong"}]}}])),
])
async def test_missing_real_or_invalid_finish_reason_is_not_fabricated(kind, body):
    async with mocked_provider(lambda _: httpx.Response(200, json=body), kind=kind) as provider:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(REQUEST)


@pytest.mark.parametrize("kind,body,expected", [
    ("fake", {"text": "", "usage": {"input_tokens": 12, "output_tokens": 4}},
     {"input_tokens": 12, "output_tokens": 4}),
    ("claude", {"content": [{"type": "thinking", "thinking": KEY}], "stop_reason": "max_tokens",
                "usage": {"input_tokens": 12, "output_tokens": 4}},
     {"input_tokens": 12, "output_tokens": 4}),
    ("openai", openai_reply(choices=[{"finish_reason": "content_filter", "message": {"role": "assistant", "content": KEY}}]),
     {"input_tokens": 3, "output_tokens": 1}),
    ("gemini", gemini_reply(candidates=[{"finishReason": "MAX_TOKENS", "content": {"role": "model", "parts": [{"text": KEY, "thought": True}]}}],
                            usageMetadata={"promptTokenCount": 12, "candidatesTokenCount": 0, "thoughtsTokenCount": 4}),
     {"input_tokens": 12, "output_tokens": 4}),
])
async def test_rejected_answers_retain_independently_reported_usage(kind, body, expected):
    attempts = []

    def upstream(request):
        attempts.append(request)
        return httpx.Response(200, json=body)

    async with mocked_provider(upstream, kind=kind) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert error.value.usage == expected
    assert str(error.value) == "Provider request failed"
    assert KEY not in repr(error.value) and len(attempts) == 1


@pytest.mark.parametrize("kind,usage_key,input_name,output_name", [
    ("fake", "usage", "input_tokens", "output_tokens"),
    ("claude", "usage", "input_tokens", "output_tokens"),
    ("openai", "usage", "prompt_tokens", "completion_tokens"),
    ("gemini", "usageMetadata", "promptTokenCount", "candidatesTokenCount"),
])
@pytest.mark.parametrize("counts,expected", [
    (None, None), ("malformed", None), ((0,), None),
    ((0, 0), {"input_tokens": 0, "output_tokens": 0}),
    ((2**63 - 1, 2**63 - 1), {"input_tokens": 2**63 - 1, "output_tokens": 2**63 - 1}),
    ((2, -1), None), ((2, True), None), ((2, 1.5), None), ((2, "3"), None), ((2, 2**63), None),
])
async def test_rejected_answer_usage_is_complete_strict_and_bounded(kind, usage_key, input_name, output_name, counts, expected):
    # Missing answer/finish fields fail independently of the accounting fields.
    raw_usage = dict(zip((input_name, output_name), counts)) if isinstance(counts, tuple) else counts
    async with mocked_provider(lambda _: httpx.Response(200, json={usage_key: raw_usage}), kind=kind) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert error.value.usage == expected


@pytest.mark.parametrize("usage", [
    {"promptTokenCount": 1, "thoughtsTokenCount": 3},
    {"promptTokenCount": 1, "candidatesTokenCount": 1, "thoughtsTokenCount": 2**63 - 1},
    {"promptTokenCount": 1, "candidatesTokenCount": 1, "thoughtsTokenCount": True},
])
async def test_rejected_gemini_answer_does_not_infer_or_overflow_thought_usage(usage):
    async with mocked_provider(lambda _: httpx.Response(200, json={"usageMetadata": usage}), kind="gemini") as provider:
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
    assert error.value.usage is None


def test_provider_error_usage_is_a_private_canonical_snapshot():
    usage = {"input_tokens": 12, "output_tokens": 4, "upstream_private": KEY}
    error = ProviderError("invalid_response", usage=usage)
    usage["input_tokens"] = -1
    snapshot = error.usage
    assert snapshot == {"input_tokens": 12, "output_tokens": 4}
    snapshot["output_tokens"] = 1000
    assert error.usage == {"input_tokens": 12, "output_tokens": 4}
    assert KEY not in str(vars(error)) + str(error) + repr(error)


@pytest.mark.parametrize("usage", [None, [], {}, {"input_tokens": 2},
    {"input_tokens": True, "output_tokens": 1}, {"input_tokens": -1, "output_tokens": 1},
    {"input_tokens": 1, "output_tokens": 1.5}, {"input_tokens": 1, "output_tokens": 2**63},
])
def test_provider_error_does_not_carry_invalid_usage(usage):
    assert ProviderError("invalid_response", usage=usage).usage is None

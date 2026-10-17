"""Adapter checks use mock HTTP transports, never live provider credentials."""

import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from gateway7.config import ProviderConfig
from gateway7.errors import ProviderError
from gateway7.models import ChatRequest, Message
from gateway7.providers import MAX_RESPONSE_BYTES, build_provider


KEY = "gateway7-synthetic-test-only"
REQUEST = ChatRequest(messages=[Message(role="user", content="ping")])


@asynccontextmanager
async def mocked_provider(handler, *, kind="fake"):
    config = ProviderConfig(
        kind=kind,
        base_url="http://127.0.0.1:8001" if kind == "fake" else "https://api.anthropic.com",
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
    body = {"text": "pong", "content": [{"type": "text", "text": "pong"}], "usage": usage}
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

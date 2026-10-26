"""Observe real HTTPX response-stream lifetime with deterministic offline bodies."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json

import httpx
import pytest
from prometheus_client import generate_latest

from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.loader import load_plugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, Message
from gateway7.pipeline import Pipeline
from gateway7.providers import MAX_RESPONSE_BYTES, build_provider


KEY = "gateway7-synthetic-transport-key"
PRIVATE = "synthetic-private-upstream-details"
REQUEST = ChatRequest(messages=[Message(role="user", content="ping")])
REPLY = json.dumps(
    {
        "choices": [
            {
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
).encode()


class ObservedStream(httpx.AsyncByteStream):
    def __init__(self, chunks, *, failure=None, block=False):
        self.chunks = chunks
        self.failure = failure
        self.block = block
        self.read_sizes = []
        self.exhausted = False
        self.close_calls = 0
        self.blocked = asyncio.Event()
        self.read_cancelled = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.read_sizes.append(len(chunk))
            yield chunk
        if self.failure is not None:
            raise self.failure
        if self.block:
            self.blocked.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.read_cancelled.set()
                raise
        self.exhausted = True

    async def aclose(self) -> None:
        self.close_calls += 1


@asynccontextmanager
async def streamed_provider(stream, *, status=200, headers=None):
    response = httpx.Response(status, stream=stream, headers=headers)
    requests = []

    def handle(request):
        requests.append(request)
        return response

    provider = build_provider(ProviderConfig(kind="openai", model="configured-test-model"), KEY)
    await provider.aclose()
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=False, trust_env=False
    )
    try:
        yield provider, requests, response
    finally:
        await provider.aclose()


def assert_safe_error(error, reason):
    assert type(error) is ProviderError
    assert str(error) == "Provider request failed"
    assert error.reason is reason
    assert error.__suppress_context__
    assert KEY not in str(error) and PRIVATE not in str(error)


async def test_multichunk_body_at_exact_byte_limit_is_accepted_and_closed_once():
    body = REPLY + b" " * (MAX_RESPONSE_BYTES - len(REPLY))
    chunks = [body[:17], body[17:65_537], body[65_537:]]
    stream = ObservedStream(chunks)
    async with streamed_provider(stream) as (provider, requests, response):
        assert "content-length" not in response.headers
        answer = await provider.complete(REQUEST)
        assert answer.text == "pong"
        assert answer.usage == {"input_tokens": 3, "output_tokens": 1}
        assert response.is_closed
        assert stream.close_calls == 1
    assert stream.read_sizes == [len(chunk) for chunk in chunks]
    assert stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1


async def test_first_overflowing_chunk_stops_reading_without_consuming_tail():
    body = REPLY + b" " * (MAX_RESPONSE_BYTES - len(REPLY))
    chunks = [body[:17], body[17:], b" ", PRIVATE.encode()]
    stream = ObservedStream(chunks)
    async with streamed_provider(stream) as (provider, requests, response):
        assert "content-length" not in response.headers
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.INVALID_RESPONSE)
    assert stream.read_sizes == [17, MAX_RESPONSE_BYTES - 17, 1]
    assert not stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1


async def test_cancellation_during_body_read_closes_once_without_provider_error_metric(caplog):
    stream = ObservedStream([REPLY[:17]], block=True)
    metrics = Metrics()
    config = GatewayConfig()
    caplog.set_level("INFO", logger="gateway7")
    async with streamed_provider(stream) as (provider, requests, response):
        pipeline = Pipeline(
            load_plugins(config),
            provider,
            config.limits,
            metrics=metrics,
            provider_name="openai",
        )
        task = asyncio.create_task(pipeline.run(REQUEST, "transport-cancellation-test"))
        try:
            await asyncio.wait_for(stream.blocked.wait(), timeout=1)
            assert len(requests) == 1
            assert not response.is_closed
            assert stream.read_sizes == [17]
            task.cancel("cancel while reading body")
            with pytest.raises(asyncio.CancelledError, match="cancel while reading body"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert stream.read_cancelled.is_set()
        assert response.is_closed
        assert stream.close_calls == 1
    assert stream.close_calls == 1
    assert len(requests) == 1
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "openai", "outcome": "cancelled"}
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "openai", "outcome": "provider_error"}
        )
        is None
    )
    assert not metrics.provider_errors.collect()[0].samples
    assert KEY not in caplog.text and PRIVATE not in caplog.text
    exposition = generate_latest(metrics.registry).decode()
    assert KEY not in exposition and PRIVATE not in exposition


@pytest.mark.parametrize(
    "failure,reason",
    [
        (httpx.ReadError, ProviderErrorReason.TRANSPORT),
        (httpx.RemoteProtocolError, ProviderErrorReason.TRANSPORT),
        (httpx.ReadTimeout, ProviderErrorReason.TIMEOUT),
    ],
)
async def test_post_header_read_failures_close_stream_once_without_retry(failure, reason):
    stream = ObservedStream([REPLY[:17]], failure=failure(PRIVATE + " " + KEY))
    async with streamed_provider(stream) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, reason)
    assert stream.read_sizes == [17]
    assert not stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1


async def test_http_decoder_failure_closes_stream_before_reading_tail():
    chunks = [(PRIVATE + " " + KEY).encode(), b"unconsumed-tail"]
    stream = ObservedStream(chunks)
    async with streamed_provider(stream, headers={"content-encoding": "gzip"}) as (
        provider,
        requests,
        response,
    ):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.INVALID_RESPONSE)
    assert stream.read_sizes == [len(chunks[0])]
    assert not stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        (PRIVATE + " " + KEY).encode(),
        b'{"text":"\xff"}',
        b"[]",
        b'{"choices":[]}',
    ],
    ids=["invalid-json", "invalid-encoding", "non-object", "invalid-envelope"],
)
async def test_decode_and_response_validation_failures_close_stream_once(body):
    chunks = [body[:2], body[2:]]
    stream = ObservedStream(chunks)
    async with streamed_provider(stream) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.INVALID_RESPONSE)
    assert stream.read_sizes == [len(chunk) for chunk in chunks]
    assert stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,reason",
    [
        (302, ProviderErrorReason.REJECTED),
        (401, ProviderErrorReason.AUTHENTICATION),
        (429, ProviderErrorReason.RATE_LIMIT),
        (503, ProviderErrorReason.UNAVAILABLE),
    ],
)
async def test_non_200_closes_stream_without_reading_body_or_retrying(status, reason):
    stream = ObservedStream([(PRIVATE + " " + KEY).encode()])
    async with streamed_provider(
        stream, status=status, headers={"location": "https://untrusted.invalid", "retry-after": "1"}
    ) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, reason)
    assert stream.read_sizes == []
    assert not stream.exhausted
    assert stream.close_calls == 1
    assert len(requests) == 1

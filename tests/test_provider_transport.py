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
async def streamed_provider(stream, *, status=200, headers=None, kind="openai"):
    response = httpx.Response(status, stream=stream, headers=headers)
    requests = []

    def handle(request):
        requests.append(request)
        return response

    provider = build_provider(ProviderConfig(kind=kind, model="configured-test-model"), KEY)
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


@pytest.mark.parametrize(
    "body",
    [
        REPLY.replace(b'"content": "pong"', b'"content": "hidden", "content": "pong"'),
        REPLY[:-1] + b', "metadata": {"repeated": 1, "repeated": 2}}',
        REPLY[:-1] + b', "metadata": NaN}',
        REPLY[:-1] + b', "metadata": Infinity}',
        REPLY[:-1] + b', "metadata": -Infinity}',
        REPLY[:-1] + b', "metadata": 1e999}',
        REPLY.decode().encode("utf-16"),
        REPLY.decode().encode("utf-32"),
        REPLY.replace(b"pong", b"\xff"),
        REPLY.replace(b"pong", b"\\ud800"),
        REPLY.replace(b"pong", b"\\udfff"),
        REPLY[:-1] + b', "metadata": {"\\ud800": 1}}',
        REPLY[:-1] + b', "metadata": ' + b"[" * 64 + b"0" + b"]" * 64 + b"}",
    ],
    ids=[
        "duplicate-content",
        "duplicate-ignored-metadata",
        "nan",
        "infinity",
        "negative-infinity",
        "overflowing-float",
        "utf16",
        "utf32",
        "invalid-utf8",
        "unpaired-high-surrogate",
        "unpaired-low-surrogate",
        "surrogate-object-key",
        "depth-overflow",
    ],
)
async def test_ambiguous_or_noninteroperable_provider_json_is_rejected(body):
    stream = ObservedStream([body[:17], body[17:]])
    async with streamed_provider(stream) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.INVALID_RESPONSE)
    assert caught.value.usage is None
    assert stream.close_calls == 1
    assert len(requests) == 1


@pytest.mark.parametrize(
    "text",
    ["данные/🌍.txt".encode(), b"\\u0434\\u0430\\u043d\\u043d\\u044b\\u0435/\\ud83c\\udf0d.txt"],
    ids=["utf8", "json-surrogate-pair"],
)
async def test_strict_provider_json_preserves_valid_unicode_and_depth_boundary(text):
    body = (
        REPLY.replace(b"pong", text)[:-1]
        + b', "metadata": '
        + b"[" * 63
        + b"0"
        + b"]" * 63
        + b"}"
    )
    stream = ObservedStream([body[:17], body[17:]])
    async with streamed_provider(stream) as (provider, requests, response):
        answer = await provider.complete(REQUEST)
        assert answer.text == "данные/🌍.txt"
        assert answer.usage == {"input_tokens": 3, "output_tokens": 1}
        assert response.is_closed
    assert stream.close_calls == 1
    assert len(requests) == 1


class DeferredCloseStream(ObservedStream):
    def __init__(self, chunks, *, close_failure=None, **options):
        super().__init__(chunks, **options)
        self.close_failure = close_failure
        self.close_entered = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_finished = asyncio.Event()
        self.close_interrupted = False
        self.close_tasks = set()

    async def aclose(self):
        self.close_calls += 1
        self.close_tasks.add(asyncio.current_task())
        self.close_entered.set()
        try:
            await self.close_release.wait()
        except asyncio.CancelledError:
            self.close_interrupted = True
            raise
        self.close_finished.set()
        if self.close_failure is not None:
            raise self.close_failure


@pytest.mark.parametrize("mode", ["json-eof", "sse-eof", "read-error", "callback-error", "cancel"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_repeated_cancellation_awaits_chat_cleanup_and_preserves_primary(mode, cleanup_fails):
    events = [
        {"choices": [{"index": 0, "delta": {"content": "pong"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}},
    ]
    sse = (
        "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
    ).encode()
    streaming = mode in ("sse-eof", "callback-error")
    stream = DeferredCloseStream(
        [sse if streaming else REPLY],
        failure=httpx.ReadError(PRIVATE) if mode == "read-error" else None,
        block=mode == "cancel",
        close_failure=httpx.ReadError(PRIVATE) if cleanup_fails else None,
    )
    original = ValueError("synthetic callback failure")

    async def on_text(_):
        raise original

    async def checkpoint():
        reached = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(reached.set_result, None)
        await reached

    headers = {"content-type": "text/event-stream"} if streaming else None
    async with streamed_provider(stream, headers=headers) as (provider, requests, response):
        before = asyncio.all_tasks()
        task = asyncio.create_task(
            provider.complete_early(REQUEST, on_text=on_text)
            if mode == "callback-error"
            else provider.complete(REQUEST, stream=streaming)
        )
        caught = None
        try:
            if mode == "cancel":
                await asyncio.wait_for(stream.blocked.wait(), 1)
                task.cancel("primary cancellation")
            await asyncio.wait_for(stream.close_entered.wait(), 1)
            task.cancel("cancellation during close")
            await checkpoint()
            assert not task.done() and not stream.close_finished.is_set()
            assert not stream.close_interrupted
            task.cancel("repeated cancellation during close")
            await checkpoint()
            assert not task.done() and not stream.close_finished.is_set()
            assert not stream.close_interrupted
        finally:
            stream.close_release.set()
            try:
                await task
            except BaseException as error:
                caught = error
        if mode == "callback-error":
            assert caught is original
        elif mode == "read-error":
            assert_safe_error(caught, ProviderErrorReason.TRANSPORT)
        else:
            assert isinstance(caught, asyncio.CancelledError)
            assert str(caught) == (
                "primary cancellation" if mode == "cancel" else "cancellation during close"
            )
        assert task.cancelled() is (mode not in ("read-error", "callback-error"))
        assert stream.close_calls == 1 and stream.close_finished.is_set()
        assert not stream.close_interrupted and response.is_closed
        assert len(stream.close_tasks) == 1
        assert all(owner is not task and owner.done() for owner in stream.close_tasks)
        assert not (asyncio.all_tasks() - before)
        assert len(requests) == 1


async def test_one_request_waiting_for_cleanup_does_not_close_or_block_another_request():
    waiting = DeferredCloseStream([REPLY])
    healthy = ObservedStream([REPLY])
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(200, stream=waiting if len(attempts) == 1 else healthy)

    provider = build_provider(
        ProviderConfig(kind="openai", model="configured-test-model"),
        KEY,
        transport=httpx.MockTransport(handle),
    )
    task = asyncio.create_task(provider.complete(REQUEST))
    try:
        await asyncio.wait_for(waiting.close_entered.wait(), 1)
        answer = await asyncio.wait_for(provider.complete(REQUEST), 1)
        assert answer.text == "pong" and answer.usage == {"input_tokens": 3, "output_tokens": 1}
        assert healthy.close_calls == 1 and healthy.exhausted
        assert not task.done() and not waiting.close_finished.is_set()
        task.cancel("cancel first request only")
    finally:
        waiting.close_release.set()
        try:
            await task
        except asyncio.CancelledError as error:
            assert str(error) == "cancel first request only"
        await provider.aclose()
    assert task.cancelled() and waiting.close_finished.is_set()
    assert waiting.close_calls == 1 and not waiting.close_interrupted
    assert healthy.close_calls == 1 and len(attempts) == 2


from gateway7.errors import GatewayError, ProviderError, ProviderErrorReason


class FailedCleanupStream(ObservedStream):
    async def aclose(self):
        await super().aclose()
        raise httpx.ReadError(PRIVATE + " " + KEY)


@pytest.mark.parametrize(
    "kind,body,expected",
    [
        ("openai", REPLY, {"input_tokens": 3, "output_tokens": 1}),
        (
            "fake",
            b'{"text":"pong","usage":{"input_tokens":3,"output_tokens":1}}',
            {"input_tokens": 3, "output_tokens": 1},
        ),
        (
            "claude",
            b'{"content":[{"type":"text","text":"pong"}],"stop_reason":"end_turn",'
            b'"usage":{"input_tokens":3,"output_tokens":1}}',
            {"input_tokens": 3, "output_tokens": 1},
        ),
        (
            "gemini",
            b'{"candidates":[{"content":{"role":"model","parts":[{"text":"pong"}]},'
            b'"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":3,'
            b'"candidatesTokenCount":1,"thoughtsTokenCount":2}}',
            {"input_tokens": 3, "output_tokens": 3},
        ),
    ],
)
async def test_cleanup_failure_retains_observed_source_usage_without_returning_an_answer(
    kind, body, expected
):
    stream = FailedCleanupStream([body[:17], body[17:]])
    async with streamed_provider(stream, kind=kind) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.TRANSPORT)
    assert caught.value.usage == expected
    detached = caught.value.usage
    detached["input_tokens"] = 999
    assert caught.value.usage == expected
    assert stream.exhausted and stream.close_calls == 1 and len(requests) == 1


@pytest.mark.parametrize(
    "chunks",
    [
        [REPLY[:-1]],
        [REPLY + b"trailing garbage"],
        [REPLY.replace(b'"prompt_tokens": 3', b'"prompt_tokens": 99, "prompt_tokens": 3')],
        [REPLY[:-1] + b', "metadata": NaN}'],
        [REPLY.replace(b"pong", b"\\ud800")],
        [REPLY.decode().encode("utf-16")],
        [REPLY.replace(b'"prompt_tokens": 3', b'"prompt_tokens": true')],
        [REPLY.replace(b'"prompt_tokens": 3', b'"prompt_tokens": -1')],
        [REPLY.replace(b', "completion_tokens": 1', b"")],
        [REPLY + b" " * (MAX_RESPONSE_BYTES - len(REPLY)), b" "],
    ],
    ids=[
        "truncated-json",
        "trailing-garbage",
        "ambiguous-usage",
        "nonfinite-metadata",
        "invalid-unicode",
        "utf16",
        "boolean-count",
        "negative-count",
        "missing-count",
        "body-overflow",
    ],
)
async def test_cleanup_failure_cannot_recover_usage_from_an_invalid_or_oversized_body(chunks):
    stream = FailedCleanupStream(chunks)
    async with streamed_provider(stream) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert caught.value.usage is None
    assert stream.close_calls == 1 and len(requests) == 1
    assert str(caught.value) == "Provider request failed"


@pytest.mark.parametrize("truncated", [False, True])
async def test_read_timeout_keeps_precedence_over_cleanup_failure_and_usage_is_only_observed(
    truncated,
):
    stream = FailedCleanupStream(
        [REPLY[:-1] if truncated else REPLY], failure=httpx.ReadTimeout(PRIVATE)
    )
    async with streamed_provider(stream) as (provider, requests, response):
        with pytest.raises(ProviderError) as caught:
            await provider.complete(REQUEST)
        assert response.is_closed
    assert_safe_error(caught.value, ProviderErrorReason.TIMEOUT)
    assert caught.value.usage == (None if truncated else {"input_tokens": 3, "output_tokens": 1})
    assert not stream.exhausted and stream.close_calls == 1 and len(requests) == 1


@pytest.mark.parametrize("valid_usage", [False, True])
async def test_pipeline_accounts_cleanup_failure_as_an_error_with_known_or_unknown_usage(
    valid_usage,
):
    body = REPLY if valid_usage else REPLY[:-1]
    stream = FailedCleanupStream([body])
    metrics = Metrics()
    config = GatewayConfig()
    async with streamed_provider(stream) as (provider, requests, response):
        pipeline = Pipeline(
            load_plugins(config), provider, config.limits, metrics=metrics, provider_name="openai"
        )
        with pytest.raises(GatewayError) as caught:
            await pipeline.run(REQUEST, "synthetic-cleanup-accounting")
        assert caught.value.code == "provider_error" and response.is_closed
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "openai", "outcome": "provider_error"}
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "openai", "outcome": "complete"}
        )
        is None
    )
    assert metrics.registry.get_sample_value(
        "gateway7_provider_tokens_total", {"provider": "openai", "direction": "input"}
    ) == (3 if valid_usage else None)
    assert metrics.registry.get_sample_value(
        "gateway7_provider_tokens_total", {"provider": "openai", "direction": "output"}
    ) == (1 if valid_usage else None)
    assert metrics.registry.get_sample_value(
        "gateway7_provider_usage_unknown_total", {"provider": "openai"}
    ) == (None if valid_usage else 1)
    assert stream.close_calls == 1 and len(requests) == 1

"""Opt-in early SSE has direct backpressure and owns its complete ASGI lifetime."""

import asyncio
import gc
import importlib
import json
import sys
from types import ModuleType

import httpx
import httpx2
import pytest
from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict

from gateway7.app import _EarlySSE, create_app
from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.errors import GatewayError
from gateway7.models import ChatResponse
from gateway7.openai_api import EarlyChatEncoder
from gateway7.plugin_api import PluginDescriptor
from gateway7.providers import build_provider

app_module = importlib.import_module("gateway7.app")
TOKEN = "gateway7-synthetic-early-client-token"
AUTH = (b"authorization", ("Bearer " + TOKEN).encode())
EARLY = (b"x-gateway7-stream-mode", b"early")
BODY = {"model": "model-a", "messages": [{"role": "user", "content": "hello"}], "stream": True}
TOOL = {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}
CALL = {"id": "call_fixture", "type": "function", "function": {"name": "read", "arguments": "{}"}}
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


def event(delta=None, *, finish=None, usage=None):
    data = {
        "id": "chatcmpl-synthetic-upstream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "model-a",
        "choices": []
        if usage is not None
        else [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
    }
    if usage is not None:
        data["usage"] = usage
    return b"data: " + json.dumps(data).encode() + b"\n\n"


def stream_parts(text="prefix", *, finish="stop", done=True):
    return [
        event({"role": "assistant", "content": ""}),
        event({"content": text}),
        event(finish=finish),
        event(usage=USAGE),
        *([b"data: [DONE]\n\n"] if done else []),
    ]


class Upstream(httpx.AsyncByteStream):
    def __init__(self, parts=None, *, gate_after=None, resist_cleanup=False):
        self.parts = stream_parts() if parts is None else parts
        self.gate_after = gate_after
        self.reads = []
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.eof = asyncio.Event()
        self.closing = asyncio.Event()
        self.closed = asyncio.Event()
        self.cleanup_release = asyncio.Event()
        self.resist_cleanup = resist_cleanup

    async def __aiter__(self):
        for index, part in enumerate(self.parts):
            self.reads.append(index)
            yield part
            if index == self.gate_after:
                self.waiting.set()
                await self.release.wait()
        self.eof.set()

    async def aclose(self):
        self.closing.set()
        if self.resist_cleanup:
            while not self.cleanup_release.is_set():
                try:
                    await self.cleanup_release.wait()
                except asyncio.CancelledError:
                    continue
        self.closed.set()


class RawHTTP:
    def __init__(
        self,
        app,
        *,
        body=None,
        headers=None,
        path="/v1/chat/completions",
        send_hook=None,
        wire=None,
    ):
        self.app = app
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                AUTH,
                *(headers if headers is not None else [EARLY]),
            ],
            "server": ("gateway.test", 80),
            "client": ("synthetic", 1000),
        }
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait(
            {
                "type": "http.request",
                "body": wire
                if wire is not None
                else json.dumps(BODY if body is None else body).encode(),
                "more_body": False,
            }
        )
        self.sent = []
        self.first_text = asyncio.Event()
        self.send_hook = send_hook
        self.task = asyncio.create_task(app(self.scope, self.incoming.get, self.send))

    async def send(self, message):
        if self.send_hook is not None:
            await self.send_hook(message)
        self.sent.append(message)
        for item in self.events:
            if any(choice.get("delta", {}).get("content") for choice in item.get("choices", [])):
                self.first_text.set()

    @property
    def body(self):
        return b"".join(message.get("body", b"") for message in self.sent)

    @property
    def events(self):
        return [
            json.loads(frame[6:])
            for frame in self.body.split(b"\n\n")
            if frame.startswith(b"data: ") and frame != b"data: [DONE]"
        ]

    @property
    def status(self):
        return next(
            (
                message["status"]
                for message in self.sent
                if message["type"] == "http.response.start"
            ),
            None,
        )

    async def finish(self):
        await asyncio.wait_for(self.task, 1)


def assert_outcome(app, outcome, *, status):
    metrics = app.state.metrics
    outcomes = [
        item
        for item in metrics.http_outcomes.collect()[0].samples
        if item.name.endswith("_total") and item.labels["route"] == "openai_chat"
    ]
    assert [(item.labels["outcome"], item.value) for item in outcomes] == [(outcome, 1)]
    statuses = [
        item
        for item in metrics.http_requests.collect()[0].samples
        if item.name.endswith("_total") and item.labels["route"] == "openai_chat"
    ]
    assert [(item.labels["status"], item.value) for item in statuses] == (
        [] if status is None else [(str(status), 1)]
    )


@pytest.fixture
def make_app(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "gateway7-synthetic-early-provider-key")
    monkeypatch.setenv("FAKE_LLM_API_KEY", "gateway7-synthetic-early-provider-key")
    monkeypatch.setenv("EARLY_CLIENT_TOKEN", TOKEN)

    def make(upstream=None, *, provider=None, status=200, kind="openai", **updates):
        attempts = []
        upstream = Upstream() if upstream is None else upstream

        async def handle(request):
            assert "x-gateway7-stream-mode" not in request.headers
            attempts.append(json.loads(request.content))
            return httpx.Response(
                status, headers={"content-type": "text/event-stream"}, stream=upstream
            )

        if provider is None:
            provider = build_provider(
                ProviderConfig(kind="openai", model="model-a"),
                "gateway7-synthetic-adapter-key",
                transport=httpx.MockTransport(handle),
            )
        monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
        config = GatewayConfig.model_validate(
            {
                "provider": {"kind": kind, "model": "model-a"},
                "auth": {
                    "enabled": True,
                    "clients": {
                        "test": {
                            "token_env": "EARLY_CLIENT_TOKEN",
                            "models": ["model-a", "model-b"],
                        }
                    },
                },
                **updates,
            }
        )
        return create_app(config=config), upstream, attempts

    return make


async def test_nonempty_text_precedes_upstream_eof_with_stable_sdk_packets(make_app):
    app, upstream, attempts = make_app(Upstream(gate_after=1))
    async with app.router.lifespan_context(app):
        raw = RawHTTP(
            app, body={**BODY, "model": "model-b", "stream_options": {"include_usage": True}}
        )
        try:
            await asyncio.wait_for(raw.first_text.wait(), 1)
            assert raw.status == 200 and not upstream.eof.is_set()
            assert b"[DONE]" not in raw.body
            assert app.state.admission.active == 1
        finally:
            upstream.release.set()
            await raw.finish()
        events = raw.events
        assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
        assert events[1]["choices"][0]["delta"] == {"content": "prefix"}
        assert events[-2]["choices"][0]["finish_reason"] == "stop"
        assert events[-1]["usage"] == USAGE and events[-1]["choices"] == []
        assert len({(item["id"], item["created"], item["model"]) for item in events}) == 1
        assert events[0]["model"] == "model-b" and raw.body.endswith(b"data: [DONE]\n\n")
        assert attempts[0]["model"] == "model-b"
        assert "stream_mode" not in attempts[0] and "x-gateway7-stream-mode" not in attempts[0]
        assert app.state.admission.active == 0 and upstream.closed.is_set()
        assert_outcome(app, "success", status=200)
        headers = dict(raw.sent[0]["headers"])
        assert headers[b"cache-control"] == b"no-cache"
        assert headers[b"x-accel-buffering"] == b"no"
        assert b"content-length" not in headers
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_provider_calls_total", {"provider": "openai", "outcome": "complete"}
            )
            == 1
        )
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_provider_tokens_total", {"provider": "openai", "direction": "input"}
            )
            == 3
        )


@pytest.mark.parametrize("headers", [[], [(b"x-gateway7-stream-mode", b"buffered")]])
async def test_default_and_explicit_buffered_still_check_full_response_before_headers(
    make_app, headers
):
    app, upstream, attempts = make_app(
        Upstream(stream_parts("PRIVATE-TEST"), gate_after=1),
        plugins={
            "guard": {
                "module": "gateway7.plugins.content_policy",
                "settings": {"terms": ["PRIVATE-TEST"], "phase": "response"},
            }
        },
        middleware=["guard"],
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, headers=headers)
        try:
            await asyncio.wait_for(upstream.waiting.wait(), 1)
            assert raw.sent == []
        finally:
            upstream.release.set()
            await raw.finish()
        assert raw.status == 403 and len(attempts) == 1
        assert json.loads(raw.body)["error"]["code"] == "policy_denied"
        assert b"PRIVATE-TEST" not in raw.body


@pytest.mark.parametrize(
    "headers",
    [
        [(b"x-gateway7-stream-mode", b"unknown-sensitive")],
        [EARLY, EARLY],
        [(b"x-gateway7-stream-mode", b"early, buffered")],
        [(b"x-gateway7-stream-mode", b"")],
    ],
)
async def test_invalid_or_duplicate_mode_is_400_without_attempts(make_app, headers):
    app, _, attempts = make_app()
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, headers=headers)
        await raw.finish()
        assert raw.status == 400 and not attempts
        assert b"unknown-sensitive" not in raw.body


@pytest.mark.parametrize("change", ["not-streaming", "native", "provider", "capability"])
async def test_early_mode_requires_streaming_openai_route_and_capabilities(make_app, change):
    provider = object() if change == "capability" else None
    if provider is not None:

        class BufferedOnly:
            async def aclose(self):
                pass

        provider = BufferedOnly()
    app, _, attempts = make_app(
        kind="fake" if change == "provider" else "openai", provider=provider
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(
            app,
            body={**BODY, "stream": change != "not-streaming"},
            path="/chat" if change == "native" else "/v1/chat/completions",
        )
        await raw.finish()
        assert raw.status == 400 and not attempts
        assert app.state.admission.active == 0


@pytest.mark.parametrize(
    "module,settings,status",
    [
        ("gateway7.plugins.content_policy", {"terms": ["hello"], "phase": "request"}, 403),
        ("gateway7.plugins.content_policy", {"terms": ["private"], "phase": "response"}, 400),
        ("gateway7.plugins.content_policy", {"terms": ["private"], "phase": "both"}, 400),
    ],
)
async def test_request_denial_and_unsafe_response_policies_remain_json_without_attempts(
    make_app, module, settings, status
):
    app, _, attempts = make_app(
        plugins={"guard": {"module": module, "settings": settings}}, middleware=["guard"]
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app)
        await raw.finish()
        assert raw.status == status and not attempts
        assert not raw.body.startswith(b"data:")


async def test_request_masks_run_before_early_forwarding(make_app):
    app, _, attempts = make_app(
        plugins={
            "mask": {"module": "gateway7.plugins.email_mask", "settings": {"phase": "request"}}
        },
        middleware=["mask"],
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(
            app, body={**BODY, "messages": [{"role": "user", "content": "fixture@example.com"}]}
        )
        await raw.finish()
        assert raw.status == 200
        assert attempts[0]["messages"][0]["content"] == "[EMAIL]"


@pytest.mark.parametrize("failure", ["eof", "finish", "malformed", "tool"])
async def test_late_invalid_upstream_keeps_prefix_but_sends_sanitized_terminal_error(
    make_app, failure, caplog
):
    parts = stream_parts(done=failure != "eof")
    body = BODY
    if failure == "finish":
        parts[2] = event(finish="content_filter")
    elif failure == "malformed":
        parts[2] = b"data: {PRIVATE-UPSTREAM\n\n"
    elif failure == "tool":
        parts[2] = event(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        **CALL,
                        "function": {"name": "read", "arguments": "PRIVATE-UPSTREAM"},
                    }
                ]
            },
            finish="tool_calls",
        )
        body = {**BODY, "tools": [TOOL]}
    app, _, attempts = make_app(Upstream(parts))
    with caplog.at_level("INFO", logger="gateway7"):
        async with app.router.lifespan_context(app):
            raw = RawHTTP(app, body=body)
            await raw.finish()
            assert raw.status == 200 and raw.first_text.is_set() and len(attempts) == 1
            assert raw.events[-1]["error"]["code"] == "provider_error"
            assert raw.events[-1]["error"]["type"] == "api_error"
            assert b"[DONE]" not in raw.body and b"PRIVATE-UPSTREAM" not in raw.body
            assert not any(
                choice["finish_reason"] for item in raw.events for choice in item.get("choices", [])
            )
            assert app.state.admission.active == 0
            assert_outcome(app, "provider_error", status=200)
            assert (
                app.state.metrics.registry.get_sample_value(
                    "gateway7_provider_calls_total",
                    {"provider": "openai", "outcome": "provider_error"},
                )
                == 1
            )
    assert "outcome=provider_error component=http" in caplog.text
    assert "PRIVATE-UPSTREAM" not in caplog.text

    # Exercise the installed 3.37 SDK's real stream decoder against the ASGI
    # packets, without a socket or an external provider request.
    with OpenAI(
        api_key="synthetic-sdk-client-key",
        max_retries=0,
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(
                    200, headers={"content-type": "text/event-stream"}, content=raw.body
                )
            )
        ),
    ) as sdk:
        with sdk.chat.completions.create(
            model="model-a", messages=[{"role": "user", "content": "synthetic"}], stream=True
        ) as stream:
            chunks = iter(stream)
            assert next(chunks).choices[0].delta.role == "assistant"
            assert next(chunks).choices[0].delta.content == "prefix"
            with pytest.raises(APIError, match="Provider request failed"):
                next(chunks)


@pytest.mark.parametrize("failure", ["upstream", "empty-invalid", "tool-invalid"])
async def test_pre_text_failures_use_json_status_without_sse_headers(make_app, failure):
    parts = [event({"role": "assistant", "content": ""})]
    if failure == "tool-invalid":
        parts.append(
            event(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            **CALL,
                            "function": {"name": "read", "arguments": "PRIVATE-UPSTREAM"},
                        }
                    ]
                },
                finish="tool_calls",
            )
        )
        parts.append(b"data: [DONE]\n\n")
    app, _, attempts = make_app(Upstream(parts), status=429 if failure == "upstream" else 200)
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, body={**BODY, "tools": [TOOL]})
        await raw.finish()
        assert raw.status == 502 and len(attempts) == 1
        assert json.loads(raw.body)["error"]["code"] == "provider_error"
        assert b"data:" not in raw.body and b"PRIVATE-UPSTREAM" not in raw.body


async def test_tool_fragments_are_withheld_until_strict_terminal_validation(make_app):
    parts = [
        event(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": CALL["id"],
                        "type": "function",
                        "function": {"name": "read", "arguments": "{"},
                    }
                ]
            }
        ),
        event({"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}),
        event(finish="tool_calls"),
        event(usage=USAGE),
        b"data: [DONE]\n\n",
    ]
    app, upstream, _ = make_app(Upstream(parts, gate_after=0))
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, body={**BODY, "tools": [TOOL]})
        try:
            await asyncio.wait_for(upstream.waiting.wait(), 1)
            assert raw.sent == []
        finally:
            upstream.release.set()
            await raw.finish()
        assert raw.status == 200
        assert raw.events[1]["choices"][0]["delta"] == {"tool_calls": [{"index": 0, **CALL}]}
        assert raw.events[-1]["choices"][0]["finish_reason"] == "tool_calls"
        assert raw.body.endswith(b"data: [DONE]\n\n")


@pytest.mark.parametrize("text", ["", "prefix"])
async def test_length_terminal_and_optional_usage_decode_in_installed_sdk(make_app, text):
    app, _, attempts = make_app(Upstream(stream_parts(text, finish="length")))
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, body={**BODY, "stream_options": {"include_usage": True}})
        await raw.finish()
        assert raw.status == 200 and len(attempts) == 1
    with OpenAI(
        api_key="synthetic-sdk-client-key",
        max_retries=0,
        _strict_response_validation=True,
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(
                    200, headers={"content-type": "text/event-stream"}, content=raw.body
                )
            )
        ),
    ) as sdk:
        with sdk.chat.completions.create(
            model="model-a", messages=[{"role": "user", "content": "synthetic"}], stream=True
        ) as stream:
            chunks = list(stream)
        assert (
            "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices)
            == text
        )
        assert chunks[-2].choices[0].finish_reason == "length"
        assert chunks[-1].usage.total_tokens == 5 and chunks[-1].choices == []


async def test_final_send_is_deadline_bounded_and_keeps_admission_until_exit(make_app):
    blocked = asyncio.Event()

    async def send(message):
        if b"[DONE]" in message.get("body", b""):
            blocked.set()
            await asyncio.Event().wait()

    app, upstream, _ = make_app(limits={"request_timeout_seconds": 0.1})
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, send_hook=send)
        await asyncio.wait_for(blocked.wait(), 1)
        assert upstream.eof.is_set() and upstream.closed.is_set()
        assert raw.first_text.is_set() and app.state.admission.active == 1
        await raw.finish()
        assert app.state.admission.active == 0 and b"[DONE]" not in raw.body
        assert raw.scope["state"]["stream_outcome"] == "timeout"
        assert_outcome(app, "timeout", status=200)
        # Generation succeeded, but the HTTP request did not finish delivery.
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_provider_calls_total", {"provider": "openai", "outcome": "complete"}
            )
            == 1
        )


async def test_blocked_downstream_send_prevents_next_upstream_read_and_hits_deadline(make_app):
    blocked = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.body":
            blocked.set()
            await asyncio.Event().wait()

    app, upstream, _ = make_app(limits={"request_timeout_seconds": 0.1})
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, send_hook=send)
        await asyncio.wait_for(blocked.wait(), 1)
        assert upstream.reads == [0, 1] and not upstream.eof.is_set()
        assert app.state.admission.active == 1
        await raw.finish()
        assert upstream.reads == [0, 1] and upstream.closed.is_set()
        assert app.state.admission.active == 0
        assert b"[DONE]" not in raw.body
        assert_outcome(app, "timeout", status=200)


@pytest.mark.parametrize("prefix", [False, True])
@pytest.mark.parametrize("termination", ["disconnect", "cancel"])
async def test_cancellation_metrics_count_terminal_outcome_not_an_unsent_status(
    make_app, caplog, prefix, termination
):
    app, upstream, _ = make_app(Upstream(gate_after=1 if prefix else 0, resist_cleanup=True))
    with caplog.at_level("INFO", logger="gateway7"):
        async with app.router.lifespan_context(app):
            raw = RawHTTP(app)
            await asyncio.wait_for(raw.first_text.wait() if prefix else upstream.waiting.wait(), 1)
            if termination == "disconnect":
                raw.incoming.put_nowait({"type": "http.disconnect"})
            else:
                raw.task.cancel()
            await asyncio.wait_for(upstream.closing.wait(), 1)
            try:
                assert not app.state.metrics.http_outcomes.collect()[0].samples
                assert app.state.admission.active == 1 and not raw.task.done()
            finally:
                upstream.cleanup_release.set()
                if termination == "cancel":
                    with pytest.raises(asyncio.CancelledError):
                        await raw.finish()
                else:
                    await raw.finish()
            assert_outcome(app, "cancelled", status=200 if prefix else None)
            assert raw.status == (200 if prefix else None)
            assert app.state.admission.active == 0
            assert not raw.body.endswith(b"data: [DONE]\n\n")
    assert "outcome=cancelled component=http" in caplog.text
    assert "outcome=http_500 component=http" not in caplog.text


@pytest.mark.parametrize("termination", ["disconnect", "send-failure", "cancel"])
async def test_termination_retains_capacity_until_provider_cleanup_really_exits(
    make_app, termination
):
    failed_send = asyncio.Event()

    async def send(message):
        if termination == "send-failure" and message["type"] == "http.response.body":
            failed_send.set()
            raise OSError("PRIVATE-SEND-FAILURE")

    app, upstream, attempts = make_app(
        Upstream(gate_after=1, resist_cleanup=True), limits={"max_concurrent_requests": 1}
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app, send_hook=send)
        if termination == "send-failure":
            await asyncio.wait_for(failed_send.wait(), 1)
        else:
            await asyncio.wait_for(raw.first_text.wait(), 1)
            if termination == "disconnect":
                raw.incoming.put_nowait({"type": "http.disconnect"})
            else:
                raw.task.cancel()
        await asyncio.wait_for(upstream.closing.wait(), 1)
        try:
            assert app.state.admission.active == 1 and not raw.task.done()
            rejected = RawHTTP(app)
            await rejected.finish()
            assert rejected.status == 503 and len(attempts) == 1
            assert json.loads(rejected.body)["error"]["code"] == "overloaded"
            assert not upstream.closed.is_set()
            if termination == "cancel":
                raw.task.cancel()
                await asyncio.sleep(0)
                assert app.state.admission.active == 1 and not raw.task.done()
        finally:
            upstream.cleanup_release.set()
            if termination == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await raw.finish()
            else:
                await raw.finish()
        assert app.state.admission.active == 0 and upstream.closed.is_set()
        assert b"[DONE]" not in raw.body and b"PRIVATE-SEND-FAILURE" not in raw.body
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_provider_calls_total", {"provider": "openai", "outcome": "cancelled"}
            )
            == 1
        )
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_http_request_outcomes_total",
                {"route": "openai_chat", "outcome": "cancelled"},
            )
            == 1
        )
        assert (
            app.state.metrics.registry.get_sample_value(
                "gateway7_http_request_outcomes_total",
                {"route": "openai_chat", "outcome": "overloaded"},
            )
            == 1
        )


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


@pytest.mark.parametrize("termination", ["disconnect", "hook-timeout"])
async def test_resistant_request_hook_cannot_forward_after_cancellation(
    make_app, monkeypatch, termination
):
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Gate:
        async def handle(self, request, context, call_next):
            return await call_next(request)

        async def prepare_early_stream(self, request, context):
            assert not hasattr(request, "stream_mode") and not hasattr(request, "model")
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
            return request

    module = ModuleType("gateway7_synthetic_early_gate")
    module.PLUGIN = PluginDescriptor("early-test", 2, Settings, lambda _: Gate())
    monkeypatch.setitem(sys.modules, module.__name__, module)
    app, _, attempts = make_app(
        plugins={"gate": {"module": module.__name__}},
        middleware=["gate"],
        limits={
            "max_concurrent_requests": 1,
            "hook_timeout_seconds": 0.05 if termination == "hook-timeout" else 10,
        },
    )
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app)
        await asyncio.wait_for(entered.wait(), 1)
        if termination == "disconnect":
            raw.incoming.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(cancelled.wait(), 1)
        try:
            assert app.state.admission.active == 1 and not raw.task.done()
            assert not attempts and not raw.sent
        finally:
            release.set()
            await raw.finish()
        assert not attempts and app.state.admission.active == 0
        if termination == "disconnect":
            assert not raw.sent
        else:
            assert raw.status == 504 and json.loads(raw.body)["error"]["code"] == "timeout"


async def test_auth_model_body_and_admission_boundaries_are_unchanged(make_app):
    app, upstream, attempts = make_app(
        Upstream(gate_after=1), limits={"max_concurrent_requests": 1, "max_body_bytes": 512}
    )
    async with app.router.lifespan_context(app):
        active = RawHTTP(app)
        await asyncio.wait_for(active.first_text.wait(), 1)
        try:
            for change, status in [("auth", 401), ("model", 403), ("body", 413), ("mode", 400)]:
                raw = RawHTTP(
                    app,
                    body={**BODY, "model": "forbidden"} if change == "model" else None,
                    wire=b"x" * 513 if change in ("auth", "body") else None,
                    headers=[(b"x-gateway7-stream-mode", b"invalid")] if change == "mode" else None,
                )
                if change == "auth":
                    raw.scope["headers"].remove(AUTH)
                await raw.finish()
                assert raw.status == status
            assert len(attempts) == 1
            assert (
                app.state.metrics.registry.get_sample_value("gateway7_admission_rejections_total")
                == 0
            )
            rejected = RawHTTP(app)
            await rejected.finish()
            assert rejected.status == 503 and len(attempts) == 1
        finally:
            upstream.release.set()
            await active.finish()


async def test_common_runner_accepts_non_chat_packet_encoder(make_app):
    from starlette.requests import Request

    app, _, attempts = make_app()
    async with app.router.lifespan_context(app):
        request = Request(
            {
                "type": "http",
                "app": app,
                "state": {
                    "deadline": asyncio.get_running_loop().time() + 1,
                    "request_id": "synthetic-reusable",
                    "principal": app.state.access.authenticate(
                        [(b"authorization", f"Bearer {TOKEN}".encode())]
                    ),
                },
            }
        )

        class Encoder:
            def text(self, text):
                return b"event: fragment\ndata: " + text.encode() + b"\n\n"

            def complete(self, response):
                assert response == {"native_result": "reusable"}
                return b"event: complete\ndata: {}\n\n"

            def error(self, error):
                return b"event: failed\ndata: {}\n\n"

        async def run(on_text):
            await on_text("reusable")
            return {"native_result": "reusable"}

        sent = []

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)

        # The shared runner does not require Chat models or impose [DONE].
        await _EarlySSE(request, run, Encoder())(request.scope, receive, send)
        assert (
            b"".join(item.get("body", b"") for item in sent)
            == b"event: fragment\ndata: reusable\n\nevent: complete\ndata: {}\n\n"
        )
        assert app.state.admission.active == 0 and not attempts


@pytest.mark.parametrize("failure_at", [1, 2])
async def test_common_runner_task_creation_failures_rollback_and_reap(
    make_app, monkeypatch, failure_at
):
    from starlette.requests import Request

    app, _, attempts = make_app()
    calls = []
    create_task = asyncio.create_task
    creations = 0

    def fail_creation(work):
        nonlocal creations
        creations += 1
        if creations == failure_at:
            raise RuntimeError("Synthetic task creation failure")
        return create_task(work)

    async def run(on_text):
        calls.append(1)
        return ChatResponse(text="unused")

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        raise AssertionError("No response should start")

    async with app.router.lifespan_context(app):
        request = Request(
            {
                "type": "http",
                "app": app,
                "state": {
                    "deadline": asyncio.get_running_loop().time() + 1,
                    "request_id": "synthetic-creation",
                    "principal": app.state.access.authenticate(
                        [(b"authorization", f"Bearer {TOKEN}".encode())]
                    ),
                },
            },
            receive,
        )
        with monkeypatch.context() as patch:
            patch.setattr(app_module.asyncio, "create_task", fail_creation)
            with pytest.raises(RuntimeError, match="Synthetic task creation failure"):
                await _EarlySSE(request, run, EarlyChatEncoder("model-a", "synthetic-creation"))(
                    request.scope, receive, send
                )
        assert not calls and not attempts and app.state.admission.active == 0


async def test_common_runner_json_error_delivery_is_also_admitted_and_bounded(make_app):
    from starlette.requests import Request

    app, _, _ = make_app()
    sending_error = asyncio.Event()
    sent = []

    async def run(on_text):
        raise GatewayError("policy_denied")

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.body":
            sending_error.set()
            await asyncio.Event().wait()
        sent.append(message)

    async with app.router.lifespan_context(app):
        request = Request(
            {
                "type": "http",
                "app": app,
                "state": {
                    "deadline": asyncio.get_running_loop().time() + 0.1,
                    "request_id": "synthetic-error",
                    "principal": app.state.access.authenticate(
                        [(b"authorization", f"Bearer {TOKEN}".encode())]
                    ),
                },
            },
            receive,
        )
        pending = asyncio.create_task(
            _EarlySSE(request, run, EarlyChatEncoder("model-a", "synthetic-error"))(
                request.scope, receive, send
            )
        )
        await asyncio.wait_for(sending_error.wait(), 1)
        assert app.state.admission.active == 1 and sent[0]["status"] == 403
        await asyncio.wait_for(pending, 1)
        assert app.state.admission.active == 0 and len(sent) == 1


@pytest.mark.parametrize("prefix", [False, True])
async def test_expired_deadline_wins_over_provider_failure_without_false_success(make_app, prefix):
    class Provider:
        def __init__(self):
            self.calls = 0
            self.closed = asyncio.Event()

        async def complete_early(self, request, *, on_text, model=None):
            self.calls += 1
            try:
                if prefix:
                    await on_text("prefix")
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise RuntimeError("PRIVATE-LATE-FAILURE")
            finally:
                self.closed.set()

        async def aclose(self):
            pass

    provider = Provider()
    app, _, _ = make_app(provider=provider, limits={"request_timeout_seconds": 0.05})
    async with app.router.lifespan_context(app):
        # Earlier test apps form cyclic graphs; collect them before starting
        # this deliberately small real deadline, not during request admission.
        gc.collect()
        raw = RawHTTP(app)
        await raw.finish()
        assert provider.calls == 1 and provider.closed.is_set()
        assert raw.scope["state"]["stream_outcome"] == "timeout"
        assert app.state.admission.active == 0
        assert b"PRIVATE-LATE-FAILURE" not in raw.body and b"[DONE]" not in raw.body
        if prefix:
            assert raw.status == 200 and raw.first_text.is_set()
            assert not any(
                choice["finish_reason"] for item in raw.events for choice in item["choices"]
            )
        else:
            assert raw.status == 504 and json.loads(raw.body)["error"]["code"] == "timeout"


async def test_explicit_cancellation_wins_over_resistant_provider_failure(make_app):
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    class Provider:
        async def complete_early(self, request, *, on_text, model=None):
            try:
                await on_text("prefix")
                entered.set()
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise RuntimeError("PRIVATE-CANCEL-FAILURE")
            finally:
                cleaned.set()

        async def aclose(self):
            pass

    app, _, _ = make_app(provider=Provider())
    async with app.router.lifespan_context(app):
        raw = RawHTTP(app)
        await asyncio.wait_for(entered.wait(), 1)
        raw.task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await raw.finish()
        assert cleaned.is_set() and app.state.admission.active == 0
        assert raw.first_text.is_set() and b"[DONE]" not in raw.body
        assert not any("error" in item for item in raw.events)
        assert raw.scope["state"]["stream_outcome"] == "cancelled"


@pytest.mark.parametrize("blocked", [False, True])
async def test_already_expired_runner_skips_work_and_bounds_json_504_delivery(make_app, blocked):
    from starlette.requests import Request

    app, _, _ = make_app()
    calls = []
    sent = []

    async def run(on_text):
        calls.append(1)
        return ChatResponse(text="must not run")

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if blocked and message["type"] == "http.response.body":
            await asyncio.Event().wait()
        sent.append(message)

    async with app.router.lifespan_context(app):
        request = Request(
            {
                "type": "http",
                "app": app,
                "state": {
                    "deadline": asyncio.get_running_loop().time() - 1,
                    "request_id": "synthetic-expired",
                    "principal": app.state.access.authenticate(
                        [(b"authorization", f"Bearer {TOKEN}".encode())]
                    ),
                },
            },
            receive,
        )
        await asyncio.wait_for(
            _EarlySSE(request, run, EarlyChatEncoder("model-a", "synthetic-expired"))(
                request.scope, receive, send
            ),
            0.5,
        )
        assert not calls and app.state.admission.active == 0
        assert sent[0]["status"] == 504
        if not blocked:
            assert json.loads(sent[1]["body"])["error"]["code"] == "timeout"
        assert request.state.stream_outcome == "timeout"

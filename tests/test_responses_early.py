"""Independent native early-delivery acceptance tests, with no callback API assumptions.

Fixtures follow the synthetic native goldens and installed SDK event shapes. Only
the HTTP transport is substituted: create_app, HTTPProvider, parsing, policies,
encoding, admission and disconnect handling remain production implementations.
"""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import importlib
import json
from types import SimpleNamespace

import httpx
from openai.types.responses import Response, ResponseStreamEvent
from pydantic import TypeAdapter
import pytest

from gateway7.app import create_app
from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.providers import build_provider

TOKEN = "gateway7-synthetic-native-early-client"
KEY = "gateway7-synthetic-native-early-provider"
MODEL = "gpt-4.1-mini"
PATH = "/v1/responses"
AUTH = (b"authorization", ("Bearer " + TOKEN).encode())
EARLY = (b"x-gateway7-stream-mode", b"early")
BODY = {"model": MODEL, "input": "hello", "stream": True, "store": False}
USAGE = {
    "input_tokens": 7,
    "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 1},
    "output_tokens": 4,
    "output_tokens_details": {"reasoning_tokens": 1},
    "total_tokens": 11,
}
FUNCTION = {"type": "function", "name": "read", "parameters": {"type": "object"}}
CUSTOM = {"type": "custom", "name": "apply_patch", "format": {"type": "text"}}
TOOL_TYPES = {"function_call", "custom_tool_call"}
SDK_EVENT = TypeAdapter(ResponseStreamEvent)
SDK_RESPONSE = TypeAdapter(Response)
WAIT = 1.0


def message(*texts, item_id="msg_original_early"):
    return {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "status": "completed",
        "content": [
            {"type": "output_text", "text": text, "annotations": []}
            for text in (texts or ("prefixsuffix",))
        ],
    }


def tool(kind="function_call"):
    return {
        "type": kind,
        "id": "item_original_tool",
        "call_id": "call_distinct_from_item",
        "name": "read" if kind == "function_call" else "apply_patch",
        "status": "completed",
        "arguments" if kind == "function_call" else "input": (
            '{"path":"SYNTHETIC_RAW_ARGUMENT"}'
            if kind == "function_call"
            else "*** Begin Patch\n+SYNTHETIC_RAW_INPUT\n*** End Patch\n"
        ),
    }


def snapshot(output=(), *, tools=(), status="in_progress"):
    return {
        "id": "resp_original_early",
        "object": "response",
        "created_at": 1800000000.0,
        "model": "synthetic-native-source-model",
        "status": status,
        "output": deepcopy(list(output)),
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": deepcopy(list(tools)),
        "usage": deepcopy(USAGE) if status == "completed" else None,
        "error": None,
        "incomplete_details": None,
    }


def checked_events(events):
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
        SDK_EVENT.validate_python(event, strict=True)
    SDK_RESPONSE.validate_python(events[-1]["response"], strict=True)
    return events


def native_events(output=None, *, tools=()):
    """Build native lifecycle records independently of the gateway's encoder."""
    output = [message()] if output is None else output
    events = []

    def emit(kind, **fields):
        events.append({"type": kind, **deepcopy(fields)})

    emit("response.created", response=snapshot(tools=tools))
    emit("response.in_progress", response=snapshot(tools=tools))
    for index, final in enumerate(output):
        kind = final["type"]
        initial = {**final, "status": "in_progress"}
        field = "arguments" if kind == "function_call" else "input"
        if kind in ("message", "reasoning"):
            initial["content" if kind == "message" else "summary"] = []
        else:
            initial[field] = ""
        emit("response.output_item.added", output_index=index, item=initial)
        refs = {"output_index": index, "item_id": final["id"]}
        if kind in ("message", "reasoning"):
            summary = kind == "reasoning"
            family = "reasoning_summary_part" if summary else "content_part"
            text_family = "reasoning_summary_text" if summary else "output_text"
            for sub, part in enumerate(final["summary" if summary else "content"]):
                ref = {**refs, "summary_index" if summary else "content_index": sub}
                emit("response." + family + ".added", **ref, part={**part, "text": ""})
                text = part["text"]
                extra = {} if summary else {"logprobs": []}
                for delta in ("", text[: len(text) // 2], text[len(text) // 2 :]):
                    emit("response." + text_family + ".delta", **ref, delta=delta, **extra)
                emit("response." + text_family + ".done", **ref, text=text, **extra)
                emit("response." + family + ".done", **ref, part=part)
        else:
            family = (
                "function_call_arguments" if kind == "function_call" else "custom_tool_call_input"
            )
            text = final[field]
            for delta in (text[: len(text) // 2], text[len(text) // 2 :]):
                emit("response." + family + ".delta", **refs, delta=delta)
            emit("response." + family + ".done", **refs, **{field: text})
        emit("response.output_item.done", output_index=index, item=final)
    emit("response.completed", response=snapshot(output, tools=tools, status="completed"))
    return checked_events(events)


def frame(event):
    return (
        "event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=True) + "\n\n"
    ).encode("ascii")


def decode(body):
    """Decode complete native frames only; transport chunks need not be frames."""
    events = []
    for packet in body.split(b"\n\n")[:-1]:
        names = [line[7:] for line in packet.splitlines() if line.startswith(b"event: ")]
        data = [line[6:] for line in packet.splitlines() if line.startswith(b"data: ")]
        assert len(names) == len(data) == 1, packet
        event = json.loads(data[0])
        assert names == [event["type"].encode("ascii")]
        events.append(event)
    return events


def first_delta(events):
    return next(
        i
        for i, event in enumerate(events)
        if event["type"] == "response.output_text.delta" and event["delta"]
    )


class SendBarrier:
    """Accumulate bytes, then hold the send completing the first matching event."""

    def __init__(self, kind="response.output_text.delta"):
        self.kind = kind
        self.blocked = asyncio.Event()
        self.release = asyncio.Event()
        self.pending = b""

    async def __call__(self, message):
        self.pending += message.get("body", b"")
        complete, separator, pending = self.pending.rpartition(b"\n\n")
        if not separator:
            return
        # Keep partial UTF-8 and frame delimiters as bytes until the frame closes.
        self.pending = pending
        if not self.blocked.is_set() and any(
            event["type"] == self.kind
            and (self.kind != "response.output_text.delta" or event["delta"])
            for event in decode(complete + separator)
        ):
            self.blocked.set()
            await self.release.wait()


class Upstream(httpx.AsyncByteStream):
    def __init__(self, events=None, *, chunks=None, gate_after=None, hold_close=False):
        self.chunks = (
            [frame(event) for event in (events or native_events())] if chunks is None else chunks
        )
        self.gate_after = gate_after
        self.hold_close = hold_close
        self.reads = []
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.eof = asyncio.Event()
        self.closing = asyncio.Event()
        self.closed = asyncio.Event()
        self.cleanup_release = asyncio.Event()

    async def __aiter__(self):
        for index, chunk in enumerate(self.chunks):
            if self.gate_after is not None and index == self.gate_after + 1:
                self.waiting.set()
                await self.release.wait()
            self.reads.append(index)
            yield chunk
        self.eof.set()

    async def aclose(self):
        self.closing.set()
        while self.hold_close and not self.cleanup_release.is_set():
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
        headers=(EARLY,),
        auth=True,
        wire=None,
        send_hook=None,
        delay_body=False,
    ):
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": PATH,
            "raw_path": PATH.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                *([AUTH] if auth else []),
                *headers,
            ],
            "client": ("synthetic", 1000),
            "server": ("synthetic.invalid", 80),
        }
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait(
            {
                "type": "http.request",
                "body": json.dumps(BODY if body is None else body).encode()
                if wire is None
                else wire,
                "more_body": False,
            }
        )
        self.sent = []
        self.reads = 0
        self.reading = asyncio.Event()
        self.body_release = asyncio.Event()
        if not delay_body:
            self.body_release.set()
        self.first_text = asyncio.Event()
        self.send_hook = send_hook
        self.task = asyncio.create_task(app(self.scope, self.receive, self.send))

    async def receive(self):
        self.reading.set()
        await self.body_release.wait()
        message = await self.incoming.get()
        self.reads += 1
        return message

    async def send(self, message):
        if self.send_hook is not None:
            await self.send_hook(message)
        self.sent.append(dict(message))
        if any(
            event["type"] == "response.output_text.delta" and event["delta"]
            for event in self.events
        ):
            self.first_text.set()

    @property
    def body(self):
        return b"".join(message.get("body", b"") for message in self.sent)

    @property
    def events(self):
        return decode(self.body)

    @property
    def status(self):
        return next((m["status"] for m in self.sent if m["type"] == "http.response.start"), None)

    async def finish(self, timeout=WAIT):
        await asyncio.wait_for(asyncio.shield(self.task), timeout)

    async def wait_for(self, signal):
        waiter = asyncio.create_task(signal.wait())
        try:
            done, _ = await asyncio.wait(
                (self.task, waiter), timeout=WAIT, return_when=asyncio.FIRST_COMPLETED
            )
            if waiter not in done:
                if self.task in done:
                    await self.finish()
                pytest.fail(
                    f"Expected stream barrier; HTTP status={self.status}, body={self.body!r}"
                )
        finally:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)


@pytest.fixture
def early_http(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("GATEWAY7_NATIVE_EARLY_TOKEN", TOKEN)

    @asynccontextmanager
    async def open_http(upstream=None, *, model=MODEL, **updates):
        upstream = Upstream() if upstream is None else upstream
        attempts, requests = [], []

        async def handle(request):
            attempts.append(request)
            assert str(request.url) == "https://api.openai.com/v1/responses"
            assert request.headers["authorization"] == "Bearer " + KEY
            assert not any(name.startswith("x-gateway7-") for name in request.headers)
            payload = json.loads(request.content)
            assert payload["model"] == model and payload["stream"] is True
            assert payload["store"] is False and "messages" not in payload
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=upstream
            )

        provider = build_provider(
            ProviderConfig(kind="openai", model=model), KEY, transport=httpx.MockTransport(handle)
        )
        config = GatewayConfig.model_validate(
            {
                "provider": {"kind": "openai", "model": model},
                "auth": {
                    "enabled": True,
                    "clients": {
                        "synthetic": {
                            "token_env": "GATEWAY7_NATIVE_EARLY_TOKEN",
                            "models": [model],
                        }
                    },
                },
                **updates,
            }
        )

        def post(**kwargs):
            raw = RawHTTP(app, **kwargs)
            requests.append(raw)
            return raw

        with monkeypatch.context() as patch:
            patch.setattr(
                importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
            )
            app = create_app(config=config)
            async with app.router.lifespan_context(app):
                try:
                    yield app, upstream, attempts, post
                finally:
                    upstream.release.set()
                    upstream.cleanup_release.set()
                    for raw in requests:
                        raw.body_release.set()
                        if not raw.task.done():
                            raw.task.cancel()
                    await asyncio.wait_for(
                        asyncio.gather(
                            *(raw.task for raw in requests),
                            return_exceptions=True,
                        ),
                        2,
                    )
        assert provider._client.is_closed

    return open_http


def assert_json_error(raw, status, code):
    assert raw.status == status, raw.body
    assert dict(raw.sent[0]["headers"])[b"content-type"].startswith(b"application/json")
    assert json.loads(raw.body)["error"]["code"] == code
    assert b"data:" not in raw.body and b"SYNTHETIC_PRIVATE" not in raw.body


def assert_tools_withheld(raw):
    """Before strict validation, executable fields must be absent or blank."""
    assert b"SYNTHETIC_RAW" not in raw.body
    for event in raw.events:
        assert not event["type"].startswith(
            ("response.function_call_arguments.", "response.custom_tool_call_input.")
        )
        assert not (
            event["type"] == "response.output_item.done" and event["item"]["type"] in TOOL_TYPES
        )
        # Both item events and enclosing response snapshots can carry tool data.
        # Do not apply this restriction to post-validation checked playback.
        snapshots = [event.get("item", {}), *event.get("response", {}).get("output", [])]
        for item in snapshots:
            if item.get("type") in TOOL_TYPES:
                field = "arguments" if item["type"] == "function_call" else "input"
                assert item.get(field, "") == "", "Executable tool payload before strict validation"


def assert_native(raw, source):
    assert raw.status == 200, raw.body
    assert dict(raw.sent[0]["headers"])[b"content-type"].startswith(b"text/event-stream")
    assert raw.body.endswith(b"\n\n") and b"[DONE]" not in raw.body
    events = raw.events
    for event in events:
        SDK_EVENT.validate_python(event, strict=True)
        assert "choices" not in event
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert events[0]["type"] == "response.created" and events[-1]["type"] == "response.completed"
    assert sum(event["type"] == "response.completed" for event in events) == 1
    terminal = events[-1]["response"]
    SDK_RESPONSE.validate_python(terminal, strict=True)
    output = source["output"]
    assert terminal["output"] == output and terminal["usage"] == USAGE
    for event in events:
        if "response" in event:
            for field in ("id", "object", "model", "created_at"):
                assert event["response"][field] == source[field]
        if "item_id" in event:
            assert event["item_id"] == output[event["output_index"]]["id"]
    assert [
        (e["output_index"], e["item"]["id"])
        for e in events
        if e["type"] == "response.output_item.added"
    ] == [(i, item["id"]) for i, item in enumerate(output)]
    assert [
        (e["output_index"], e["item"]) for e in events if e["type"] == "response.output_item.done"
    ] == list(enumerate(output))
    parts = [
        (i, j, part)
        for i, item in enumerate(output)
        if item["type"] == "message"
        for j, part in enumerate(item["content"])
    ]
    assert [
        (e["output_index"], e["content_index"], e["part"])
        for e in events
        if e["type"] == "response.content_part.done"
    ] == parts
    for index, sub, part in parts:
        assert (
            "".join(
                e["delta"]
                for e in events
                if e["type"] == "response.output_text.delta"
                and (e["output_index"], e["content_index"]) == (index, sub)
            )
            == part["text"]
        )
        assert [
            e["text"]
            for e in events
            if e["type"] == "response.output_text.done"
            and (e["output_index"], e["content_index"]) == (index, sub)
        ] == [part["text"]]
    return events


def captured_events(events):
    """A frozen send capture for helper controls, not an application or route."""
    body = b"".join(frame(event) for event in events)
    return SimpleNamespace(
        status=200,
        sent=[
            {"type": "http.response.start", "headers": [(b"content-type", b"text/event-stream")]}
        ],
        body=body,
        events=decode(body),
    )


@pytest.mark.parametrize(
    "kind,definition", [("function_call", FUNCTION), ("custom_tool_call", CUSTOM)]
)
@pytest.mark.parametrize("carrier", ["item-added", "response-output"])
def test_helper_control_rejects_tool_payload_in_prevalidation_snapshots(kind, definition, carrier):
    events = native_events([tool(kind)], tools=[definition])
    assert_tools_withheld(captured_events(events[:3]))
    field = "arguments" if kind == "function_call" else "input"
    leaked = {**events[2]["item"], field: tool(kind)[field][:3]}
    assert "SYNTHETIC" not in leaked[field]
    if carrier == "item-added":
        events[2]["item"] = leaked
    else:
        events[1]["response"]["output"] = [leaked]
    with pytest.raises(AssertionError, match="Executable tool payload"):
        assert_tools_withheld(captured_events(events[:3]))
    # The same bytes are legitimate checked playback after strict validation;
    # the final canonical oracle must not impose the pre-validation restriction.
    assert_native(captured_events(events), events[-1]["response"])


@pytest.mark.parametrize("kind", ["response.output_text.delta", "response.completed"])
async def test_helper_control_split_frames_hold_reads_until_send_resumes(kind):
    events = native_events([message("🌍")])
    chunks = [frame(event).replace(b"\\ud83c\\udf0d", "🌍".encode()) for event in events]
    upstream = Upstream(chunks=chunks)
    barrier = SendBarrier(kind)
    accepted = []

    async def pump():
        async for chunk in upstream:
            for byte in chunk:
                part = bytes([byte])
                await barrier({"type": "http.response.body", "body": part, "more_body": True})
                accepted.append(part)

    task = asyncio.create_task(pump())
    waiter = asyncio.create_task(barrier.blocked.wait())
    try:
        done, _ = await asyncio.wait(
            (task, waiter), timeout=WAIT, return_when=asyncio.FIRST_COMPLETED
        )
        assert waiter in done, "Split native frame did not reach the send barrier"
        target = first_delta(events) if kind == "response.output_text.delta" else len(events) - 1
        assert upstream.reads == list(range(target + 1))
        assert not task.done() and not upstream.eof.is_set()
        assert events[target] not in decode(b"".join(accepted))
        barrier.release.set()
        await asyncio.wait_for(asyncio.shield(task), WAIT)
        assert upstream.reads == list(range(len(events))) and upstream.eof.is_set()
        assert decode(b"".join(accepted)) == events
    finally:
        barrier.release.set()
        for pending in (task, waiter):
            if not pending.done():
                pending.cancel()
        await asyncio.wait_for(asyncio.gather(task, waiter, return_exceptions=True), WAIT)
        await upstream.aclose()


async def test_leading_nonempty_native_text_precedes_upstream_eof(early_http):
    events = native_events()
    async with early_http(Upstream(events, gate_after=first_delta(events))) as (
        app,
        up,
        attempts,
        post,
    ):
        raw = post()
        await raw.wait_for(raw.first_text)
        assert raw.status == 200 and not up.eof.is_set() and not up.release.is_set()
        assert app.state.admission.active == 1
        assert not any(e["type"] == "response.completed" for e in raw.events)
        up.release.set()
        await raw.finish()
        assert_native(raw, events[-1]["response"])
        assert len(attempts) == 1 and up.closed.is_set() and app.state.admission.active == 0


async def test_opaque_requested_model_keeps_native_early_source_identity_and_controls(early_http):
    selected = "ft:synthetic/account:model/" + "x" * 160
    events = native_events([message(), tool()], tools=[FUNCTION])
    async with early_http(
        Upstream(events, gate_after=first_delta(events)), model=selected
    ) as (_, up, attempts, post):
        raw = post(body={**BODY, "model": selected, "tools": [FUNCTION]})
        await raw.wait_for(raw.first_text)
        assert_tools_withheld(raw)
        up.release.set()
        await raw.finish()
        assert_native(raw, events[-1]["response"])
        assert len(attempts) == 1 and attempts[0].method == "POST"
        assert json.loads(attempts[0].content)["model"] == selected


@pytest.mark.parametrize(
    "headers", [(), ((b"x-gateway7-stream-mode", b"buffered"),)], ids=["default", "buffered"]
)
async def test_buffered_native_response_keeps_full_policy_before_headers(early_http, headers):
    events = native_events([message("SYNTHETIC_PRIVATE_OUTPUT")])
    async with early_http(
        Upstream(events, gate_after=first_delta(events)),
        plugins={"guard": policy("SYNTHETIC_PRIVATE_OUTPUT", "response")},
        middleware=["guard"],
    ) as (_, up, attempts, post):
        raw = post(headers=headers)
        await raw.wait_for(up.waiting)
        assert raw.sent == []
        up.release.set()
        await raw.finish()
        assert_json_error(raw, 403, "policy_denied")
        assert len(attempts) == 1


def policy(term, phase):
    return {
        "module": "gateway7.plugins.content_policy",
        "settings": {"terms": [term], "phase": phase},
    }


async def test_request_only_mask_runs_before_native_early_forwarding(early_http):
    events = native_events()
    async with early_http(
        Upstream(events, gate_after=first_delta(events)),
        plugins={
            "mask": {"module": "gateway7.plugins.email_mask", "settings": {"phase": "request"}},
        },
        middleware=["mask"],
    ) as (_, up, attempts, post):
        raw = post(body={**BODY, "input": "fixture@example.com"})
        await raw.wait_for(raw.first_text)
        assert json.loads(attempts[0].content)["input"] == "[EMAIL]" and not up.eof.is_set()
        up.release.set()
        await raw.finish()
        assert_native(raw, events[-1]["response"])


@pytest.mark.parametrize("case", ["response", "both", "earlier-denial"])
async def test_unsafe_native_early_policy_chain_stops_before_upstream(early_http, case):
    plugins = {"unsafe": policy("synthetic", "both" if case == "both" else "response")}
    middleware = ["unsafe"]
    if case == "earlier-denial":
        plugins["deny"] = policy("hello", "request")
        middleware.insert(0, "deny")
    async with early_http(plugins=plugins, middleware=middleware) as (_, _, attempts, post):
        raw = post()
        await raw.finish()
        assert_json_error(
            raw,
            403 if case == "earlier-denial" else 400,
            "policy_denied" if case == "earlier-denial" else "invalid_request",
        )
        assert not attempts


@pytest.mark.parametrize("case", ["auth", "model"])
async def test_native_early_auth_and_model_boundaries_do_not_attempt_provider(early_http, case):
    async with early_http() as (app, _, attempts, post):
        app.state.admission.limit = 0
        raw = post(
            auth=case != "auth",
            wire=b"SYNTHETIC_PRIVATE_NOT_JSON" if case == "auth" else None,
            body={**BODY, "model": "forbidden-model"},
        )
        await raw.finish()
        assert_json_error(
            raw,
            401 if case == "auth" else 403,
            "unauthorized" if case == "auth" else "model_forbidden",
        )
        assert not attempts and app.state.admission.active == 0
        assert raw.reads == (0 if case == "auth" else 1)


@pytest.mark.parametrize("failure", ["malformed", "truncated", "invalid-tool"])
async def test_late_native_failure_preserves_prefix_but_never_commits_tools(early_http, failure):
    call = tool()
    if failure == "invalid-tool":
        call["arguments"] = '{"path":"SYNTHETIC_PRIVATE_INVALID_ARGUMENT"'
    events = native_events([message(), call], tools=[FUNCTION])
    chunks = [frame(event) for event in events[:-1]]
    if failure == "malformed":
        chunks.append(b"event: response.completed\ndata: {SYNTHETIC_PRIVATE_MALFORMED\n\n")
    elif failure == "invalid-tool":
        chunks.append(frame(events[-1]))
    async with early_http(Upstream(chunks=chunks, gate_after=first_delta(events))) as (
        app,
        up,
        _,
        post,
    ):
        raw = post(body={**BODY, "tools": [FUNCTION]})
        await raw.wait_for(raw.first_text)
        assert not up.eof.is_set()
        up.release.set()
        await raw.finish()
        assert raw.status == 200 and raw.first_text.is_set()
        assert_tools_withheld(raw)
        assert b"[DONE]" not in raw.body and b"SYNTHETIC_PRIVATE" not in raw.body
        assert not any(
            e["type"] in ("response.completed", "response.incomplete") for e in raw.events
        )
        for event in raw.events:
            SDK_EVENT.validate_python(event, strict=True)
            assert "choices" not in event and not isinstance(event.get("error"), dict)
        assert up.closed.is_set() and app.state.admission.active == 0


@pytest.mark.parametrize(
    "profile", ["interleaved-parts", "interleaved-messages", "reasoning-first", "tool-first"]
)
async def test_complex_native_profiles_keep_canonical_indices_and_original_ids(early_http, profile):
    tools = [FUNCTION] if profile == "tool-first" else []
    if profile == "interleaved-parts":
        events = native_events([message("first-part", "second-part")])
        parts = [[e for e in events if e.get("content_index") == j] for j in (0, 1)]
        a, b = parts
        events = checked_events(
            [*events[:3], a[0], b[0], *b[1:3], *a[1:3], *b[3:], *a[3:], *events[-2:]]
        )
    elif profile == "interleaved-messages":
        events = native_events(
            [message("first-message"), message("second-message", item_id="msg_second_original")]
        )
        a, b = [[e for e in events if e.get("output_index") == j] for j in (0, 1)]
        events = checked_events([*events[:2], a[0], b[0], *a[1:4], *b[1:], *a[4:], events[-1]])
    else:
        first = (
            tool()
            if tools
            else {
                "type": "reasoning",
                "id": "rs_original",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": "Synthetic summary"}],
            }
        )
        events = native_events([first, message("later-message")], tools=tools)
    async with early_http(Upstream(events, gate_after=len(events) - 2)) as (_, up, _, post):
        raw = post(body={**BODY, "tools": tools})
        await raw.wait_for(up.waiting)
        assert_tools_withheld(raw)
        up.release.set()
        await raw.finish()
        assert_native(raw, events[-1]["response"])


@pytest.mark.parametrize(
    "kind,definition", [("function_call", FUNCTION), ("custom_tool_call", CUSTOM)]
)
async def test_raw_native_tool_fragments_wait_for_validated_terminal(early_http, kind, definition):
    events = native_events([tool(kind)], tools=[definition])
    async with early_http(Upstream(events, gate_after=len(events) - 2)) as (_, up, _, post):
        raw = post(body={**BODY, "tools": [definition]})
        await raw.wait_for(up.waiting)
        assert_tools_withheld(raw)
        up.release.set()
        await raw.finish()
        delivered = assert_native(raw, events[-1]["response"])
        field = "arguments" if kind == "function_call" else "input"
        family = (
            "response.function_call_arguments.delta"
            if kind == "function_call"
            else "response.custom_tool_call_input.delta"
        )
        assert "".join(e["delta"] for e in delivered if e["type"] == family) == tool(kind)[field]


async def test_blocked_native_text_send_prevents_next_upstream_read(early_http):
    barrier = SendBarrier()
    events = native_events()
    async with early_http(Upstream(events), limits={"request_timeout_seconds": 0.25}) as (
        app,
        up,
        _,
        post,
    ):
        raw = post(send_hook=barrier)
        await raw.wait_for(barrier.blocked)
        assert up.reads == list(range(first_delta(events) + 1)) and not up.eof.is_set()
        assert app.state.admission.active == 1
        await raw.finish()
        assert up.reads == list(range(first_delta(events) + 1)) and up.closed.is_set()
        assert app.state.admission.active == 0 and b"response.completed" not in raw.body


async def test_native_terminal_send_uses_original_absolute_request_deadline(
    early_http, monkeypatch
):
    class TimeoutObserver:
        def __init__(self):
            self.timers = []

        def timeout_at(self, when):
            timer = asyncio.timeout_at(when)
            self.timers.append(timer)
            return timer

        def __getattr__(self, name):
            return getattr(asyncio, name)

    observer = TimeoutObserver()
    barrier = SendBarrier("response.completed")
    send_cancelled = asyncio.Event()
    cleanup_release = asyncio.Event()
    cleanup_finished = asyncio.Event()
    send_timeout = None

    async def send(message):
        nonlocal send_timeout
        # Capture the real context enclosing this actual ASGI send.
        send_timeout = observer.timers[-1]
        try:
            await barrier(message)
        except asyncio.CancelledError:
            send_cancelled.set()
            await cleanup_release.wait()
            cleanup_finished.set()
            raise

    async with early_http() as (app, up, _, post):
        app_module = importlib.import_module("gateway7.app")
        with monkeypatch.context() as patch:
            patch.setattr(app_module, "asyncio", observer)
            raw = post(send_hook=send, delay_body=True)
            try:
                await raw.wait_for(raw.reading)
                original_deadline = raw.scope["state"]["deadline"]
                raw.body_release.set()
                await raw.wait_for(barrier.blocked)
                assert raw.status == 200 and raw.first_text.is_set()
                assert up.eof.is_set() and up.closed.is_set()
                assert app.state.admission.active == 1 and not raw.task.done()
                assert raw.scope["state"]["deadline"] == original_deadline
                assert isinstance(send_timeout, asyncio.Timeout)
                assert send_timeout.when() == original_deadline
                assert not send_timeout.expired()

                send_timeout.reschedule(asyncio.get_running_loop().time())
                await raw.wait_for(send_cancelled)
                assert send_timeout.expired()
                assert not cleanup_finished.is_set() and not raw.task.done()
                assert app.state.admission.active == 1
            finally:
                cleanup_release.set()
            await raw.finish()
            assert cleanup_finished.is_set() and send_timeout.expired()
            assert raw.scope["state"]["deadline"] == original_deadline
            assert app.state.admission.active == 0
            assert b"response.completed" not in raw.body and b"[DONE]" not in raw.body


@pytest.mark.parametrize("published", [False, True], ids=["before-text", "after-prefix"])
async def test_native_disconnect_holds_admission_until_actual_provider_cleanup(
    early_http, published
):
    events = native_events()
    up = Upstream(events, gate_after=first_delta(events) if published else 1, hold_close=True)
    async with early_http(up, limits={"max_concurrent_requests": 1}) as (app, _, attempts, post):
        raw = post()
        await raw.wait_for(raw.first_text if published else up.waiting)
        raw.incoming.put_nowait({"type": "http.disconnect"})
        await raw.wait_for(up.closing)
        assert app.state.admission.active == 1 and not raw.task.done() and not up.closed.is_set()
        rejected = post()
        await rejected.finish()
        assert_json_error(rejected, 503, "overloaded")
        assert len(attempts) == 1 and app.state.admission.active == 1
        up.cleanup_release.set()
        await raw.finish()
        assert up.closed.is_set() and app.state.admission.active == 0
        assert b"response.completed" not in raw.body and b"[DONE]" not in raw.body

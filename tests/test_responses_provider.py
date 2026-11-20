"""Native Responses adapter tests use synthetic data and offline HTTP transports."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json

import httpx
import pytest

from gateway7.config import ProviderConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.providers import HTTPProvider, build_provider
from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesRequest
from gateway7.responses_provider import _check_text_delta, _control_snapshot
from gateway7.responses_stream import ResponsesStream

KEY = "gateway7-synthetic-responses-key"
MODEL = "synthetic-native-model"
ALL = ResponsesConsent(allow_opaque=True, allow_hosted=True)
USAGE = {
    "input_tokens": 19,
    "input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 3},
    "output_tokens": 11,
    "output_tokens_details": {"reasoning_tokens": 5},
    "total_tokens": 30,
}
FUNCTION = {
    "type": "function",
    "name": "read",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
}
CUSTOM = {
    "type": "custom",
    "name": "apply_patch",
    "format": {
        "type": "grammar",
        "syntax": "lark",
        "definition": "start: /.+/",
    },
}
NAMESPACES = [
    {"type": "namespace", "name": name, "description": "Synthetic tools", "tools": [FUNCTION]}
    for name in ("alpha", "beta")
]
RAW = "*** Begin Patch\n*** Add File: synthetic.txt\n+Synthetic only\n*** End Patch\n"
OPAQUE = "SYNTHETIC_NOT_REAL_ENCRYPTED_REASONING_v1"


def request(*, consent=ResponsesConsent(), **changes):
    return ResponsesRequest.model_validate(
        {"input": "Synthetic request", **changes},
        context={"consent": consent},
    )


def message(text="Synthetic answer", *, status="completed", suffix="new", refusal=False):
    part = (
        {"type": "refusal", "refusal": text}
        if refusal
        else {
            "type": "output_text",
            "text": text,
            "annotations": [],
        }
    )
    return {
        "type": "message",
        "id": "msg_" + suffix,
        "role": "assistant",
        "phase": "final_answer",
        "status": status,
        "content": [part],
    }


def call(suffix="new", *, namespace=None, custom=False):
    result = {
        "type": "custom_tool_call" if custom else "function_call",
        "id": "item_" + suffix,
        "call_id": "call_" + suffix,
        "name": "apply_patch" if custom else "read",
        "input" if custom else "arguments": RAW if custom else ' {"path": "fixture.txt"} ',
        "status": "completed",
    }
    if namespace is not None:
        result["namespace"] = namespace
    return result


def response(*output, status="completed", usage=USAGE, **changes):
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 1800000000.0,
        "model": MODEL,
        "status": status,
        "output": deepcopy(list(output)),
        "parallel_tool_calls": True,
        "tools": [],
        "tool_choice": "auto",
        "usage": deepcopy(usage),
        "error": None,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        **changes,
    }


def native_events(final):
    """Invent complete synthetic lifecycles, preserving the terminal native snapshot."""
    events = []

    def emit(kind, **fields):
        events.append({"type": kind, "sequence_number": len(events), **deepcopy(fields)})

    initial = {
        **deepcopy(final),
        "status": "in_progress",
        "output": [],
        "usage": None,
        "error": None,
        "incomplete_details": None,
    }
    initial.pop("completed_at", None)
    emit("response.created", response=initial)
    emit("response.in_progress", response=initial)
    for index, item in enumerate(final["output"]):
        kind = item["type"]
        added = {**deepcopy(item), "status": "in_progress"}
        if kind == "message":
            added["content"] = []
        elif kind == "reasoning":
            added["summary"] = []
            added["content"] = [] if "content" in item else None
            added.pop("encrypted_content", None)
        elif kind in ("function_call", "custom_tool_call"):
            added["arguments" if kind == "function_call" else "input"] = ""
        emit("response.output_item.added", output_index=index, item=added)
        refs = {"output_index": index, "item_id": item["id"]}
        if kind in ("message", "reasoning"):
            families = [("content_part", "content", "content_index")]
            if kind == "reasoning":
                families = [("reasoning_summary_part", "summary", "summary_index")]
            for family, field, subfield in families:
                for sub, part in enumerate(item.get(field) or []):
                    ref = {**refs, subfield: sub}
                    refusal = part["type"] == "refusal"
                    text_field = "refusal" if refusal else "text"
                    text_family = (
                        "reasoning_summary_text"
                        if kind == "reasoning"
                        else ("refusal" if refusal else "output_text")
                    )
                    logprobs = {"logprobs": []} if text_family == "output_text" else {}
                    emit("response." + family + ".added", **ref, part={**part, text_field: ""})
                    text = part[text_field]
                    for delta in (text[: len(text) // 2], text[len(text) // 2 :]):
                        emit("response." + text_family + ".delta", **ref, delta=delta, **logprobs)
                    emit(
                        "response." + text_family + ".done", **ref, **{text_field: text}, **logprobs
                    )
                    emit("response." + family + ".done", **ref, part=part)
            if kind == "reasoning":
                for sub, part in enumerate(item.get("content") or []):
                    ref = {**refs, "content_index": sub}
                    text = part["text"]
                    for delta in (text[: len(text) // 2], text[len(text) // 2 :]):
                        emit("response.reasoning_text.delta", **ref, delta=delta)
                    emit("response.reasoning_text.done", **ref, text=text)
        elif kind in ("function_call", "custom_tool_call"):
            field = "arguments" if kind == "function_call" else "input"
            family = (
                "function_call_arguments" if kind == "function_call" else "custom_tool_call_input"
            )
            for delta in (
                item[field][: len(item[field]) // 2],
                item[field][len(item[field]) // 2 :],
            ):
                emit("response." + family + ".delta", **refs, delta=delta)
            emit("response." + family + ".done", **refs, **{field: item[field]})
        emit("response.output_item.done", output_index=index, item=item)
    emit("response." + final["status"], response=final)
    return events


@pytest.mark.parametrize("namespace", [False, True])
def test_nullable_response_tool_echoes_keep_request_control_comparison_strict(namespace):
    leaf = deepcopy(FUNCTION)

    def wrap(tool):
        return (
            [{"type": "namespace", "name": "alpha", "description": "Synthetic", "tools": [tool]}]
            if namespace
            else [tool]
        )

    core = request(tools=wrap(leaf))
    controls = {
        name: _control_snapshot(getattr(core, name))
        for name in ("parallel_tool_calls", "tool_choice", "tools")
    }
    source = typed_record(core)
    echoes = wrap({**deepcopy(leaf), "allowed_callers": None, "async": None, "output_schema": None})
    head = ResponsesStreamHead.model_validate({**source.head.wire_dict(), "tools": tuple(echoes)})
    record = source.model_copy(update={"head": head})
    before = deepcopy(head.wire_dict())
    _check_text_delta(record, controls, set())
    assert head.wire_dict() == before and before["tools"] == echoes
    for mutation in ("name", "parameters", "strict", "namespace"):
        altered = deepcopy(echoes)
        tool = altered[0]["tools"][0] if namespace else altered[0]
        if mutation == "namespace":
            if not namespace:
                continue
            altered[0]["name"] = "other"
        else:
            tool[mutation] = {"name": "other", "parameters": {"const": False}, "strict": False}[
                mutation
            ]
        bad_head = ResponsesStreamHead.model_validate({**head.wire_dict(), "tools": tuple(altered)})
        with pytest.raises(ProviderError):
            _check_text_delta(record.model_copy(update={"head": bad_head}), controls, set())
    assert head.wire_dict() == before


def sse(events):
    return b"".join(
        (
            "event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=True) + "\n\n"
        ).encode()
        for event in events
    )


class Parts(httpx.AsyncByteStream):
    def __init__(self, *parts, close_failure=None):
        self.parts = parts
        self.close_failure = close_failure
        self.reads = 0
        self.close_attempts = 0
        self.eof = False

    async def __aiter__(self):
        for part in self.parts:
            self.reads += 1
            yield part
        self.eof = True

    async def aclose(self):
        self.close_attempts += 1
        if self.close_failure is not None:
            raise self.close_failure


@asynccontextmanager
async def mocked(handler, *, kind="openai"):
    provider = build_provider(
        ProviderConfig(kind=kind, model=MODEL),
        KEY,
        transport=httpx.MockTransport(handler),
    )
    try:
        yield provider
    finally:
        await provider.aclose()


def upstream(final, *, stream=False, size=7):
    if not stream:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(final, ensure_ascii=True).encode(),
        )
    body = sse(native_events(final))
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
        stream=Parts(*(body[i : i + size] for i in range(0, len(body), size))),
    )


async def complete(provider, core, mode, *, consent=ResponsesConsent(), on_text=None):
    if mode == "typed":
        assert on_text is not None
        return await provider.complete_responses_early(core, consent=consent, on_text_delta=on_text)
    if mode == "early":
        assert on_text is not None
        return await provider.complete_responses_early(core, consent=consent, on_text=on_text)
    return await provider.complete_responses(core, stream=mode == "sse", consent=consent)


@pytest.mark.parametrize("mode", ["json", "sse", "early"])
@pytest.mark.parametrize(
    "profile",
    [
        "completed_text",
        "parallel_namespace",
        "custom_raw",
        "reasoning_encrypted_summary",
        "incomplete_length",
        "empty_text",
        "incomplete_empty",
        "unknown_usage",
    ],
)
async def test_native_golden_profiles_preserve_items_controls_and_actual_usage(mode, profile):
    core = request()
    consent = ResponsesConsent()
    if profile == "parallel_namespace":
        core = request(tools=NAMESPACES, parallel_tool_calls=True)
        final = response(
            call("a", namespace="alpha"), call("b", namespace="beta"), tools=NAMESPACES
        )
    elif profile == "custom_raw":
        core = request(tools=[CUSTOM], tool_choice={"type": "custom", "name": "apply_patch"})
        final = response(
            call(custom=True), tools=[CUSTOM], tool_choice=core.wire_dict()["tool_choice"]
        )
    elif profile == "reasoning_encrypted_summary":
        consent = ResponsesConsent(allow_opaque=True)
        final = response(
            {
                "type": "reasoning",
                "id": "rs_new",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": "Synthetic summary"}],
                "encrypted_content": OPAQUE,
            },
            message("Synthetic final"),
        )
    elif profile.startswith("incomplete"):
        text = "Synthetic partial" if profile == "incomplete_length" else ""
        final = response(message(text, status="incomplete"), status="incomplete")
    elif profile == "unknown_usage":
        final = response(message("Synthetic usage unavailable"), usage=None)
    else:
        final = response(
            message("" if profile == "empty_text" else 'Synthetic\n"quoted" — 🌍\ud800')
        )
    attempts = []
    delivered = []

    async def on_text(text):
        delivered.append(text)

    def handle(wire):
        attempts.append(wire)
        assert str(wire.url) == "https://api.openai.com/v1/responses"
        assert wire.headers["authorization"] == "Bearer " + KEY
        assert KEY not in wire.content.decode() and KEY not in str(wire.url)
        assert json.loads(wire.content) == {
            **core.wire_dict(),
            "model": MODEL,
            "stream": mode != "json",
        }
        return upstream(final, stream=mode != "json")

    async with mocked(handle) as provider:
        answer = await complete(provider, core, mode, consent=consent, on_text=on_text)
        assert not provider._client.is_closed
    assert answer.wire_dict() == final
    assert answer.output_text == "".join(
        part["text"]
        for item in final["output"]
        if item["type"] == "message"
        for part in item["content"]
        if part["type"] == "output_text"
    )
    assert ("".join(delivered) if mode == "early" else "") == (
        answer.output_text if mode == "early" else ""
    )
    assert len(attempts) == 1 and provider._client.is_closed


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "profile",
    [
        "text",
        "parallel_namespace",
        "parallel_results",
        "custom_raw",
        "reasoning_history",
        "structured_result_image",
        "structured_custom_result_image",
        "hosted_explicit",
    ],
)
async def test_native_request_profiles_preserve_order_history_raw_commands_and_controls(
    stream, profile
):
    controls = {
        "instructions": "Synthetic developer instruction",
        "max_output_tokens": 4096,
        "reasoning": {"effort": "xhigh", "summary": "auto", "context": "all_turns"},
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "result",
                "strict": True,
                "schema": FUNCTION["parameters"],
            },
        },
        "client_metadata": {"x-codex-turn-metadata": "synthetic" * 100},
        "prompt_cache_key": "synthetic-cache",
        "service_tier": "priority",
        "stream_options": {
            "reasoning_summary_delivery": "sequential_cutoff",
            "include_obfuscation": False,
        },
        "parallel_tool_calls": True,
        "store": False,
    }
    if profile == "parallel_namespace":
        controls["tools"] = NAMESPACES
    elif profile == "parallel_results":
        controls.update(
            tools=NAMESPACES,
            input=[
                call("a", namespace="alpha"),
                call("b", namespace="beta"),
                {"type": "function_call_output", "call_id": "call_b", "output": "beta result"},
                {"type": "function_call_output", "call_id": "call_a", "output": "alpha result"},
                {"role": "user", "content": "Continue"},
            ],
        )
    elif profile == "custom_raw":
        controls.update(
            tools=[CUSTOM],
            input=[
                call("old", custom=True),
                {
                    "type": "custom_tool_call_output",
                    "call_id": "call_old",
                    "output": "Synthetic result",
                },
            ],
        )
    elif profile == "reasoning_history":
        controls.update(
            include=["reasoning.encrypted_content"],
            input=[
                {
                    "type": "reasoning",
                    "id": "rs_old",
                    "summary": [],
                    "encrypted_content": OPAQUE,
                },
                message("Synthetic prior", suffix="old"),
                {"role": "user", "content": "Continue"},
            ],
        )
    elif profile.startswith("structured"):
        custom = profile == "structured_custom_result_image"
        controls.update(
            tools=[CUSTOM if custom else FUNCTION],
            input=[
                call("old", custom=custom),
                {
                    "type": "custom_tool_call_output" if custom else "function_call_output",
                    "call_id": "call_old",
                    "output": [
                        {"type": "input_text", "text": "Synthetic adjacent text"},
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,aGVsbG8=",
                            "detail": "original",
                        },
                    ],
                },
            ],
        )
    elif profile == "hosted_explicit":
        controls["tools"] = [{"type": "web_search", "external_web_access": False}]
    core = request(consent=ALL, **controls)
    before = core.wire_dict()
    attempts = []

    def handle(wire):
        attempts.append(wire)
        assert json.loads(wire.content) == {**before, "model": "routed-model", "stream": stream}
        return upstream(response(message()), stream=stream)

    async with mocked(handle) as provider:
        client = provider._client
        answer = await provider.complete_responses(
            core, model="routed-model", stream=stream, consent=ALL
        )
        assert provider._client is client and not client.is_closed
    assert core.wire_dict() == before and len(attempts) == 1
    assert answer.model == MODEL


@pytest.mark.parametrize("mode", ["json", "sse", "early"])
@pytest.mark.parametrize(
    "changes",
    [
        {"tools": [{"type": "web_search"}]},
        {"include": ["reasoning.encrypted_content"]},
        {
            "input": [
                {"type": "reasoning", "id": "rs_old", "summary": [], "encrypted_content": OPAQUE}
            ]
        },
    ],
)
async def test_default_consent_rejects_hosted_or_opaque_request_before_transport(mode, changes):
    attempts = []
    core = request(consent=ALL, **changes)

    async def on_text(_):
        raise AssertionError("Rejected request cannot deliver text")

    async with mocked(lambda wire: attempts.append(wire)) as provider:
        with pytest.raises(ProviderError) as caught:
            await complete(provider, core, mode, on_text=on_text)
    assert caught.value.reason is ProviderErrorReason.REJECTED and not attempts


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "injected"},
        {"stream": True},
        {"allow_opaque": True},
        {"store": True},
        {"max_output_tokens": 4097},
        {"tool_choice": {"type": "function", "name": "undeclared"}},
    ],
)
async def test_revalidation_rejects_copied_authority_and_invalid_native_controls(changes):
    attempts = []
    core = request(tools=[FUNCTION]).model_copy(update=changes)
    async with mocked(lambda wire: attempts.append(wire)) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(core)
    assert caught.value.reason is ProviderErrorReason.REJECTED and not attempts


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize(
    "case",
    [
        "none",
        "required",
        "named",
        "unadvertised",
        "namespace",
        "reused-item",
        "reused-call",
        "arguments",
        "incomplete-call",
        "parallel",
    ],
)
async def test_native_final_validation_uses_request_authority_not_echoed_tools(mode, case):
    core = request(tools=[FUNCTION])
    item = call()
    output = [item]
    if case == "none":
        core = request(tools=[FUNCTION], tool_choice="none")
    elif case == "required":
        core = request(tools=[FUNCTION], tool_choice="required")
        output = [message()]
    elif case == "named":
        other = {**FUNCTION, "name": "write"}
        core = request(tools=[FUNCTION, other], tool_choice={"type": "function", "name": "read"})
        item["name"] = "write"
    elif case == "unadvertised":
        item["name"] = "undeclared"
    elif case == "namespace":
        core = request(tools=NAMESPACES)
    elif case.startswith("reused"):
        core = request(
            tools=[FUNCTION],
            input=[
                call("old"),
                {
                    "type": "function_call_output",
                    "call_id": "call_old",
                    "output": "Synthetic result",
                },
            ],
        )
        item["id" if case == "reused-item" else "call_id"] = (
            "item_old" if case == "reused-item" else "call_old"
        )
    elif case == "arguments":
        item["arguments"] = '{"path":'
    elif case == "incomplete-call":
        item["status"] = "incomplete"
    elif case == "parallel":
        core = request(tools=[FUNCTION], parallel_tool_calls=False)
        output.append(call("second"))
    final = response(*output, tools=[FUNCTION, {**FUNCTION, "name": "undeclared"}])
    async with mocked(lambda _: upstream(final, stream=mode == "sse")) as provider:
        with pytest.raises(ProviderError) as caught:
            await complete(provider, core, mode)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


@pytest.mark.parametrize("mode", ["json", "sse", "early", "typed"])
async def test_opaque_hosted_and_refusal_output_never_becomes_a_text_callback(mode):
    core = request(consent=ALL, tools=[CUSTOM, {"type": "web_search"}])
    final = response(
        {
            "type": "reasoning",
            "id": "rs_new",
            "summary": [{"type": "summary_text", "text": "private reasoning"}],
            "content": [{"type": "reasoning_text", "text": "private raw reasoning"}],
            "encrypted_content": OPAQUE,
            "status": "completed",
        },
        call(custom=True),
        message("private refusal", refusal=True),
        {
            "type": "web_search_call",
            "id": "web_new",
            "status": "completed",
            "action": {
                "type": "search",
                "queries": ["synthetic"],
                "sources": [{"type": "url", "url": "https://example.invalid"}],
            },
        },
        tools=core.wire_dict()["tools"],
    )
    delivered = []

    async def on_text(text):
        delivered.append(text)

    async with mocked(lambda _: upstream(final, stream=mode != "json")) as provider:
        answer = await complete(provider, core, mode, consent=ALL, on_text=on_text)
    assert answer.wire_dict() == final and not delivered


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize("opaque", [False, True])
async def test_upstream_output_cannot_grant_opaque_or_hosted_consent(mode, opaque):
    item = (
        {"type": "reasoning", "id": "rs_new", "summary": [], "encrypted_content": OPAQUE}
        if opaque
        else {
            "type": "web_search_call",
            "id": "web_new",
            "status": "completed",
            "action": {"type": "search"},
        }
    )
    final = response(item)
    async with mocked(lambda _: upstream(final, stream=mode == "sse")) as provider:
        with pytest.raises(ProviderError) as caught:
            await complete(provider, request(), mode)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "status,reason",
    [
        (301, "rejected"),
        (307, "rejected"),
        (400, "rejected"),
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (500, "unavailable"),
        (503, "unavailable"),
    ],
)
async def test_native_http_failures_are_sanitized_and_never_redirected_or_retried(
    stream, status, reason
):
    attempts = []

    def handle(wire):
        attempts.append(wire)
        return httpx.Response(
            status, content=KEY.encode(), headers={"location": "https://untrusted.invalid"}
        )

    async with mocked(handle) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), stream=stream)
    assert caught.value.reason == reason and len(attempts) == 1
    assert str(caught.value) == "Provider request failed"
    assert KEY not in repr(caught.value) and caught.value.__suppress_context__


@pytest.mark.parametrize("kind", ["fake", "claude", "gemini"])
async def test_native_other_provider_kinds_are_rejected_without_transport(kind):
    attempts = []
    async with mocked(lambda wire: attempts.append(wire), kind=kind) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request())
    assert caught.value.reason is ProviderErrorReason.REJECTED and not attempts


@pytest.mark.parametrize("model", ["", "invalid model", "bad\nmodel", "x" * 1025, True, 1])
async def test_native_bound_model_is_validated_before_the_single_request(model):
    attempts = []
    async with mocked(lambda wire: attempts.append(wire)) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), model=model)
    assert caught.value.reason is ProviderErrorReason.REJECTED and not attempts


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b"\xff",
        b'{"id":1,"id":2}',
        b'{"created_at":NaN}',
        b'{"created_at":1e9999}',
        b"x" * 1_048_577,
    ],
    ids=["syntax", "array", "encoding", "duplicate", "nonfinite", "overflow", "size"],
)
async def test_native_json_parsing_is_strict_bounded_and_sanitized(body):
    attempts = []

    def handle(wire):
        attempts.append(wire)
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    async with mocked(handle) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request())
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE and len(attempts) == 1
    assert str(caught.value) == "Provider request failed"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": 19},
        {"output_tokens": 11},
        {"input_tokens": 0, "output_tokens": 0},
        USAGE,
    ],
)
async def test_native_rejected_json_keeps_only_actual_partial_usage(usage):
    final = response(message(), usage=usage, headers={"synthetic": "private upstream value"})
    async with mocked(lambda _: upstream(final)) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request())
    actual = {
        name: value
        for name, value in (usage or {}).items()
        if name in ("input_tokens", "output_tokens")
    }
    assert caught.value.usage == (actual or None)
    assert (
        None if caught.value.responses_usage is None else caught.value.responses_usage.wire_dict()
    ) == (usage or None)
    assert "private upstream value" not in str(caught.value) + repr(caught.value)


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize(
    "code,reason",
    [
        ("server_error", "unavailable"),
        ("rate_limit_exceeded", "rate_limit"),
        ("invalid_prompt", "rejected"),
        ("private-code", "invalid_response"),
    ],
)
async def test_native_failed_terminal_cannot_be_returned_as_success(mode, code, reason):
    final = response(status="failed", error={"code": code, "message": "private upstream failure"})
    async with mocked(lambda _: upstream(final, stream=mode == "sse")) as provider:
        with pytest.raises(ProviderError) as caught:
            await complete(provider, request(), mode)
    assert caught.value.reason == reason
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
    assert "private upstream failure" not in str(caught.value) + repr(caught.value)


async def test_native_early_callback_backpressure_precedes_next_read_and_final_validation_is_detached():
    core = request(tools=[FUNCTION])
    final = response(message("prefixsuffix"), call(), tools=[FUNCTION])
    events = native_events(final)
    parts = Parts(sse(events[:5]), sse(events[5:]))
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered = []
    attempts = []

    async def on_text(text):
        delivered.append(text)
        if not entered.is_set():
            core.tools.clear()
            entered.set()
            await release.wait()

    def handle(wire):
        attempts.append(wire)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)

    async with mocked(handle) as provider:
        task = asyncio.create_task(provider.complete_responses_early(core, on_text=on_text))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert delivered == ["prefix"] and parts.reads == 1 and not parts.eof
            assert not task.done()
            release.set()
            answer = await asyncio.wait_for(task, 1)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    assert delivered == ["prefix", "suffix"] and len(attempts) == 1 and parts.close_attempts == 1
    assert answer.wire_dict() == final


@pytest.mark.parametrize(
    "failure", [RuntimeError, ProviderError, httpx.ReadError, httpx.ReadTimeout]
)
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("sink_name", ["on_text", "on_text_delta"])
@pytest.mark.parametrize(
    "reported",
    [USAGE, {"input_tokens": 19}, {"output_tokens_details": {"reasoning_tokens": 5}}],
    ids=["full", "partial", "details-only"],
)
async def test_native_callback_primary_survives_fallible_close_and_retains_actual_usage(
    failure, cleanup_fails, sink_name, reported
):
    events = native_events(response(message()))
    events[0]["response"]["usage"] = deepcopy(reported)
    parts = Parts(
        sse(events[:5]),
        sse(events[5:]),
        close_failure=httpx.ReadError("private cleanup") if cleanup_fails else None,
    )
    original = failure("synthetic callback failure")

    async def on_text(_):
        raise original

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        with pytest.raises(failure) as caught:
            await provider.complete_responses_early(request(), **{sink_name: on_text})
        assert not provider._client.is_closed
    assert caught.value is original and parts.reads == 1 and parts.close_attempts == 1
    assert caught.value.responses_usage.wire_dict() == reported
    assert provider._client.is_closed


@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("waiting_at", ["callback", "transport"])
@pytest.mark.parametrize("sink_name", ["on_text", "on_text_delta"])
@pytest.mark.parametrize(
    "reported",
    [USAGE, {"input_tokens": 19}, {"output_tokens_details": {"reasoning_tokens": 5}}],
    ids=["full", "partial", "details-only"],
)
async def test_native_real_cancellation_survives_fallible_close(
    cleanup_fails, waiting_at, sink_name, reported
):
    entered = asyncio.Event()
    events = native_events(response(message()))

    class ActiveParts(Parts):
        async def __aiter__(self):
            self.reads += 1
            yield self.parts[0]
            if waiting_at == "transport":
                entered.set()
                await asyncio.Event().wait()

    events[0]["response"]["usage"] = deepcopy(reported)
    parts = ActiveParts(
        sse(events[:5]),
        close_failure=httpx.ReadError("private cleanup") if cleanup_fails else None,
    )

    async def on_text(_):
        if waiting_at == "callback":
            entered.set()
            await asyncio.Event().wait()

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        task = asyncio.create_task(
            provider.complete_responses_early(request(), **{sink_name: on_text})
        )
        try:
            await asyncio.wait_for(entered.wait(), 1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
        assert task.cancelled() and not provider._client.is_closed
    assert parts.close_attempts == 1 and parts.reads == 1 and provider._client.is_closed
    assert caught.value.responses_usage.wire_dict() == reported


@pytest.mark.parametrize("primary", [None, "authentication", "invalid_response"])
async def test_native_provider_primary_and_standalone_cleanup_errors_are_safe(primary):
    events = native_events(response(message()))
    events[0]["response"]["usage"] = deepcopy(USAGE)
    body = sse(events) if primary != "invalid_response" else sse(events[:1]) + b"data: \xff\n\n"
    parts = Parts(body, close_failure=httpx.ReadError("private cleanup"))
    async with mocked(
        lambda _: httpx.Response(
            401 if primary == "authentication" else 200,
            headers={"content-type": "text/event-stream"},
            stream=parts,
        )
    ) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), stream=True)
    assert caught.value.reason == (primary or "transport")
    assert caught.value.usage == (
        None if primary == "authentication" else {"input_tokens": 19, "output_tokens": 11}
    )
    assert "private cleanup" not in str(caught.value) + repr(caught.value)
    assert parts.close_attempts == 1 and provider._client.is_closed


@pytest.mark.parametrize("stream", [0, 1, None, "true"])
async def test_native_stream_authority_is_a_strict_external_boolean(stream):
    attempts = []
    async with mocked(lambda wire: attempts.append(wire)) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), stream=stream)
    assert caught.value.reason is ProviderErrorReason.REJECTED and not attempts


@pytest.mark.parametrize("stream", [False, True])
async def test_native_media_type_must_match_the_pinned_stream_mode(stream):
    wrong_type = "application/json" if stream else "text/event-stream"
    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": wrong_type}, content=b"{}")
    ) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), stream=stream)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True},
        {"output_tokens": -1},
        {"input_tokens": 2**63},
        {"unknown_count": 1},
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 9},
    ],
)
async def test_native_invalid_usage_cannot_be_exposed_as_valid_accounting(usage):
    async with mocked(lambda _: upstream(response(message(), usage=usage))) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request())
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage is None and caught.value.responses_usage is None


@pytest.mark.parametrize("mode", ["json", "sse", "early"])
async def test_native_incomplete_required_call_keeps_status_and_partial_usage(mode):
    final = response(status="incomplete", usage={"input_tokens": 19})
    core = request(tools=[FUNCTION], tool_choice="required")
    delivered = []

    async def on_text(text):
        delivered.append(text)

    async with mocked(lambda _: upstream(final, stream=mode != "json")) as provider:
        answer = await complete(provider, core, mode, on_text=on_text)
    assert answer.status == "incomplete" and not answer.output and not delivered
    assert answer.usage.wire_dict() == {"input_tokens": 19}
    assert answer.accounting_usage() == {"input_tokens": 19}


@pytest.mark.parametrize(
    "failure", ["missing-terminal", "late-invalid", "utf8", "event-limit", "body-limit"]
)
async def test_native_early_late_failures_never_publish_success_and_keep_actual_usage(failure):
    events = native_events(response(message("prefixsuffix")))
    events[0]["response"]["usage"] = deepcopy(USAGE)
    if failure == "missing-terminal":
        tail = sse(events[5:-1])
    elif failure == "late-invalid":
        tail = sse([{**events[5], "item_id": "unknown_item"}, *events[6:]])
    elif failure == "utf8":
        tail = b"data: \xff\n\n"
    elif failure == "event-limit":
        tail = sse([{**events[5], "delta": "x" * 65_536}])
    else:
        tail = b": bounded-heartbeat\n\n" * 60_000
    parts = Parts(sse(events[:5]), tail)
    delivered = []

    async def on_text(text):
        delivered.append(text)

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses_early(request(), on_text=on_text)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.responses_usage.wire_dict() == USAGE
    assert delivered == (["prefix", "suffix"] if failure == "missing-terminal" else ["prefix"])
    assert parts.close_attempts == 1


@pytest.mark.parametrize(
    "failure,reason",
    [
        (httpx.ReadTimeout, "timeout"),
        (httpx.ReadError, "transport"),
        (httpx.DecodingError, "invalid_response"),
        (RuntimeError, "unknown"),
    ],
)
async def test_native_transport_failures_are_sanitized_without_a_second_attempt(failure, reason):
    attempts = []

    def handle(wire):
        attempts.append(wire)
        raise failure("private transport " + KEY)

    async with mocked(handle) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses(request(), stream=True)
    assert caught.value.reason == reason and len(attempts) == 1
    assert str(caught.value) == "Provider request failed" and KEY not in repr(caught.value)


@pytest.mark.parametrize("mode", ["json", "sse", "early"])
async def test_native_failed_hosted_search_can_finish_with_a_completed_fallback(mode):
    core = request(consent=ALL, tools=[{"type": "web_search"}])
    final = response(
        {
            "type": "web_search_call",
            "id": "web_failed",
            "status": "failed",
            "action": {"type": "search"},
        },
        message("Synthetic fallback"),
        tools=core.wire_dict()["tools"],
    )
    delivered = []

    async def on_text(text):
        delivered.append(text)

    async with mocked(lambda _: upstream(final, stream=mode != "json")) as provider:
        answer = await complete(provider, core, mode, consent=ALL, on_text=on_text)
    assert answer.wire_dict() == final and answer.status == "completed"
    assert ("".join(delivered) if mode == "early" else answer.output_text) == "Synthetic fallback"


@pytest.mark.parametrize("mode", ["sse", "early"])
async def test_native_parallel_arguments_interleave_without_reordering_final_items(mode):
    core = request(tools=NAMESPACES, parallel_tool_calls=True)
    final = response(call("a", namespace="alpha"), call("b", namespace="beta"))
    events = native_events(final)
    events = [events[index] for index in (0, 1, 2, 7, 3, 8, 4, 9, 5, 10, 6, 11, 12)]
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    parts = Parts(*(sse([event]) for event in events))
    delivered = []

    async def on_text(text):
        delivered.append(text)

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        answer = await complete(provider, core, mode, on_text=on_text)
    assert answer.wire_dict() == final and not delivered and parts.close_attempts == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_native_client_search_history_loads_the_named_namespace_without_flattening(stream):
    loaded = {**deepcopy(NAMESPACES[0]), "tools": [{**FUNCTION, "defer_loading": True}]}
    history = [
        {
            "type": "tool_search_call",
            "id": "search_old",
            "call_id": "call_search_old",
            "execution": "client",
            "status": "completed",
            "arguments": {"query": "read"},
        },
        {
            "type": "tool_search_output",
            "call_id": "call_search_old",
            "execution": "client",
            "status": "completed",
            "tools": [loaded],
        },
    ]
    core = request(
        input=history,
        tools=[{"type": "tool_search", "execution": "client"}],
        tool_choice={"type": "function", "namespace": "alpha", "name": "read"},
    )
    final = response(call(namespace="alpha"))

    def handle(wire):
        assert json.loads(wire.content)["input"] == history
        return upstream(final, stream=stream)

    async with mocked(handle) as provider:
        answer = await provider.complete_responses(core, stream=stream)
    assert answer.wire_dict() == final


@pytest.mark.parametrize("stream", [False, True])
async def test_native_server_search_results_can_advertise_the_following_native_call(stream):
    core = request(consent=ALL, tools=[{"type": "tool_search", "execution": "server"}])
    final = response(
        {
            "type": "tool_search_call",
            "id": "search_new",
            "call_id": "call_search_new",
            "execution": "server",
            "status": "completed",
            "arguments": {"query": "read"},
        },
        {
            "type": "tool_search_output",
            "id": "search_result_new",
            "call_id": "call_search_new",
            "execution": "server",
            "status": "completed",
            "tools": [NAMESPACES[0]],
        },
        {**call(namespace="alpha"), "encrypted_function_args": [OPAQUE]},
    )
    async with mocked(lambda _: upstream(final, stream=stream)) as provider:
        answer = await provider.complete_responses(core, stream=stream, consent=ALL)
    assert answer.wire_dict() == final


@pytest.mark.parametrize("primary", ["runtime", "provider", "cancel"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("sink_name", ["on_text", "on_text_delta"])
async def test_native_repeated_cancellation_waits_for_one_owned_close_and_restores_primary(
    primary, cleanup_fails, sink_name
):
    callback_entered = asyncio.Event()
    close_entered = asyncio.Event()
    close_release = asyncio.Event()
    close_finished = asyncio.Event()
    close_interrupted = False
    close_tasks = set()
    attempts = []
    original = (
        RuntimeError("synthetic callback failure") if primary == "runtime" else ProviderError()
    )
    events = native_events(response(message()))

    class DeferredClose(Parts):
        async def aclose(self):
            nonlocal close_interrupted
            self.close_attempts += 1
            close_tasks.add(asyncio.current_task())
            close_entered.set()
            try:
                await close_release.wait()
            except asyncio.CancelledError:
                close_interrupted = True
                raise
            close_finished.set()
            if cleanup_fails:
                raise httpx.ReadError("private cleanup failure")

    parts = DeferredClose(sse(events[:5]), sse(events[5:]))

    async def on_text(_):
        nonlocal original
        callback_entered.set()
        if primary == "cancel":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError as error:
                original = error
                raise
        raise original

    async def checkpoint():
        reached = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(reached.set_result, None)
        await reached

    def handle(wire):
        attempts.append(wire)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)

    async with mocked(handle) as provider:
        before = asyncio.all_tasks()
        task = asyncio.create_task(
            provider.complete_responses_early(request(), **{sink_name: on_text})
        )
        caught = None
        try:
            await asyncio.wait_for(callback_entered.wait(), 1)
            if primary == "cancel":
                task.cancel("primary cancellation")
            await asyncio.wait_for(close_entered.wait(), 1)
            task.cancel("cancellation during close")
            await checkpoint()
            assert not task.done() and not close_finished.is_set() and not close_interrupted
            task.cancel("repeated cancellation during close")
            await checkpoint()
            assert not task.done() and not close_finished.is_set() and not close_interrupted
        finally:
            close_release.set()
            try:
                await task
            except BaseException as error:
                caught = error
        assert caught is original and task.cancelled() is (primary == "cancel")
        assert close_finished.is_set() and not close_interrupted
        assert len(close_tasks) == 1 and all(
            owner is not task and owner.done() for owner in close_tasks
        )
        assert not (asyncio.all_tasks() - before)
        assert not provider._client.is_closed
    assert parts.close_attempts == 1 and len(attempts) == 1 and provider._client.is_closed


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize(
    "usage",
    [USAGE, {"input_tokens": 19}, {"output_tokens_details": {"reasoning_tokens": 5}}],
    ids=["full", "partial", "details-only"],
)
async def test_native_failed_terminal_retains_the_full_source_usage_not_an_accounting_projection(
    mode, usage
):
    final = response(
        status="failed", usage=usage, error={"code": "server_error", "message": "private failure"}
    )
    async with mocked(lambda _: upstream(final, stream=mode == "sse")) as provider:
        with pytest.raises(ProviderError) as caught:
            await complete(provider, request(), mode)
    assert caught.value.reason is ProviderErrorReason.UNAVAILABLE
    assert caught.value.responses_usage.wire_dict() == usage


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"on_text": None},
        {"on_text_delta": None},
        {"on_text": "not-callable"},
        {"on_text_delta": "not-callable"},
        {"on_text": False},
        {"on_text": lambda _: None, "on_text_delta": lambda _: None},
        {"on_text": lambda _: None, "on_text_delta": False},
    ],
)
async def test_native_early_requires_exactly_one_callable_before_provider_work(options):
    provider = object.__new__(HTTPProvider)
    with pytest.raises(ProviderError) as caught:
        await provider.complete_responses_early(request(), **options)
    assert caught.value.reason is ProviderErrorReason.REJECTED
    assert not vars(provider)


def typed_record(core=None, **head_changes):
    core = request() if core is None else core
    return ResponsesTextDelta(
        head=ResponsesStreamHead.model_validate(
            {
                "id": "resp_fixture",
                "created_at": 1800000000.0,
                "model": MODEL,
                "parallel_tool_calls": core.parallel_tool_calls,
                "tool_choice": core.tool_choice,
                "tools": tuple(core.tools),
                **head_changes,
            }
        ),
        sequence_number=4,
        item_id="msg_new",
        output_index=0,
        content_index=0,
        phase="final_answer",
        delta="Synthetic",
        leading_prefix=True,
    )


def test_native_record_head_validation_keeps_record_state_and_missing_controls_unchanged():
    core = request(tools=[FUNCTION])
    controls = {
        name: _control_snapshot(getattr(core, name))
        for name in ("parallel_tool_calls", "tool_choice", "tools")
    }
    record = typed_record(core)
    before = record.wire_dict()
    assert _check_text_delta(record, controls, set()) is None
    assert record.wire_dict() == before
    absent = record.model_copy(
        update={
            "head": ResponsesStreamHead(
                id="resp_fixture",
                created_at=1800000000.0,
                model=MODEL,
            )
        }
    )
    assert _check_text_delta(absent, controls, set()) is None
    assert set(absent.head.wire_dict()) == {"id", "created_at", "model"}


@pytest.mark.parametrize(
    "field", ["parallel_tool_calls", "tool_choice", "tools", "schema-type", "history-id"]
)
def test_native_record_head_validation_rejects_authority_mismatch_without_normalizing(field):
    core = request(tools=[FUNCTION])
    controls = {
        name: _control_snapshot(getattr(core, name))
        for name in ("parallel_tool_calls", "tool_choice", "tools")
    }
    record = typed_record(core)
    changes = {
        "parallel_tool_calls": False,
        "tool_choice": "none",
        "tools": (),
    }
    if field == "schema-type":
        changed = deepcopy(FUNCTION)
        changed["parameters"]["additionalProperties"] = 0
        head = ResponsesStreamHead.model_validate({**record.head.model_dump(), "tools": (changed,)})
        record = record.model_copy(update={"head": head})
    elif field != "history-id":
        record = record.model_copy(
            update={"head": record.head.model_copy(update={field: changes[field]})}
        )
    with pytest.raises(ProviderError) as caught:
        _check_text_delta(record, controls, {"msg_new"} if field == "history-id" else set())
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize("sink_name", ["on_text", "on_text_delta"])
async def test_native_typed_seam_preserves_real_record_identity_and_awaited_backpressure(
    monkeypatch, sink_name
):
    instances = []
    observed = []
    original_init = ResponsesStream.__init__
    original_drain = ResponsesStream.drain_text_deltas

    def traced_init(self):
        original_init(self)
        instances.append(self)

    def traced_drain(self):
        records = original_drain(self)
        observed.extend(records)
        return records

    monkeypatch.setattr(ResponsesStream, "__init__", traced_init)
    monkeypatch.setattr(ResponsesStream, "drain_text_deltas", traced_drain)
    core = request(tools=[FUNCTION])
    item = {**message("prefixsuffix"), "phase": "commentary"}
    final = response(item, tools=[FUNCTION])
    events = native_events(final)
    parts = Parts(sse(events[:5]), sse(events[5:]))
    entered = asyncio.Event()
    release = asyncio.Event()
    received = []

    async def sink(value):
        received.append(value)
        if len(received) == 1:
            entered.set()
            await release.wait()

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        task = asyncio.create_task(provider.complete_responses_early(core, **{sink_name: sink}))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert parts.reads == 1 and not parts.eof and not task.done()
            assert len(received) == len(observed) == 1
            release.set()
            answer = await asyncio.wait_for(task, 1)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    assert len(instances) == 1 and parts.close_attempts == 1
    assert [record.sequence_number for record in observed] == [4, 5]
    assert all(type(record) is ResponsesTextDelta for record in observed)
    assert all(record.item_id == item["id"] and record.phase == "commentary" for record in observed)
    assert all(
        record.output_index == record.content_index == 0 and record.leading_prefix
        for record in observed
    )
    assert all(
        record.head.id == final["id"] and record.head.created_at == final["created_at"]
        for record in observed
    )
    assert all(
        record.head.model == MODEL and record.head.tools[0].wire_dict() == FUNCTION
        for record in observed
    )
    if sink_name == "on_text_delta":
        assert all(left is right for left, right in zip(received, observed, strict=True))
    else:
        assert received == [record.delta for record in observed]
    assert answer.wire_dict() == final


@pytest.mark.parametrize(
    "case", ["parallel_tool_calls", "tool_choice", "tools", "schema-type", "history-id"]
)
async def test_native_typed_delivery_rejects_post_policy_head_mismatch_before_callback(case):
    core = request(tools=[FUNCTION])
    final = response(message(), tools=deepcopy([FUNCTION]))
    if case == "parallel_tool_calls":
        final[case] = False
    elif case == "tool_choice":
        final[case] = "none"
    elif case == "tools":
        final[case] = []
    elif case == "schema-type":
        final["tools"][0]["parameters"]["additionalProperties"] = 0
    else:
        core = request(
            tools=[FUNCTION],
            input=[message("previous", suffix="old"), {"role": "user", "content": "Continue"}],
        )
        final["output"][0]["id"] = "msg_old"
    events = native_events(final)
    events[0]["response"]["usage"] = deepcopy(USAGE)
    parts = Parts(sse(events[:5]), sse(events[5:]))
    received = []

    async def sink(record):
        received.append(record)

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses_early(core, on_text_delta=sink)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.responses_usage.wire_dict() == USAGE
    assert received == [] and parts.close_attempts == 1


async def test_native_typed_interleaving_stays_in_source_order_and_encoder_holds_it_back():
    from gateway7.responses_api import EarlyResponsesEncoder

    first = message("FIRST", suffix="first")
    second = message("SECOND", suffix="second")
    final = response(first, second)
    source = native_events(final)
    events = [source[index] for index in (0, 1, 2, 3, 9, 10, 11, 12, 13, 14, 15, 4, 5, 6, 7, 8, 16)]
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    parts = Parts(*(sse([event]) for event in events))
    records = []
    encoder = EarlyResponsesEncoder()

    async def sink(record):
        records.append(record)
        assert encoder.stage_text(record) is None

    async with mocked(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)
    ) as provider:
        answer = await provider.complete_responses_early(request(), on_text_delta=sink)
    assert [record.item_id for record in records] == [
        second["id"],
        second["id"],
        first["id"],
        first["id"],
    ]
    assert [record.output_index for record in records] == [1, 1, 0, 0]
    assert [record.sequence_number for record in records] == [6, 7, 11, 12]
    assert not any(record.leading_prefix for record in records)
    assert "".join(record.delta for record in records) == "SECONDFIRST"
    frames = [
        json.loads(frame.split(b"data: ", 1)[1])
        for frame in encoder.complete(answer).split(b"\n\n")
        if frame
    ]
    assert (
        "".join(frame["delta"] for frame in frames if frame["type"] == "response.output_text.delta")
        == "FIRSTSECOND"
    )
    assert answer.wire_dict() == final and parts.close_attempts == 1


@pytest.mark.parametrize("delivery", ["json", "sse", "on_text", "on_text_delta"])
@pytest.mark.parametrize("alias", ["gpt-4.1-mini", "ft:synthetic/account:model/" + "x" * 160, "é" * 512])
async def test_native_outbound_alias_keeps_consistent_dated_provider_identity(delivery, alias):
    reported = "gpt-4.1-mini-2025-04-14"
    final = response(message("Synthetic alias result"), model=reported)
    wire_response = upstream(final, stream=delivery != "json")
    attempts = []
    received = []

    async def sink(value):
        received.append(value)

    def handle(wire):
        attempts.append(wire)
        assert json.loads(wire.content)["model"] == alias
        return wire_response

    async with mocked(handle) as provider:
        if delivery in ("on_text", "on_text_delta"):
            answer = await provider.complete_responses_early(
                request(), model=alias, **{delivery: sink}
            )
        else:
            answer = await provider.complete_responses(
                request(), model=alias, stream=delivery == "sse"
            )
        assert not provider._client.is_closed
    assert answer.wire_dict() == final and answer.model == reported
    assert len(attempts) == 1 and wire_response.is_closed and provider._client.is_closed
    if delivery == "on_text_delta":
        assert all(value.head.model == reported for value in received)
        assert all(value.head.id == final["id"] for value in received)
        assert "".join(value.delta for value in received) == answer.output_text
    elif delivery == "on_text":
        assert "".join(received) == answer.output_text
    else:
        assert received == []


@pytest.mark.parametrize("sink_name", ["on_text", "on_text_delta"])
@pytest.mark.parametrize("changed_at", ["before-head", "terminal"])
async def test_native_reported_model_must_stay_consistent_with_its_source_identity(
    sink_name, changed_at
):
    alias = "gpt-4.1-mini"
    reported = "gpt-4.1-mini-2025-04-14"
    final = response(message("Synthetic alias result"), model=reported)
    events = native_events(final)
    events[0]["response"]["usage"] = deepcopy(USAGE)
    changed = events[1] if changed_at == "before-head" else events[-1]
    changed["response"]["model"] = "gpt-4.1-mini-2025-04-15"
    parts = Parts(sse(events[:5]), sse(events[5:]))
    received = []
    attempts = []

    async def sink(value):
        received.append(value)

    def handle(wire):
        attempts.append(wire)
        assert json.loads(wire.content)["model"] == alias
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=parts)

    async with mocked(handle) as provider:
        with pytest.raises(ProviderError) as caught:
            await provider.complete_responses_early(request(), model=alias, **{sink_name: sink})
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.responses_usage.wire_dict() == USAGE
    assert len(attempts) == 1 and parts.close_attempts == 1 and provider._client.is_closed
    assert len(received) == (0 if changed_at == "before-head" else 1)
    if sink_name == "on_text_delta":
        assert all(value.head.model == reported for value in received)


@pytest.mark.parametrize("model", ["", "invalid model", True, "m" * 1025])
def test_native_record_reported_model_keeps_its_strict_bounded_identifier(model):
    core = request()
    controls = {
        name: _control_snapshot(getattr(core, name))
        for name in ("parallel_tool_calls", "tool_choice", "tools")
    }
    record = typed_record(core)
    forged = record.model_copy(update={"head": record.head.model_copy(update={"model": model})})
    with pytest.raises(ProviderError) as caught:
        _check_text_delta(forged, controls, set())
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize("mode", ["json", "sse", "typed"])
async def test_raw_projection_uniform_canonical_and_typed_identity(mode, caplog, capsys):
    from gateway7.responses_api import response_json, response_sse
    from gateway7.responses_models import ResponsesResponse
    from gateway7.responses_policy import apply_policy

    marker = "SYNTHETIC_DISCARD_CANARY"
    canonical = response(
        message("Synthetic retained text"),
        model="synthetic-provider-alias",
        metadata={"retained": "SYNTHETIC_RETAINED_CANARY"},
        user=None,
        safety_identifier="",
        reasoning={"effort": None, "summary": "none", "context": None},
    )
    raw = {
        **deepcopy(canonical),
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "image": {},
        "tool_usage": {},
        "access_programs": None,
        "moderation": None,
        "synthetic_admin_echo": marker,
    }
    raw["reasoning"]["synthetic_config_echo"] = marker
    received = []
    core = request()
    before = deepcopy(core.wire_dict())

    async def sink(record):
        received.append(record)

    def handle(wire):
        assert json.loads(wire.content)["model"] == MODEL
        return upstream(raw, stream=mode != "json")

    async with mocked(handle) as provider:
        answer = await complete(provider, core, mode, on_text=sink)
    assert answer.wire_dict() == ResponsesResponse.model_validate(canonical).wire_dict()
    assert core.wire_dict() == before and answer.accounting_usage() == {
        "input_tokens": 19,
        "output_tokens": 11,
    }
    assert marker not in repr(response_json(answer)) + repr(response_sse(answer)) + repr(received)
    inspected = []

    def inspect_text(text):
        inspected.append(text)
        return text, 0

    apply_policy(answer, inspect_text)
    assert "SYNTHETIC_RETAINED_CANARY" in inspected and answer.output_text in inspected
    assert marker not in inspected and "synthetic_admin_echo" not in inspected
    if mode == "typed":
        assert received and "".join(record.delta for record in received) == answer.output_text
        assert all(record.head.id == canonical["id"] for record in received)
        assert all(record.head.model == canonical["model"] for record in received)
        assert all(record.head.parallel_tool_calls is True for record in received)
        assert all(record.item_id == canonical["output"][0]["id"] for record in received)
    captured = capsys.readouterr()
    for excluded in (marker, "synthetic_admin_echo", "synthetic_config_echo"):
        assert excluded not in caplog.text + captured.out + captured.err


@pytest.mark.parametrize("mode", ["json", "sse", "typed"])
async def test_raw_projection_semantic_and_retained_failures_keep_usage(mode, caplog):
    cases = [
        {field: value}
        for field in ("headers", "usage_metadata", "end_turn")
        for value in (None, False, {})
    ]
    cases += [{"reasoning": {"context": True}}, {"reasoning": {"context": "unsupported"}}]
    for changes in cases:
        final = response(message(), synthetic_admin_echo="SYNTHETIC_DISCARD_CANARY", **changes)
        received = []

        async def sink(record):
            received.append(record)

        async with mocked(lambda _: upstream(final, stream=mode != "json")) as provider:
            with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
                await complete(provider, request(), mode, on_text=sink)
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert caught.value.responses_usage.wire_dict() == USAGE
        assert received == []
        assert "SYNTHETIC_DISCARD_CANARY" not in repr(caught.value) + caplog.text


@pytest.mark.parametrize("mode", ["json", "sse"])
async def test_raw_projection_checks_entire_source_before_discard(mode):
    from gateway7.responses_stream import MAX_RESPONSE_BYTES

    fragments = [
        '{"duplicate":1,"duplicate":2}',
        "NaN",
        "Infinity",
        "1e9999",
        '{"broken":[}',
        "[" * 65 + "null" + "]" * 65,
        '"' + "x" * MAX_RESPONSE_BYTES + '"',
    ]
    for fragment in fragments:
        final = response(message())
        if mode == "json":
            source = json.dumps(final)[:-1] + ',"synthetic_admin_echo":' + fragment + "}"
            content_type = "application/json"
        else:
            events = native_events(final)
            first = json.dumps(events[0])[:-2] + ',"synthetic_admin_echo":' + fragment + "}}"
            source = "event: response.created\ndata: " + first + "\n\n"
            source += sse(events[1:]).decode()
            content_type = "text/event-stream"
        async with mocked(
            lambda _: httpx.Response(
                200, headers={"content-type": content_type}, content=source.encode()
            )
        ) as provider:
            with pytest.raises(ProviderError) as caught:
                await complete(provider, request(), mode)
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE

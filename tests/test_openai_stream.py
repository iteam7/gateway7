"""Nullable OpenAI tool fragments stay bounded and require valid final calls."""

import json

import httpx
import pytest

from gateway7.config import ProviderConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.models import ChatRequest
from gateway7.openai_stream import MAX_EVENT_BYTES, OpenAIStream
from gateway7.providers import build_provider


USAGE = {"prompt_tokens": 7, "completion_tokens": 3}
ARGUMENTS = '{"path":"данные/🌍.txt"}'
FIRST = {
    "index": 0,
    "id": "call_fixture",
    "type": "function",
    "function": {"name": "read", "arguments": '{"path":'},
}
LAST = {"index": 0, "function": {"arguments": '"данные/🌍.txt"}'}}
CALL = {
    "id": "call_fixture",
    "type": "function",
    "function": {"name": "read", "arguments": ARGUMENTS},
}


def stream_chunk(delta=None, finish_reason=None, **fields):
    return {
        "id": "chatcmpl-synthetic-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "synthetic-model",
        "choices": [
            {"index": 0, "delta": {} if delta is None else delta, "finish_reason": finish_reason}
        ],
        **fields,
    }


def sse_body(*events, done=True):
    return (
        "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events)
        + ("data: [DONE]\n\n" if done else "")
    ).encode()


def tool_body(*tools):
    return sse_body(
        *(stream_chunk({"tool_calls": [tool]}) for tool in tools),
        stream_chunk(finish_reason="tool_calls"),
        {"choices": [], "usage": USAGE},
    )


def assemble(body, fragment_size=1):
    stream = OpenAIStream(max_bytes=len(body))
    for offset in range(0, len(body), fragment_size):
        stream.feed(body[offset : offset + fragment_size])
    return stream.finish()


@pytest.mark.parametrize("fragment_size", [1, 19, 4096])
@pytest.mark.parametrize(
    "omitted,nullable",
    [
        ({"index": 0, "function": {}}, {"index": 0, "id": None, "function": {}}),
        ({"index": 0, "function": {}}, {"index": 0, "type": None, "function": {}}),
        ({"index": 0}, {"index": 0, "function": None}),
        ({"index": 0, "function": {}}, {"index": 0, "function": {"name": None}}),
        ({"index": 0, "function": {}}, {"index": 0, "function": {"arguments": None}}),
        (
            {"index": 0},
            {"index": 0, "id": None, "type": None, "function": None},
        ),
        (
            {"index": 0, "function": {}},
            {
                "index": 0,
                "id": None,
                "type": None,
                "function": {"name": None, "arguments": None},
            },
        ),
    ],
    ids=["id", "type", "function", "name", "arguments", "all-outer", "all-nested"],
)
def test_null_and_omitted_continuation_fields_preserve_the_same_call(
    omitted, nullable, fragment_size
):
    expected = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "", "tool_calls": [CALL]},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": USAGE,
    }
    assert assemble(tool_body(FIRST, omitted, LAST), fragment_size) == expected
    assert assemble(tool_body(FIRST, nullable, LAST), fragment_size) == expected


@pytest.mark.parametrize("fragment_size", [1, 19, 4096])
def test_nullable_argument_continuation_matches_omitted_fields_with_utf8(fragment_size):
    nullable = {
        **LAST,
        "id": None,
        "type": None,
        "function": {**LAST["function"], "name": None},
    }
    omitted = assemble(tool_body(FIRST, LAST), fragment_size)
    assert assemble(tool_body(FIRST, nullable), fragment_size) == omitted
    assert omitted["choices"][0]["message"]["tool_calls"] == [CALL]
    assert omitted["usage"] == USAGE


@pytest.mark.parametrize(
    "initial",
    [
        {"index": 0},
        {"index": 0, "id": None, "type": None, "function": None},
        {
            "index": 0,
            "id": None,
            "type": None,
            "function": {"name": None, "arguments": None},
        },
    ],
    ids=["omitted", "nullable-function", "nullable-function-fields"],
)
def test_initial_null_fields_allow_later_complete_identity_and_arguments(initial):
    result = assemble(tool_body(initial, FIRST, LAST))
    assert result["choices"][0]["message"]["tool_calls"] == [CALL]
    assert result["usage"] == USAGE


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        {},
        {"index": None},
        {"index": True},
        {"index": 0.0},
        {"index": 1},
        {"index": -1},
        {"index": 0, "extra": None},
        {"index": 0, "id": "call_changed"},
        {"index": 0, "id": ""},
        {"index": 0, "id": 12},
        {"index": 0, "type": "custom"},
        {"index": 0, "type": ""},
        {"index": 0, "type": False},
        {"index": 0, "function": []},
        {"index": 0, "function": [{"name": "read"}]},
        {"index": 0, "function": "read"},
        {"index": 0, "function": False},
        {"index": 0, "function": {"extra": None}},
        {"index": 0, "function": {"name": "write"}},
        {"index": 0, "function": {"name": ""}},
        {"index": 0, "function": {"name": 12}},
        {"index": 0, "function": {"arguments": 12}},
        {"index": 0, "function": {"arguments": False}},
        {"index": 0, "function": {"arguments": []}},
        {"index": 0, "function": {"arguments": {}}},
    ],
    ids=[
        "null-tool",
        "list-tool",
        "missing-index",
        "null-index",
        "boolean-index",
        "float-index",
        "second-index",
        "negative-index",
        "extra-tool-key",
        "conflicting-id",
        "empty-id",
        "numeric-id",
        "unsupported-type",
        "empty-type",
        "boolean-type",
        "list-function",
        "function-list-entry",
        "string-function",
        "boolean-function",
        "extra-function-key",
        "conflicting-name",
        "empty-name",
        "numeric-name",
        "numeric-arguments",
        "boolean-arguments",
        "list-arguments",
        "object-arguments",
    ],
)
def test_invalid_fragments_remain_terminal_and_retain_later_usage(invalid):
    null_fields = {
        "index": 0,
        "id": None,
        "type": None,
        "function": {"name": None, "arguments": None},
    }
    body = tool_body(FIRST, null_fields, invalid, LAST)
    with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
        assemble(body)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


@pytest.mark.parametrize(
    "identity",
    [{"id": "changed"}, {"model": "changed"}, {"created": 2}, {"object": "changed"}],
    ids=["id", "model", "created", "object"],
)
def test_nullable_tool_fields_do_not_relax_event_identity(identity):
    body = sse_body(
        stream_chunk({"tool_calls": [FIRST]}),
        stream_chunk({"tool_calls": [{"index": 0, "function": None}]}, **identity),
        stream_chunk({"tool_calls": [LAST]}, finish_reason="tool_calls"),
        {"choices": [], "usage": USAGE},
    )
    with pytest.raises(ProviderError) as caught:
        assemble(body)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


@pytest.mark.parametrize("failure", ["event-limit", "total-limit", "invalid-utf8"])
def test_nullable_tools_do_not_relax_byte_limits_or_utf8(failure):
    prefix = sse_body({"choices": [], "usage": USAGE}, done=False)
    prefix += sse_body(
        stream_chunk({"tool_calls": [{"index": 0, "id": None, "function": None}]}), done=False
    )
    if failure == "event-limit":
        body = prefix + tool_body({"index": 0, "function": {"arguments": "x" * MAX_EVENT_BYTES}})
    elif failure == "total-limit":
        body = prefix + tool_body(FIRST, LAST)
    else:
        body = prefix + b"data: \xff\n\n"
    stream = OpenAIStream(max_bytes=len(body) - (1 if failure == "total-limit" else 0))
    with pytest.raises(ProviderError) as caught:
        stream.feed(body)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


async def provider_completion(body):
    class Fragments(httpx.AsyncByteStream):
        async def __aiter__(self):
            for byte in body:
                yield bytes([byte])

    response = httpx.Response(
        200, headers={"content-type": "text/event-stream"}, stream=Fragments()
    )
    provider = build_provider(
        ProviderConfig(kind="openai", model="synthetic-model"), "synthetic-test-only"
    )
    await provider.aclose()
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response), follow_redirects=False, trust_env=False
    )
    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "read the fixture"}],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "read", "parameters": {"type": "object"}},
                }
            ],
        }
    )
    try:
        return await provider.complete(request, stream=True)
    finally:
        await provider.aclose()
        assert response.is_closed


async def test_initial_null_fields_succeed_only_after_a_valid_final_call_is_assembled():
    initial = {
        "index": 0,
        "id": None,
        "type": None,
        "function": {"name": None, "arguments": None},
    }
    answer = await provider_completion(tool_body(initial, FIRST, LAST))
    assert [call.model_dump() for call in answer.tool_calls] == [CALL]
    assert answer.finish_reason == "tool_calls"
    assert answer.usage == {"input_tokens": 7, "output_tokens": 3}


@pytest.mark.parametrize(
    "call",
    [
        {**CALL, "id": None},
        {**CALL, "function": {**CALL["function"], "name": None}},
        {**CALL, "function": {"name": "read", "arguments": None}},
        {**CALL, "function": {"name": "read", "arguments": '{"path":'}},
    ],
    ids=["missing-id", "missing-name", "missing-arguments", "incomplete-arguments"],
)
async def test_incomplete_final_calls_are_rejected_at_the_provider_boundary(call):
    body = tool_body({"index": 0, **call})
    assembled = assemble(body)
    assert assembled["choices"][0]["message"]["tool_calls"]

    with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
        await provider_completion(body)
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


def test_text_drains_only_after_a_complete_utf8_event_and_only_once():
    stream = OpenAIStream(max_bytes=1_048_576)
    assert stream.drain_text() == ()
    event = sse_body(stream_chunk({"content": "Привет 🌍"}), done=False)
    split = event.index("🌍".encode()) + 1
    stream.feed(event[:split])
    assert stream.drain_text() == ()
    stream.feed(event[split:-1])
    assert stream.drain_text() == ()
    stream.feed(event[-1:])
    assert stream.drain_text() == ("Привет 🌍",)
    assert stream.drain_text() == ()

    stream.feed(sse_body(stream_chunk(finish_reason="stop"), {"choices": [], "usage": USAGE}))
    assert stream.drain_text() == ()
    assert stream.finish()["choices"][0]["message"]["content"] == "Привет 🌍"
    assert stream.drain_text() == ()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_text_drains_keep_nonempty_delta_boundaries_and_full_response(newline):
    stream = OpenAIStream(max_bytes=1_048_576)
    first = sse_body(
        stream_chunk({"role": "assistant", "content": ""}),
        stream_chunk({"content": "one"}),
        stream_chunk({"content": None}),
        stream_chunk({"content": " "}),
        done=False,
    ).replace(b"\n", newline)
    stream.feed(first)
    assert stream.drain_text() == ("one", " ")
    assert stream.drain_text() == ()

    stream.feed(
        sse_body(stream_chunk({"content": "🌍"}, "stop"), {"choices": [], "usage": USAGE}).replace(
            b"\n", newline
        )
    )
    assert stream.drain_text() == ("🌍",)
    result = stream.finish()
    assert result["choices"][0]["message"]["content"] == "one 🌍"
    assert result["usage"] == USAGE
    assert stream.drain_text() == ()


def test_text_drain_never_returns_raw_tool_fragments():
    stream = OpenAIStream(max_bytes=1_048_576)
    stream.feed(sse_body(stream_chunk({"content": "notice", "tool_calls": [FIRST]}), done=False))
    assert stream.drain_text() == ("notice",)
    stream.feed(tool_body({"index": 0, "id": None, "function": None}, LAST))
    assert stream.drain_text() == ()
    message = stream.finish()["choices"][0]["message"]
    assert message["content"] == "notice"
    assert message["tool_calls"] == [CALL]


@pytest.mark.parametrize("drain_prefix", [False, True])
@pytest.mark.parametrize(
    "event",
    [
        stream_chunk({"content": "private", "tool_calls": {"index": 0}}),
        stream_chunk({"content": "private", "tool_calls": [{"index": 1}]}),
        stream_chunk({"content": "private", "tool_calls": [{"index": 0, "function": []}]}),
        stream_chunk({"content": "private", "tool_calls": [FIRST, LAST]}),
        stream_chunk({"content": "private"}, "content_filter"),
        stream_chunk({"content": "private", "reasoning_content": "hidden reasoning"}),
        stream_chunk({"content": "private", "refusal": "hidden refusal"}),
        stream_chunk({"content": "private"}, error={"message": "upstream error"}),
        stream_chunk({"content": "private"}, id="changed"),
    ],
    ids=[
        "tool-object",
        "tool-index",
        "function-list",
        "multiple-tools",
        "finish-reason",
        "reasoning",
        "refusal",
        "upstream-error",
        "identity",
    ],
)
def test_entire_event_must_validate_before_its_text_can_drain(event, drain_prefix):
    stream = OpenAIStream(max_bytes=1_048_576)
    stream.feed(sse_body(stream_chunk({"content": "prefix"}), done=False))
    if drain_prefix:
        assert stream.drain_text() == ("prefix",)
    stream.feed(sse_body(event, done=False))
    assert stream.drain_text() == ()
    assert stream.drain_text() == ()

    stream.feed(
        sse_body(
            stream_chunk({"content": "later hidden text"}, "stop"), {"choices": [], "usage": USAGE}
        )
    )
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}
    assert stream.drain_text() == ()


@pytest.mark.parametrize(
    "malformed",
    [b"data: not-json\n\n", b"data: []\n\n", b'data: {"choices":[]}\n\n'],
    ids=["invalid-json", "non-object", "missing-usage"],
)
def test_malformed_following_event_discards_undrained_text_from_the_same_feed(malformed):
    stream = OpenAIStream(max_bytes=1_048_576)
    stream.feed(
        sse_body(stream_chunk({"content": "undrained prefix"}), done=False)
        + malformed
        + sse_body(
            stream_chunk({"content": "later hidden text"}, "stop"), {"choices": [], "usage": USAGE}
        )
    )
    assert stream.drain_text() == ()
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


@pytest.mark.parametrize("failure", ["invalid-utf8", "event-limit", "total-limit"])
def test_hard_parsing_failure_suppresses_pending_text(failure):
    prefix = sse_body(
        stream_chunk({"content": "undrained prefix"}), {"choices": [], "usage": USAGE}, done=False
    )
    stream = OpenAIStream(max_bytes=len(prefix) if failure == "total-limit" else 1_048_576)
    stream.feed(prefix)
    if failure == "invalid-utf8":
        bad = b"data: \xff\n\n"
    elif failure == "event-limit":
        bad = sse_body(stream_chunk({"content": "x" * MAX_EVENT_BYTES}))
    else:
        bad = b"x"
    with pytest.raises(ProviderError) as caught:
        stream.feed(bad)
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()
    assert stream.drain_text() == ()


@pytest.mark.parametrize(
    "ending",
    [
        sse_body(stream_chunk(finish_reason="stop"), done=False),
        b"data: [DONE]\n\n",
        b'data: {"choices":',
    ],
    ids=["missing-done", "missing-finish", "incomplete-event"],
)
def test_invalid_final_protocol_discards_undrained_text(ending):
    stream = OpenAIStream(max_bytes=1_048_576)
    stream.feed(sse_body(stream_chunk({"content": "undrained prefix"}), done=False) + ending)
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert stream.drain_text() == ()


@pytest.mark.parametrize("already_drained_prefix", [False, True])
def test_premature_done_discards_pending_text_before_finish(already_drained_prefix):
    stream = OpenAIStream(max_bytes=1_048_576)
    if already_drained_prefix:
        stream.feed(sse_body(stream_chunk({"content": "already published"}), done=False))
        assert stream.drain_text() == ("already published",)

    stream.feed(
        sse_body(stream_chunk({"content": "undrained prefix"}), {"choices": [], "usage": USAGE})
    )
    assert stream.drain_text() == ()
    assert stream.drain_text() == ()
    assert stream.usage == {"input_tokens": 7, "output_tokens": 3}

    stream.feed(
        sse_body(
            stream_chunk({"content": "late text"}, "stop"),
            {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 4}},
        )
    )
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 7, "output_tokens": 3}


def test_event_after_done_discards_undrained_text():
    stream = OpenAIStream(max_bytes=1_048_576)
    stream.feed(sse_body(stream_chunk({"content": "undrained prefix"}, "stop")))
    stream.feed(sse_body(stream_chunk({"content": "hidden text"})))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()

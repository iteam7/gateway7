"""Native Responses protocol checks use synthetic, transport-independent events."""

import asyncio
from copy import deepcopy
import json

import pytest

from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_stream import MAX_EVENT_BYTES, MAX_RESPONSE_BYTES, ResponsesStream


USAGE = {
    "input_tokens": 19,
    "input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 3},
    "output_tokens": 11,
    "output_tokens_details": {"reasoning_tokens": 5},
    "total_tokens": 30,
}


def response(output=(), status="in_progress", usage=None):
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 1.0,
        "model": "synthetic-model",
        "status": status,
        "output": list(output),
        "parallel_tool_calls": True,
        "tools": [],
        "tool_choice": "auto",
        "usage": usage,
        "error": None,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
    }


@pytest.mark.parametrize("snapshot", [0, 1, 9])
def test_known_subset_echo_shapes_are_validated_in_every_response_envelope(snapshot):
    echoes = {
        "max_tool_calls": 0,
        "prompt_cache_retention": "24h",
        "safety_identifier": "",
        "top_logprobs": 20,
        "user": None,
    }
    events = events_for(message())
    for event in events:
        if "response" in event:
            event["response"].update(echoes)
    stream, terminal = parse(events, size=4096)
    assert {key: terminal[key] for key in echoes} == echoes
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    for field, invalid in (
        ("max_tool_calls", True),
        ("top_logprobs", 21),
        ("safety_identifier", "x" * 129),
        ("user", []),
        ("prompt_cache_retention", "other"),
    ):
        altered = deepcopy(events)
        altered[snapshot]["response"][field] = invalid
        stream = ResponsesStream()
        stream.feed(wire(altered))
        assert stream.drain_text_deltas() == ()
        with pytest.raises(ProviderError):
            stream.finish()


def test_known_subset_nonempty_snapshot_probabilities_survive_with_event_shape_and_holdback():
    events = probability_events(
        delta_top={"top_logprobs": [{"token": "y", "logprob": -1.0}]},
        done_top={"top_logprobs": [{"token": "y", "logprob": -1.0}]},
        output_top=[{"token": "y", "bytes": [121], "logprob": -1.0}],
    )
    stream, terminal = parse(events, size=4096)
    from gateway7.responses_api import EarlyResponsesEncoder
    from gateway7.responses_models import ResponsesResponse

    encoder = EarlyResponsesEncoder()
    records = stream.drain_text_deltas()
    assert records and all(not record.leading_prefix for record in records)
    assert all(encoder.stage_text(record) is None for record in records)
    checked = ResponsesResponse.model_validate(terminal)
    assert checked.wire_dict() == terminal


def message(text="Привет 🌍", status="completed"):
    return {
        "id": "msg_fixture",
        "type": "message",
        "role": "assistant",
        "status": status,
        "phase": "final_answer",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def call(suffix="one", kind="function_call"):
    field = "arguments" if kind == "function_call" else "input"
    return {
        "id": "item_" + suffix,
        "type": kind,
        "call_id": "call_" + suffix,
        "namespace": "alpha",
        "name": "read" if kind == "function_call" else "patch",
        "status": "completed",
        field: '{"path":"fixture.txt"}' if kind == "function_call" else "*** Patch\n+🌍\n",
    }


def events_for(*output, status="completed", usage=USAGE):
    events = []

    def emit(kind, **fields):
        events.append({"type": kind, "sequence_number": len(events), **deepcopy(fields)})

    emit("response.created", response=response())
    emit("response.in_progress", response=response())
    for index, final in enumerate(output):
        initial = {**final, "status": "in_progress"}
        kind = final["type"]
        field = "arguments" if kind == "function_call" else "input"
        if kind == "message":
            initial["content"] = []
        elif kind == "reasoning":
            initial["summary"] = []
            initial.pop("encrypted_content", None)
        elif kind in ("function_call", "custom_tool_call"):
            initial[field] = ""
        emit("response.output_item.added", output_index=index, item=initial)
        refs = {"output_index": index, "item_id": final["id"]}
        if kind in ("message", "reasoning"):
            summary = kind == "reasoning"
            for sub, part in enumerate(final["summary" if summary else "content"]):
                ref = {**refs, "summary_index" if summary else "content_index": sub}
                family = "reasoning_summary_part" if summary else "content_part"
                refusal = part["type"] == "refusal"
                text_family = (
                    "reasoning_summary_text" if summary else "refusal" if refusal else "output_text"
                )
                value_field = "refusal" if refusal else "text"
                emit("response." + family + ".added", **ref, part={**part, value_field: ""})
                text = part[value_field]
                logprobs = {"logprobs": []} if text_family == "output_text" else {}
                for delta in (text[: len(text) // 2], text[len(text) // 2 :]):
                    emit("response." + text_family + ".delta", **ref, delta=delta, **logprobs)
                emit("response." + text_family + ".done", **ref, **{value_field: text}, **logprobs)
                emit("response." + family + ".done", **ref, part=part)
        elif kind in ("function_call", "custom_tool_call"):
            family = "function_call_arguments" if field == "arguments" else "custom_tool_call_input"
            text = final[field]
            for delta in (text[: len(text) // 2], text[len(text) // 2 :]):
                emit("response." + family + ".delta", **refs, delta=delta)
            emit("response." + family + ".done", **refs, **{field: text})
        emit("response.output_item.done", output_index=index, item=final)
    terminal = response(output, status, deepcopy(usage))
    emit("response." + status, response=terminal)
    return events


def wire(events, newline="\n", named=True):
    return "".join(
        ("event: " + event["type"] + newline if named else "")
        + "data: "
        + json.dumps(event, ensure_ascii=True)
        + newline
        + newline
        for event in events
    ).encode()


def parse(events, size=1):
    body = wire(events)
    stream = ResponsesStream()
    for offset in range(0, len(body), size):
        stream.feed(body[offset : offset + size])
    return stream, stream.finish()


@pytest.mark.parametrize("namespace", [False, True])
def test_nullable_response_tool_echoes_match_typed_heads_and_terminal(namespace):
    leaf = {
        "type": "function",
        "name": "read",
        "parameters": {"type": "object"},
        "strict": True,
        "allowed_callers": None,
        "async": None,
        "output_schema": None,
    }
    tools = (
        [{"type": "namespace", "name": "alpha", "description": "Synthetic", "tools": [leaf]}]
        if namespace
        else [leaf]
    )
    events = events_for(message())
    for event in events:
        if "response" in event:
            event["response"]["tools"] = deepcopy(tools)
    stream, terminal = parse(events, size=4096)
    records = stream.drain_text_deltas()
    assert records and terminal["tools"] == tools
    assert all(record.head.wire_dict()["tools"] == tools for record in records)
    assert stream.native_usage == USAGE


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed_callers", ["direct"]),
        ("async", False),
        ("output_schema", {"type": "object"}),
    ],
)
def test_nullable_response_tool_echoes_reject_nonnull_before_executable_processing(field, value):
    events = events_for(call())
    for event in events:
        if "response" in event:
            event["response"]["tools"] = [
                {"type": "function", "name": "read", "parameters": {}, field: value}
            ]
    stream = ResponsesStream()
    stream.feed(wire(events[:1]))
    assert stream._initial is None
    stream.feed(wire(events[1:]))
    assert stream.drain_text_deltas() == ()
    with pytest.raises(ProviderError):
        stream.finish()
    assert stream.native_usage == USAGE


def test_nullable_response_tool_echo_presence_cannot_change_between_snapshots():
    for field in ("allowed_callers", "async", "output_schema"):
        events = events_for(message())
        for event in events:
            if "response" in event:
                event["response"]["tools"] = [
                    {"type": "function", "name": "read", "parameters": {}, field: None}
                ]
        del events[-1]["response"]["tools"][0][field]
        stream = ResponsesStream()
        stream.feed(wire(events))
        assert stream.drain_text_deltas() == ()
        with pytest.raises(ProviderError):
            stream.finish()


@pytest.mark.parametrize("size", [1, 7, 4096])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_native_text_preserves_the_complete_terminal_response(size, newline):
    events = events_for(message('Привет 🌍\n"quote"\ud800'))
    body = b"\xef\xbb\xbf" + (": heartbeat" + newline + newline).encode() + wire(events, newline)
    stream = ResponsesStream()
    for offset in range(0, len(body), size):
        stream.feed(body[offset : offset + size])
    assert stream.finish() == events[-1]["response"]
    assert "".join(stream.drain_text()) == events[-1]["response"]["output"][0]["content"][0]["text"]
    assert stream.drain_text() == ()
    assert stream.usage["input_tokens"] == 19
    assert stream.usage["output_tokens"] == 11


def test_text_waits_for_full_utf8_and_event_before_draining():
    events = events_for(message("🌍"))
    stream = ResponsesStream()
    stream.feed(wire(events[:4]))
    event = wire([events[5]]).replace(b'"\\ud83c\\udf0d"', '"🌍"'.encode())
    # Use one combined delta and renumber the remaining events.
    event = event.replace(b'"sequence_number": 5', b'"sequence_number": 4')
    split = event.index("🌍".encode()) + 1
    stream.feed(event[:split])
    assert stream.drain_text() == ()
    stream.feed(event[split:-1])
    assert stream.drain_text() == ()
    stream.feed(event[-1:])
    assert stream.drain_text() == ("🌍",)
    assert stream.drain_text() == ()


@pytest.mark.parametrize("status", ["completed", "incomplete"])
@pytest.mark.parametrize("text", ["", "partial"])
def test_empty_and_incomplete_text_are_valid_native_terminals(status, text):
    events = events_for(message(text, status), status=status)
    stream, result = parse(events)
    assert result == events[-1]["response"]
    assert all(stream.drain_text())


def test_parallel_namespace_items_interleave_without_confusing_call_and_item_ids():
    events = events_for(call("one"), call("two"))
    events = [events[i] for i in (0, 1, 2, 7, 3, 8, 4, 9, 5, 10, 6, 11, 12)]
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream, result = parse(events)
    assert result["output"] == [call("one"), call("two")]
    assert stream.drain_text() == ()


def test_custom_refusal_and_opaque_reasoning_are_preserved_but_never_drained():
    reason = {
        "type": "reasoning",
        "id": "rs_fixture",
        "status": "completed",
        "summary": [{"type": "summary_text", "text": "private summary"}],
        "encrypted_content": "SYNTHETIC_OPAQUE",
    }
    refusal = {**message(), "content": [{"type": "refusal", "refusal": "private refusal"}]}
    events = events_for(reason, call("custom", "custom_tool_call"), refusal)
    stream, result = parse(events)
    assert result["output"] == [reason, call("custom", "custom_tool_call"), refusal]
    assert stream.drain_text() == ()


@pytest.mark.parametrize("kind", ["web_search_call", "tool_search_call", "tool_search_output"])
def test_hosted_and_client_search_payloads_survive_item_done(kind):
    item = {"type": kind, "id": "search_fixture", "status": "completed"}
    if kind == "web_search_call":
        item["action"] = {
            "type": "search",
            "queries": ["synthetic"],
            "sources": [{"type": "url", "url": "https://example.invalid"}],
        }
    else:
        item.update(execution="client", call_id="call_search")
        item["arguments" if kind == "tool_search_call" else "tools"] = (
            {"query": "read", "limit": 1}
            if kind == "tool_search_call"
            else [{"type": "function", "name": "read", "parameters": {"type": "object"}}]
        )
    stream, result = parse(events_for(item))
    assert result["output"] == [item]
    assert stream.drain_text() == ()


@pytest.mark.parametrize(
    "usage",
    [None, {}, {"input_tokens": 19}, {"input_tokens": None, "output_tokens": 11}],
)
def test_unknown_or_partial_usage_is_not_fabricated(usage):
    stream, result = parse(events_for(message(), usage=usage))
    assert stream.usage is None
    assert result["usage"] == usage


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": 19, "output_tokens": 11},
        {"input_tokens": 19, "output_tokens": 11, "total_tokens": None},
        {
            "input_tokens": 19,
            "output_tokens": 11,
            "input_tokens_details": {"cached_tokens": None, "cache_write_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": None},
        },
    ],
)
def test_reported_aggregate_usage_survives_absent_or_nullable_details(usage):
    stream, result = parse(events_for(message(), usage=usage))
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    assert result["usage"] == usage


def test_incomplete_max_messages_has_a_strict_native_reason():
    events = events_for(message("partial", "incomplete"), status="incomplete")
    events[-1]["response"]["incomplete_details"] = {"reason": "max_messages"}
    _, result = parse(events)
    assert result["incomplete_details"] == {"reason": "max_messages"}


def mutate(events, path, value=None, remove=False):
    result = deepcopy(events)
    owner = result
    for key in path[:-1]:
        owner = owner[key]
    if remove:
        del owner[path[-1]]
    else:
        owner[path[-1]] = value
    return result


@pytest.mark.parametrize(
    "path,value,remove",
    [
        ((4, "sequence_number"), 3, False),
        ((4, "sequence_number"), True, False),
        ((0, "sequence_number"), -1, False),
        ((4, "output_index"), True, False),
        ((4, "item_id"), "missing", False),
        ((4, "content_index"), -1, False),
        ((4, "private_extension"), None, False),
        ((4, "logprobs"), None, True),
        ((2, "item", "id"), "bad\nid", False),
        ((9, "response", "id"), "changed", False),
        ((9, "response", "model"), "changed", False),
        ((9, "response", "status"), "incomplete", False),
        ((9, "response", "output", 0, "content", 0, "text"), "changed", False),
        ((6, "text"), "changed", False),
        ((7, "part", "text"), "changed", False),
        ((8, "item", "status"), "in_progress", False),
        ((8, "item", "phase"), "commentary", False),
        ((9, "response", "usage", "input_tokens"), True, False),
        ((9, "response", "usage", "input_tokens"), -1, False),
        ((9, "response", "usage", "input_tokens"), 2**63, False),
        ((9, "response", "usage", "total_tokens"), 31, False),
        ((3, "content_index"), 1, False),
        ((9,), None, True),
    ],
)
def test_protocol_mutations_are_terminal_and_suppress_pending_text(path, value, remove):
    events = mutate(events_for(message()), path, value, remove)
    stream = ResponsesStream()
    stream.feed(wire(events))
    if remove and path == (9,):
        with pytest.raises(ProviderError):
            stream.finish()
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "changed"),
        ("call_id", "changed"),
        ("namespace", "beta"),
        ("name", "write"),
        ("arguments", "{}"),
        ("type", "custom_tool_call"),
        ("private_extension", None),
    ],
)
def test_function_item_final_identity_and_arguments_must_match(field, value):
    events = mutate(events_for(call()), (6, "item", field), value)
    stream = ResponsesStream()
    stream.feed(wire(events))
    with pytest.raises(ProviderError):
        stream.finish()
    assert stream.drain_text() == ()


@pytest.mark.parametrize(
    "arguments",
    ['{"x":', "[]", "null", '{"x":1,"x":2}', '{"x":NaN}', '{"x":' * 66 + "{}" + "}" * 66],
)
def test_final_function_arguments_require_a_bounded_json_object(arguments):
    item = {**call(), "arguments": arguments}
    stream = ResponsesStream()
    stream.feed(wire(events_for(item)))
    with pytest.raises(ProviderError):
        stream.finish()


@pytest.mark.parametrize(
    "code,reason",
    [
        ("server_error", "unavailable"),
        ("rate_limit_exceeded", "rate_limit"),
        ("invalid_prompt", "rejected"),
    ],
)
@pytest.mark.parametrize("failed_response", [False, True])
def test_failures_never_become_success_and_keep_independent_usage(code, reason, failed_response):
    events = events_for(message())[:5]
    if failed_response:
        failed = response(status="failed", usage=USAGE)
        failed["error"] = {"code": code, "message": "private upstream message"}
        event = {"type": "response.failed", "sequence_number": len(events), "response": failed}
    else:
        events[0]["response"]["usage"] = USAGE
        event = {
            "type": "error",
            "sequence_number": len(events),
            "code": code,
            "message": "private upstream message",
            "param": None,
        }
    stream = ResponsesStream()
    stream.feed(wire([*events, event]))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
        stream.finish()
    assert caught.value.reason == reason
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
    assert "private" not in str(caught.value) + repr(caught.value)


def test_late_accounting_survives_invalid_event_but_cannot_restore_text():
    events = events_for(message())
    events[4]["item_id"] = "missing"
    stream = ResponsesStream()
    stream.feed(wire(events[:5]))
    assert stream.drain_text() == ()
    stream.feed(wire(events[5:]))
    assert stream.drain_text() == ()
    assert stream.usage["input_tokens"] == 19
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


def test_premature_terminal_and_events_after_terminal_clear_all_pending_text():
    for events in (
        events_for(message())[:5] + events_for(message())[-1:],
        events_for(message()) + events_for(message())[-1:],
    ):
        stream = ResponsesStream()
        stream.feed(wire(events))
        assert stream.drain_text() == ()
        with pytest.raises(ProviderError):
            stream.finish()


@pytest.mark.parametrize(
    "bad",
    [
        b'data: {"type":"error","type":"error","sequence_number":0,"message":"x"}\n\n',
        b'data: {"type":"error","sequence_number":NaN,"message":"x"}\n\n',
        b"data: \xff\n\n",
        b"data: [DONE]\n\n",
        b'event: response.failed\ndata: {"type":"response.created","sequence_number":0}\n\n',
        b"data: []\n\n",
        b'data: {"type":',
    ],
)
def test_malformed_wire_never_yields_a_success_or_text(bad):
    stream = ResponsesStream()
    with pytest.raises(ProviderError):
        stream.feed(bad)
        stream.finish()
    assert stream.drain_text() == ()


@pytest.mark.parametrize("failure", ["event", "total", "utf8", "partial-frame"])
def test_wire_bounds_and_encoding_preserve_already_accounted_usage(failure):
    events = events_for(message())
    events[0]["response"]["usage"] = USAGE
    stream = ResponsesStream()
    stream.feed(wire(events[:4]))
    if failure == "event":
        bad = wire([{**events[4], "delta": "x" * MAX_EVENT_BYTES}])
    elif failure == "total":
        bad = b": heartbeat\n\n" * (MAX_RESPONSE_BYTES // 10)
    elif failure == "utf8":
        bad = b"data: \xff\n\n"
    else:
        bad = wire(events[4:])[:-1]
    with pytest.raises(ProviderError) as caught:
        stream.feed(bad)
        stream.finish()
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.native_usage == USAGE
    assert stream.drain_text() == ()


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-created",
        "duplicate-progress",
        "item-before-created",
        "item-index-gap",
        "duplicate-part",
        "text-before-part",
        "text-after-done",
        "delta-after-item-done",
        "wrong-delta-family",
        "missing-part-done",
        "duplicate-item-id",
        "duplicate-call-id",
        "missing-argument-done",
        "call-id-in-item-reference",
        "unknown-event",
    ],
)
def test_lifecycle_transitions_are_closed_and_ordered(change):
    events = events_for(message())
    if change == "duplicate-created":
        events.insert(1, deepcopy(events[0]))
    elif change == "duplicate-progress":
        events.insert(2, deepcopy(events[1]))
    elif change == "item-before-created":
        events[0], events[2] = events[2], events[0]
    elif change == "item-index-gap":
        events[2]["output_index"] = 1
    elif change == "duplicate-part":
        events.insert(4, deepcopy(events[3]))
    elif change == "text-before-part":
        events[3], events[4] = events[4], events[3]
    elif change == "text-after-done":
        events.insert(7, deepcopy(events[4]))
    elif change == "delta-after-item-done":
        events.insert(9, deepcopy(events[4]))
    elif change == "wrong-delta-family":
        events[4]["type"] = "response.reasoning_text.delta"
        del events[4]["logprobs"]
    elif change == "missing-part-done":
        del events[7]
    elif change in ("duplicate-item-id", "duplicate-call-id"):
        first, second = call("one"), call("two")
        second["id" if change == "duplicate-item-id" else "call_id"] = first[
            "id" if change == "duplicate-item-id" else "call_id"
        ]
        events = events_for(first, second)
    elif change == "missing-argument-done":
        events = events_for(call())
        del events[5]
    elif change == "call-id-in-item-reference":
        events = events_for(call())
        events[3]["item_id"] = "call_one"
    else:
        events[4]["type"] = "response.unknown.delta"
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()


def test_reasoning_text_has_its_own_ordered_content_and_never_drains():
    item = {
        "type": "reasoning",
        "id": "rs_fixture",
        "status": "completed",
        "summary": [],
        "content": [{"type": "reasoning_text", "text": "private reasoning"}],
        "encrypted_content": "SYNTHETIC_OPAQUE",
    }
    initial = {**item, "status": "in_progress", "content": [], "encrypted_content": "partial"}
    refs = {"output_index": 0, "item_id": item["id"], "content_index": 0}
    events = [
        {"type": "response.created", "response": response()},
        {"type": "response.output_item.added", "output_index": 0, "item": initial},
        {"type": "response.reasoning_text.delta", **refs, "delta": "private reasoning"},
        {"type": "response.reasoning_text.done", **refs, "text": "private reasoning"},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": response([item], "completed", USAGE)},
    ]
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream, result = parse(events)
    assert result["output"] == [item]
    assert stream.drain_text() == ()


def test_annotation_and_logprob_data_survive_without_becoming_early_text():
    annotation = {
        "type": "url_citation",
        "start_index": 0,
        "end_index": 1,
        "title": "Synthetic",
        "url": "https://example.invalid",
    }
    event_logprob = {"token": "x", "logprob": -0.5, "top_logprobs": []}
    output_logprob = {**event_logprob, "bytes": [120]}
    item = message("x")
    item["content"][0].update(annotations=[annotation], logprobs=[output_logprob])
    events = events_for(message("x"))
    events[5]["logprobs"] = [event_logprob]
    events[6]["logprobs"] = [event_logprob]
    events[7]["part"] = deepcopy(item["content"][0])
    events[8]["item"] = deepcopy(item)
    events[9]["response"]["output"] = [deepcopy(item)]
    events.insert(
        7,
        {
            "type": "response.output_text.annotation.added",
            "output_index": 0,
            "item_id": item["id"],
            "content_index": 0,
            "annotation_index": 0,
            "annotation": annotation,
        },
    )
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream, result = parse(events)
    assert result["output"] == [item]
    assert stream.drain_text() == ("x",)


@pytest.mark.parametrize(
    "logprobs", [None, {}, [{"token": "x", "bytes": [True], "logprob": -1, "top_logprobs": []}]]
)
def test_bad_logprob_in_the_current_event_cannot_publish_its_text(logprobs):
    events = events_for(message())[:5]
    events[4]["logprobs"] = logprobs
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()


@pytest.mark.parametrize("bad_order", [False, True])
def test_web_search_progress_tracks_the_known_item_and_monotonic_phase(bad_order):
    item = {
        "type": "web_search_call",
        "id": "ws_fixture",
        "status": "completed",
        "action": {"type": "open_page", "url": "https://example.invalid"},
    }
    events = events_for(item)
    phases = ["in_progress", "searching", "completed"]
    if bad_order:
        phases.reverse()
    progress = [
        {"type": "response.web_search_call." + phase, "output_index": 0, "item_id": item["id"]}
        for phase in phases
    ]
    events[3:3] = progress
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    if bad_order:
        with pytest.raises(ProviderError):
            parse(events)
    else:
        stream, result = parse(events)
        assert result["output"] == [item]
        assert stream.drain_text() == ()


def test_sse_multiline_data_and_optional_event_names_follow_the_framing_contract():
    events = events_for(message())
    body = wire(events, named=False)
    body = body.replace(b'"response", "created_at"', b'"response",\ndata: "created_at"')
    body = b"event: ignored\nevent:\n" + body
    stream = ResponsesStream()
    stream.feed(body)
    assert stream.finish() == events[-1]["response"]


def test_json_numeric_overflow_fails_safely():
    stream = ResponsesStream()
    stream.feed(wire(events_for(message())[:4]))
    raw = wire([events_for(message())[4]]).replace(
        b'"logprobs": []',
        b'"logprobs": [{"token":"x","bytes":[],"logprob":1e9999,"top_logprobs":[]}]',
    )
    stream.feed(raw)
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError, match="^Provider request failed$"):
        stream.finish()


def test_already_drained_prefix_remains_irreversible_but_failure_stops_future_text():
    events = events_for(message("prefixsuffix"))
    stream = ResponsesStream()
    stream.feed(wire(events[:5]))
    assert stream.drain_text() == ("prefix",)
    stream.feed(wire([{**events[5], "item_id": "missing"}, *events[6:]]))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


@pytest.mark.parametrize("snapshot", [0, 1, 9], ids=["created", "in-progress", "terminal"])
def test_deep_snapshot_is_rejected_before_copy_or_text_drain(snapshot):
    events = events_for(message())
    nested = "synthetic"
    for _ in range(600):
        nested = {"nested": nested}
    events[snapshot]["response"]["metadata"] = nested
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


def test_terminal_copy_failure_is_safe_sticky_and_discards_pending_text(monkeypatch):
    stream = ResponsesStream()
    stream.feed(wire(events_for(message())))

    def failed_copy(_):
        raise RecursionError("synthetic copy failure")

    monkeypatch.setattr("gateway7.responses_stream.deepcopy", failed_copy)
    for _ in range(2):
        with pytest.raises(ProviderError, match="^Provider request failed$") as caught:
            stream.finish()
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
        assert stream.native_usage == USAGE
        assert stream.drain_text() == ()


@pytest.mark.parametrize("snapshot", [0, 1], ids=["created", "in-progress"])
@pytest.mark.parametrize("extra", [None, "synthetic"])
def test_unmodelled_semantic_intermediate_response_envelope_field_is_rejected(snapshot, extra):
    events = events_for(message())
    events[snapshot]["response"]["headers"] = extra
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


def test_known_response_envelope_echo_fields_remain_native():
    events = events_for(message())
    for index in (0, 1, 9):
        events[index]["response"].update(
            metadata={"fixture": "synthetic"},
            background=False,
            store=False,
            instructions="synthetic instruction",
            temperature=0.5,
            top_p=0.9,
        )
    _, result = parse(events)
    assert result == events[-1]["response"]


def probability_events(*, delta_top=None, done_top=None, output_top=None):
    events = events_for(message("x"))
    delta = {"token": "x", "logprob": -0.5, **(delta_top or {})}
    done = {"token": "x", "logprob": -0.5, **(done_top or {})}
    output = {
        "token": "x",
        "bytes": [120],
        "logprob": -0.5,
        "top_logprobs": [] if output_top is None else output_top,
    }
    events[5]["logprobs"] = [delta]
    events[6]["logprobs"] = [done]
    events[7]["part"]["logprobs"] = [deepcopy(output)]
    events[8]["item"]["content"][0]["logprobs"] = [deepcopy(output)]
    events[9]["response"]["output"][0]["content"][0]["logprobs"] = [deepcopy(output)]
    return events


@pytest.mark.parametrize(
    "top",
    [{}, {"top_logprobs": None}, {"top_logprobs": [{"token": None, "logprob": -1.0}]}],
    ids=["omitted", "nullable", "partial-top-token"],
)
def test_event_logprobs_need_no_bytes_or_invented_optional_top_fields(top):
    output_top = [{"token": "y", "bytes": [121], "logprob": -1.0}]
    events = probability_events(delta_top=top, done_top=top, output_top=output_top)
    stream, result = parse(events)
    assert result == events[-1]["response"]
    assert stream.drain_text() == ("x",)
    assert "bytes" not in events[5]["logprobs"][0]


@pytest.mark.parametrize(
    "mismatch", ["done-token", "done-probability", "final-probability", "final-top"]
)
def test_logprobs_compare_reported_common_values_across_event_and_final_shapes(mismatch):
    top = {"top_logprobs": [{"token": "y", "logprob": -1.0}]}
    events = probability_events(
        delta_top=top,
        done_top=top,
        output_top=[{"token": "y", "bytes": [121], "logprob": -1.0}],
    )
    if mismatch == "done-token":
        events[6]["logprobs"][0]["token"] = "z"
    elif mismatch == "done-probability":
        events[6]["logprobs"][0]["logprob"] = -0.7
    elif mismatch == "final-probability":
        events[7]["part"]["logprobs"][0]["logprob"] = -0.7
    else:
        events[7]["part"]["logprobs"][0]["top_logprobs"][0]["logprob"] = -2.0
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()


def test_done_event_optional_logprobs_are_checked_even_when_delta_omits_them():
    events = probability_events(
        done_top={"top_logprobs": [{"token": "y", "logprob": -1.0}]},
        output_top=[{"token": "y", "bytes": [121], "logprob": -2.0}],
    )
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()


@pytest.mark.parametrize(
    "reported",
    [
        USAGE,
        {"input_tokens": 19},
        {"output_tokens": 11},
        {"total_tokens": 30},
        {"input_tokens": 0},
        {"input_tokens": None, "output_tokens": 11, "total_tokens": None},
        {"input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": None}},
        {"output_tokens_details": {"reasoning_tokens": 5}},
        {"input_tokens": 19, "input_tokens_details": None},
    ],
)
def test_native_usage_preserves_full_and_legitimately_partial_source_counts(reported):
    stream, result = parse(events_for(message(), usage=reported))
    assert stream.native_usage == reported
    assert result["usage"] == reported
    expected = (
        {"input_tokens": reported["input_tokens"], "output_tokens": reported["output_tokens"]}
        if reported.get("input_tokens") is not None and reported.get("output_tokens") is not None
        else None
    )
    assert stream.usage == expected


@pytest.mark.parametrize("unknown", [None, {}, {"input_tokens": None}])
def test_native_usage_unknown_values_do_not_fabricate_counts_or_erase_known_source(unknown):
    stream = ResponsesStream()
    assert stream.native_usage is None
    stream.feed(
        wire(
            [
                {
                    "type": "response.created",
                    "sequence_number": 0,
                    "response": response(usage=unknown),
                }
            ]
        )
    )
    assert stream.native_usage is None

    events = events_for(message(), usage=unknown)
    events[0]["response"]["usage"] = USAGE
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.native_usage == USAGE
    assert stream.finish()["usage"] == unknown


def test_native_usage_snapshots_are_detached_from_callers_and_canonical_output():
    stream, result = parse(events_for(message()))
    snapshot = stream.native_usage
    snapshot["input_tokens"] = -1
    snapshot["input_tokens_details"]["cached_tokens"] = -1
    snapshot["output_tokens_details"].clear()
    result["usage"]["input_tokens_details"]["cache_write_tokens"] = -1
    assert stream.native_usage == USAGE
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.finish()["usage"] == USAGE


@pytest.mark.parametrize(
    "malformed",
    [
        [],
        {**USAGE, "unknown": None},
        {**USAGE, "input_tokens": True},
        {**USAGE, "input_tokens": "19"},
        {**USAGE, "input_tokens": -1},
        {**USAGE, "input_tokens": 2**63},
        {**USAGE, "total_tokens": 31},
        {"input_tokens": 19, "total_tokens": 18},
        {**USAGE, "input_tokens_details": []},
        {**USAGE, "input_tokens_details": {"private": None}},
        {**USAGE, "input_tokens_details": {"cached_tokens": True}},
        {**USAGE, "input_tokens_details": {"cache_write_tokens": 20}},
        {**USAGE, "output_tokens_details": {"private": 1}},
        {**USAGE, "output_tokens_details": {"reasoning_tokens": 12}},
    ],
)
def test_native_usage_malformed_after_valid_never_overwrites_trustworthy_snapshot(malformed):
    events = events_for(message(), usage=malformed)
    events[0]["response"]["usage"] = USAGE
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    assert stream.native_usage == USAGE
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert stream.native_usage == USAGE


def test_native_usage_deep_malformed_details_never_replace_a_valid_snapshot():
    events = events_for(message())
    events[0]["response"]["usage"] = USAGE
    nested = 1
    for _ in range(100):
        nested = {"cached_tokens": nested}
    events[-1]["response"]["usage"] = {"input_tokens_details": nested}
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.native_usage == USAGE
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()


def test_native_usage_is_captured_after_sticky_protocol_failure():
    events = events_for(message())
    events[4]["item_id"] = "missing"
    stream = ResponsesStream()
    stream.feed(wire(events[:5]))
    assert stream.native_usage is None
    stream.feed(wire(events[5:]))
    assert stream.native_usage == USAGE
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError):
        stream.finish()
    assert stream.native_usage == USAGE


@pytest.mark.parametrize("failed_response", [False, True])
def test_native_usage_remains_available_after_a_failure_terminal(failed_response):
    events = events_for(message())[:5]
    if failed_response:
        terminal = response(status="failed", usage=USAGE)
        terminal["error"] = {"code": "server_error", "message": "synthetic failure"}
        events.append({"type": "response.failed", "sequence_number": 5, "response": terminal})
    else:
        events[0]["response"]["usage"] = USAGE
        events.append(
            {
                "type": "error",
                "sequence_number": 5,
                "code": "server_error",
                "message": "synthetic failure",
            }
        )
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.UNAVAILABLE
    assert stream.native_usage == USAGE


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_native_usage_survives_a_consumer_stopping_before_terminal(failure):
    events = events_for(message())[:5]
    events[0]["response"]["usage"] = USAGE
    stream = ResponsesStream()
    stream.feed(wire(events))
    with pytest.raises(failure):
        for text in stream.drain_text():
            assert text
            raise failure()
    assert stream.native_usage == USAGE


@pytest.mark.parametrize(
    "changed_snapshot", [None, 1, 9], ids=["unchanged", "in-progress", "terminal"]
)
def test_structured_envelope_snapshots_distinguish_booleans_from_numbers(changed_snapshot):
    events = events_for(message())
    tools = [
        {
            "type": "function",
            "name": "read",
            "parameters": {"type": "object", "properties": {"value": {"const": True}}},
        }
    ]
    for snapshot in (0, 1, 9):
        events[snapshot]["response"]["tools"] = deepcopy(tools)
    events[0]["response"]["usage"] = USAGE
    if changed_snapshot is not None:
        events[changed_snapshot]["response"]["tools"][0]["parameters"]["properties"]["value"][
            "const"
        ] = 1
    stream = ResponsesStream()
    stream.feed(wire(events))
    if changed_snapshot is None:
        assert stream.finish() == events[-1]["response"]
        assert "".join(stream.drain_text()) == message()["content"][0]["text"]
    else:
        assert stream.drain_text() == ()
        with pytest.raises(ProviderError) as caught:
            stream.finish()
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert stream.native_usage == USAGE


@pytest.mark.parametrize("previous", [USAGE, {"input_tokens": 19, "total_tokens": 30}])
@pytest.mark.parametrize(
    "family,name",
    [
        ("input_tokens_details", "cached_tokens"),
        ("input_tokens_details", "cache_write_tokens"),
        ("output_tokens_details", "reasoning_tokens"),
    ],
)
def test_native_usage_detail_above_total_rejects_without_parent_and_retains_previous(
    previous, family, name
):
    events = events_for(message(), usage={"total_tokens": 0, family: {name: 1}})
    events[0]["response"]["usage"] = previous
    stream = ResponsesStream()
    stream.feed(wire(events[:1]))
    accounting = stream.usage
    stream.feed(wire(events[1:]))
    assert stream.native_usage == previous
    assert stream.usage == accounting
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == accounting
    assert stream.native_usage == previous


@pytest.mark.parametrize(
    "reported",
    [
        {"total_tokens": 1, "input_tokens_details": {"cached_tokens": 1}},
        {"total_tokens": 1, "input_tokens_details": {"cache_write_tokens": 1}},
        {"total_tokens": 1, "output_tokens_details": {"reasoning_tokens": 1}},
        {
            "total_tokens": 1,
            "input_tokens_details": {"cached_tokens": 1, "cache_write_tokens": 1},
        },
        {
            "input_tokens_details": {"cached_tokens": 1, "cache_write_tokens": 1},
            "output_tokens_details": {"reasoning_tokens": 1},
        },
        {"input_tokens": None, "total_tokens": 1, "input_tokens_details": {"cached_tokens": 1}},
    ],
)
def test_native_usage_legal_omitted_parent_details_are_not_summed_or_used_to_derive_counts(
    reported,
):
    stream, result = parse(events_for(message(), usage=reported))
    assert stream.native_usage == reported
    assert result["usage"] == reported
    assert stream.usage is None


@pytest.mark.parametrize(
    "changed",
    [
        {"id": None},
        {"id": ""},
        {"id": "resp_invalid\nid"},
        {"id": "resp_other"},
        {"object": "chat.completion"},
        {"model": "other-model"},
        {"created_at": 2.0},
        {"created_at": True},
    ],
    ids=[
        "null-id",
        "empty-id",
        "invalid-id",
        "mismatched-id",
        "invalid-object",
        "changed-model",
        "changed-created-at",
        "boolean-created-at",
    ],
)
def test_usage_identity_rejects_terminal_changes_before_committing_new_counts(changed):
    incoming = {**deepcopy(USAGE), "input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
    events = events_for(message(), usage=incoming)
    events[0]["response"]["usage"] = USAGE
    events[-1]["response"].update(changed)
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.native_usage == USAGE
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.native_usage == USAGE


@pytest.mark.parametrize("outcome", ["completed", "bad-output", "sticky-output", "failed"])
def test_usage_identity_valid_source_can_account_even_when_output_fails(outcome):
    incoming = {**deepcopy(USAGE), "input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
    events = events_for(message(), usage=incoming)
    if outcome == "bad-output":
        events[-1]["response"]["output"][0]["content"][0]["text"] = "different"
    elif outcome == "sticky-output":
        events[4]["item_id"] = "missing"
    elif outcome == "failed":
        events[-1]["type"] = "response.failed"
        events[-1]["response"]["status"] = "failed"
        events[-1]["response"]["error"] = {"code": "server_error", "message": "synthetic failure"}
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.native_usage == incoming
    assert stream.usage == {"input_tokens": 999, "output_tokens": 888}
    if outcome == "completed":
        assert stream.finish()["usage"] == incoming
    else:
        assert stream.drain_text() == ()
        with pytest.raises(ProviderError) as caught:
            stream.finish()
        expected = (
            ProviderErrorReason.UNAVAILABLE
            if outcome == "failed"
            else ProviderErrorReason.INVALID_RESPONSE
        )
        assert caught.value.reason is expected
        assert caught.value.usage == {"input_tokens": 999, "output_tokens": 888}
        assert stream.native_usage == incoming


@pytest.mark.parametrize("phase", [None, "commentary", "final_answer"])
def test_typed_drain_preserves_real_identity_indices_phase_sequence_and_head(phase):
    item = message("abcd")
    if phase is None:
        item.pop("phase")
    else:
        item["phase"] = phase
    events = events_for(item)
    for index, event in enumerate(events):
        event["sequence_number"] = 100 + index * 3
    stream = ResponsesStream()
    stream.feed(wire(events[:6]))
    records = stream.drain_text_deltas()
    assert all(isinstance(record, ResponsesTextDelta) for record in records)
    assert [(record.delta, record.sequence_number) for record in records] == [
        ("ab", 112),
        ("cd", 115),
    ]
    for record in records:
        assert record.head.id == "resp_fixture"
        assert record.head.created_at == 1.0
        assert record.head.model == "synthetic-model"
        assert record.head.parallel_tool_calls is True
        assert record.head.tool_choice == "auto"
        assert record.head.tools == ()
        assert (record.item_id, record.output_index, record.content_index) == (item["id"], 0, 0)
        assert record.phase == phase
        assert record.leading_prefix is True
    assert stream.drain_text_deltas() == ()
    stream.feed(wire(events[6:]))
    assert stream.finish() == events[-1]["response"]
    assert stream.drain_text_deltas() == ()


def test_typed_drain_and_string_wrapper_consume_one_queue_without_duplicate_delivery():
    events = events_for(message("abcd"))
    stream = ResponsesStream()
    assert stream.drain_text_deltas() == ()
    stream.feed(wire(events[:5]))
    assert stream.drain_text() == ("ab",)
    assert stream.drain_text_deltas() == ()
    stream.feed(wire(events[5:6]))
    assert [record.delta for record in stream.drain_text_deltas()] == ["cd"]
    assert stream.drain_text() == ()
    stream.feed(wire(events[6:]))
    assert stream.finish() == events[-1]["response"]
    assert stream.drain_text_deltas() == ()
    assert stream.drain_text() == ()


def test_typed_drain_waits_for_complete_utf8_and_event_validation():
    events = events_for(message("🌍"))
    stream = ResponsesStream()
    stream.feed(wire(events[:4]))
    event = wire([events[5]]).replace(b'"\\ud83c\\udf0d"', '"🌍"'.encode())
    split = event.index("🌍".encode()) + 1
    stream.feed(event[:split])
    assert stream.drain_text_deltas() == ()
    stream.feed(event[split:-1])
    assert stream.drain_text_deltas() == ()
    stream.feed(event[-1:])
    (record,) = stream.drain_text_deltas()
    assert (record.delta, record.sequence_number, record.leading_prefix) == ("🌍", 5, True)


@pytest.mark.parametrize("profile", ["reasoning", "function", "custom", "web", "search", "refusal"])
def test_typed_drain_preserves_text_after_nontext_without_claiming_a_leading_prefix(profile):
    final = message("later")
    if profile == "reasoning":
        first = {
            "type": "reasoning",
            "id": "rs_fixture",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": "private summary"}],
            "encrypted_content": "SYNTHETIC_OPAQUE",
        }
    elif profile in ("function", "custom"):
        first = call("first", "function_call" if profile == "function" else "custom_tool_call")
    elif profile == "web":
        first = {
            "type": "web_search_call",
            "id": "ws_fixture",
            "status": "completed",
            "action": {"type": "search", "query": "synthetic"},
        }
    elif profile == "search":
        first = {
            "type": "tool_search_call",
            "id": "search_fixture",
            "call_id": "call_search",
            "status": "completed",
            "execution": "client",
            "arguments": {"query": "synthetic"},
        }
    else:
        final["content"].insert(0, {"type": "refusal", "refusal": "private refusal"})
        first = None
    events = events_for(final) if first is None else events_for(first, final)
    stream, result = parse(events)
    records = stream.drain_text_deltas()
    assert "".join(record.delta for record in records) == "later"
    assert all(record.leading_prefix is False for record in records)
    assert {(record.item_id, record.output_index, record.content_index) for record in records} == {
        (final["id"], 0, 1) if first is None else (final["id"], 1, 0)
    }
    assert result == events[-1]["response"]


@pytest.mark.parametrize("boundary", ["item", "part"])
def test_typed_drain_prefix_window_never_reopens_after_a_parallel_boundary(boundary):
    item = message("abcd")
    if boundary == "item":
        events = events_for(item, call("later"))
        order = (0, 1, 2, 3, 4, 9, 5, 6, 7, 8, 10, 11, 12, 13, 14)
    else:
        item["content"].append({"type": "output_text", "text": "later", "annotations": []})
        events = events_for(item)
        order = (0, 1, 2, 3, 4, 8, 5, 6, 7, 9, 10, 11, 12, 13, 14)
    events = [events[index] for index in order]
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream, result = parse(events)
    records = stream.drain_text_deltas()
    assert [(record.delta, record.leading_prefix) for record in records[:2]] == [
        ("ab", True),
        ("cd", False),
    ]
    assert all(record.leading_prefix is False for record in records[1:])
    assert result == events[-1]["response"]


def test_typed_drain_later_messages_and_parts_retain_canonical_order_and_phase():
    first = message("abcd")
    first["phase"] = "commentary"
    first["content"].append({"type": "output_text", "text": "second part", "annotations": []})
    second = {**message("answer"), "id": "msg_answer"}
    events = events_for(first, second)
    stream, result = parse(events)
    records = stream.drain_text_deltas()
    assert [record.leading_prefix for record in records[:2]] == [True, True]
    assert all(record.leading_prefix is False for record in records[2:])
    assert {(record.item_id, record.phase) for record in records} == {
        (first["id"], "commentary"),
        (second["id"], "final_answer"),
    }
    assert result["output"] == [first, second]


def test_typed_drain_held_annotation_closes_the_window_before_later_leading_part_text():
    annotation = {
        "type": "url_citation",
        "start_index": 0,
        "end_index": 1,
        "title": "Synthetic",
        "url": "https://example.invalid",
    }
    events = events_for(message("abcd"))
    for part in (
        events[7]["part"],
        events[8]["item"]["content"][0],
        events[9]["response"]["output"][0]["content"][0],
    ):
        part["annotations"] = [deepcopy(annotation)]
    events.insert(
        5,
        {
            "type": "response.output_text.annotation.added",
            "output_index": 0,
            "item_id": "msg_fixture",
            "content_index": 0,
            "annotation_index": 0,
            "annotation": annotation,
        },
    )
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    stream, result = parse(events)
    assert [(record.delta, record.leading_prefix) for record in stream.drain_text_deltas()] == [
        ("ab", True),
        ("cd", False),
    ]
    assert result == events[-1]["response"]


def test_typed_drain_nonempty_logprobs_are_held_metadata_not_an_early_prefix():
    events = probability_events()
    stream, result = parse(events)
    (record,) = stream.drain_text_deltas()
    assert (record.delta, record.leading_prefix) == ("x", False)
    assert result == events[-1]["response"]


@pytest.mark.parametrize("failure", ["current-event", "terminal-identity", "terminal-depth"])
def test_typed_drain_discards_pending_records_on_invalid_events_and_preserves_accounting(failure):
    events = events_for(message())
    events[0]["response"]["usage"] = USAGE
    if failure == "current-event":
        events[5]["private_extension"] = None
    elif failure == "terminal-identity":
        events[-1]["response"]["id"] = "resp_other"
    else:
        nested = "synthetic"
        for _ in range(100):
            nested = {"nested": nested}
        events[-1]["response"]["metadata"] = nested
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text_deltas() == ()
    assert stream.drain_text() == ()
    assert stream.native_usage == USAGE
    with pytest.raises(ProviderError):
        stream.finish()


def test_typed_drain_header_is_validated_before_committing_the_current_text_event():
    events = events_for(message())
    events[0]["response"]["usage"] = USAGE
    for index in (0, 1, 9):
        events[index]["response"]["tools"] = [
            {
                "type": "function",
                "name": "read",
                "parameters": {"type": "object"},
                "private_extension": None,
            }
        ]
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.drain_text_deltas() == ()
    assert stream.drain_text() == ()
    assert stream.native_usage == USAGE
    with pytest.raises(ProviderError, match="^Provider request failed$"):
        stream.finish()


def test_typed_drain_heads_are_detached_across_records_and_from_canonical_state():
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    tools = [
        {
            "type": "namespace",
            "name": "alpha",
            "description": "Synthetic",
            "tools": [{"type": "function", "name": "read", "parameters": schema}],
        }
    ]
    events = events_for(message("abcd"))
    for index in (0, 1, 9):
        events[index]["response"]["tools"] = deepcopy(tools)
    stream = ResponsesStream()
    stream.feed(wire(events[:5]))
    (first,) = stream.drain_text_deltas()
    first.head.tools[0].tools[0].parameters["properties"]["path"]["type"] = "integer"
    stream.feed(wire(events[5:]))
    (second,) = stream.drain_text_deltas()
    assert second.head.tools[0].tools[0].parameters == schema
    assert stream.finish() == events[-1]["response"]


def events_with_rejected_created(violation, first_usage, terminal_usage):
    events = events_for(message(), usage=terminal_usage)
    created = events[0]["response"]
    created["usage"] = deepcopy(first_usage)
    if violation == "semantic-field":
        created["end_turn"] = None
    elif violation == "control-type":
        created["parallel_tool_calls"] = 1
    else:
        nested = "synthetic"
        for _ in range(100):
            nested = {"nested": nested}
        created["metadata"] = nested
    return events


@pytest.mark.parametrize("violation", ["semantic-field", "control-type", "depth"])
@pytest.mark.parametrize(
    "changed",
    [
        None,
        {"id": "resp_other"},
        {"model": "other-model"},
        {"created_at": 2.0},
        {"object": "chat.completion"},
    ],
    ids=["same-identity", "different-id", "different-model", "different-time", "invalid-object"],
)
def test_accounting_identity_pin_survives_rejected_created_before_initial_acceptance(
    violation, changed
):
    incoming = {**deepcopy(USAGE), "input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
    if changed is None:
        incoming = deepcopy(USAGE)
        incoming["input_tokens_details"]["cached_tokens"] = 8
    events = events_with_rejected_created(violation, USAGE, incoming)
    if changed is not None:
        events[-1]["response"].update(changed)
    stream = ResponsesStream()
    stream.feed(wire(events[:1]))
    assert stream.native_usage == USAGE
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    stream.feed(wire(events[1:]))
    expected = incoming if changed is None else USAGE
    assert stream.native_usage == expected
    assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.drain_text_deltas() == ()
    assert stream.drain_text() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
    assert stream.native_usage == expected


@pytest.mark.parametrize(
    "first_usage",
    [
        None,
        {},
        {"input_tokens": True},
        {"total_tokens": 0, "output_tokens_details": {"reasoning_tokens": 1}},
    ],
)
def test_accounting_identity_pin_is_not_established_from_unknown_or_malformed_usage(first_usage):
    incoming = {**deepcopy(USAGE), "input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
    events = events_with_rejected_created("semantic-field", first_usage, incoming)
    events[-1]["response"]["id"] = "resp_other"
    stream = ResponsesStream()
    stream.feed(wire(events[:1]))
    assert stream.native_usage is None
    stream.feed(wire(events[1:]))
    assert stream.native_usage == incoming
    assert stream.usage == {"input_tokens": 999, "output_tokens": 888}
    assert stream.drain_text_deltas() == ()
    with pytest.raises(ProviderError):
        stream.finish()


@pytest.mark.parametrize(
    "first_usage",
    [{"input_tokens": 19}, {"total_tokens": 0}, {"input_tokens_details": {"cached_tokens": 1}}],
)
def test_accounting_identity_pin_is_established_by_trustworthy_partial_usage(first_usage):
    incoming = {**deepcopy(USAGE), "input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
    events = events_with_rejected_created("semantic-field", first_usage, incoming)
    events[-1]["response"]["id"] = "resp_other"
    stream = ResponsesStream()
    stream.feed(wire(events))
    assert stream.native_usage == first_usage
    assert stream.usage is None
    assert stream.drain_text_deltas() == ()
    with pytest.raises(ProviderError) as caught:
        stream.finish()
    assert caught.value.usage is None


def test_raw_projection_keeps_event_roots_and_item_trees_closed():
    cases = []
    for field in ("headers", "metadata", "safety_buffering", "synthetic_event_extension"):
        events = events_for(message())
        events[0][field] = None
        cases.append(events)
    for kind in ("response.metadata", "response.headers", "response.synthetic_extension"):
        events = events_for(message())
        events[0]["type"] = kind
        cases.append(events)
    for item in (
        {**message(), "synthetic_item_extension": None},
        message(),
        {**call(), "synthetic_tool_extension": None},
        {"type": "reasoning", "id": "rs_fixture", "summary": [], "synthetic_extension": None},
    ):
        if item == message():
            item["content"][0]["synthetic_content_extension"] = None
        cases.append(events_for(item))
    for events in cases:
        for event in events:
            if "response" in event:
                event["response"]["synthetic_admin_echo"] = "SYNTHETIC_DISCARD_CANARY"
        stream = ResponsesStream()
        stream.feed(wire(events))
        assert stream.drain_text_deltas() == ()
        with pytest.raises(ProviderError) as caught:
            stream.finish()
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert stream.usage == {"input_tokens": 19, "output_tokens": 11}


@pytest.mark.parametrize("size", [1, 4096])
def test_output_text_delta_padding_is_discarded_without_changing_text_or_records(
    size, monkeypatch, caplog, capsys
):
    original_process = ResponsesStream._process

    def process_without_padding(self, kind, event):
        assert "obfuscation" not in event
        return original_process(self, kind, event)

    monkeypatch.setattr(ResponsesStream, "_process", process_without_padding)
    item = message("abcd")
    item["content"].append({"type": "output_text", "text": "later", "annotations": []})
    control = events_for(item)
    reference, expected = parse(control, size=size)
    expected_records = reference.drain_text_deltas()
    assert [record.leading_prefix for record in expected_records] == [True, True, False, False]
    for padding in (None, "", "SYNTHETIC_PADDING_ONLY", "SYNTHETIC_PADDING_ONLY_填充🧪"):
        events = deepcopy(control)
        if padding is not None:
            for event in events:
                if event["type"] == "response.output_text.delta":
                    event["obfuscation"] = padding
        body = wire(events)
        if padding:
            body = body.replace(
                json.dumps(padding).encode("ascii"),
                json.dumps(padding, ensure_ascii=False).encode("utf-8"),
            )
        stream = ResponsesStream()
        records = []
        for offset in range(0, len(body), size):
            stream.feed(body[offset : offset + size])
            records.extend(stream.drain_text_deltas())
            assert stream.drain_text() == ()
        result = stream.finish()
        assert result == expected
        assert tuple(records) == expected_records
        assert stream.native_usage == USAGE
        assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
        assert stream.drain_text_deltas() == ()
        public = json.dumps(
            {"response": result, "records": [record.model_dump(mode="json") for record in records]},
            ensure_ascii=False,
        )
        assert "obfuscation" not in public
        if padding:
            assert padding not in public
    assert caplog.records == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("case", ["null", "nonstring", "unknown-field", "wrong-family", "nested"])
def test_output_text_delta_padding_keeps_other_shapes_closed_and_clears_pending(case):
    for variant in ("item", "content") if case == "nested" else (case,):
        events = (
            events_for(message("abcd"), call())
            if case == "wrong-family"
            else events_for(message("abcd"))
        )
        events[0]["response"]["usage"] = deepcopy(USAGE)
        for event in events:
            if event["type"] == "response.output_text.delta":
                event["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        if case == "null":
            events[5]["obfuscation"] = None
        elif case == "nonstring":
            events[5]["obfuscation"] = 7
        elif case == "unknown-field":
            events[5]["synthetic_unknown"] = None
        elif case == "wrong-family":
            events[10]["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        elif variant == "item":
            events[8]["item"]["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        else:
            events[7]["part"]["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        stream = ResponsesStream()
        stream.feed(wire(events))
        assert stream.drain_text_deltas() == ()
        assert stream.drain_text() == ()
        assert stream.native_usage == USAGE
        assert stream.usage == {"input_tokens": 19, "output_tokens": 11}
        with pytest.raises(ProviderError) as caught:
            stream.finish()
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
        assert "SYNTHETIC_PADDING_ONLY" not in str(caught.value)


def test_output_text_delta_padding_does_not_hide_raw_json_violations():
    for violation in ("duplicate", "nonfinite", "depth"):
        events = events_for(message("abcd"))
        events[0]["response"]["usage"] = deepcopy(USAGE)
        events[4]["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        event = deepcopy(events[5])
        event["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        if violation == "nonfinite":
            event["obfuscation"] = float("nan")
        elif violation == "depth":
            nested = None
            for _ in range(100):
                nested = {"nested": nested}
            event["obfuscation"] = nested
        encoded = wire([event])
        if violation == "duplicate":
            encoded = encoded.replace(
                b'"obfuscation": "SYNTHETIC_PADDING_ONLY"',
                b'"obfuscation": "first", "obfuscation": "second"',
                1,
            )
        stream = ResponsesStream()
        stream.feed(wire(events[:5]) + encoded + wire(events[6:]))
        assert stream.drain_text_deltas() == ()
        assert stream.drain_text() == ()
        assert stream.native_usage == USAGE
        with pytest.raises(ProviderError) as caught:
            stream.finish()
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}


def test_output_text_delta_padding_counts_toward_event_and_body_byte_budgets():
    for budget in ("event", "body"):
        events = events_for(message("abcd"))
        events[0]["response"]["usage"] = deepcopy(USAGE)
        events[4]["obfuscation"] = "SYNTHETIC_PADDING_ONLY"
        stream = ResponsesStream()
        stream.feed(wire(events[:5]))
        event = deepcopy(events[5])
        if budget == "event":
            event["obfuscation"] = "填" * MAX_EVENT_BYTES
            body = wire([event])
            assert MAX_EVENT_BYTES < len(body) < MAX_RESPONSE_BYTES
        else:
            event["delta"] = ""
            event["obfuscation"] = "P" * (MAX_EVENT_BYTES // 2)
            repeated = []
            for sequence in range(5, 45):
                event["sequence_number"] = sequence
                assert len(wire([event])) < MAX_EVENT_BYTES
                repeated.append(deepcopy(event))
            body = wire(repeated)
            assert len(body) > MAX_RESPONSE_BYTES
        with pytest.raises(ProviderError) as caught:
            for offset in range(0, len(body), 4096):
                stream.feed(body[offset : offset + 4096])
        assert caught.value.reason is ProviderErrorReason.INVALID_RESPONSE
        assert caught.value.usage == {"input_tokens": 19, "output_tokens": 11}
        assert stream.native_usage == USAGE
        assert stream.drain_text_deltas() == ()
        assert stream.drain_text() == ()
        with pytest.raises(ProviderError):
            stream.finish()

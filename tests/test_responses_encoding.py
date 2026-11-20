"""Checked native output is reconstructed without replaying upstream SSE."""

from copy import deepcopy
import json
import warnings

from openai.types.responses import Response, ResponseStreamEvent
from pydantic import TypeAdapter, ValidationError
import pytest

from gateway7.errors import GatewayError
from gateway7.responses_api import EarlyResponsesEncoder, response_json, response_sse
from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import MAX_JSON_BYTES, FunctionTool, ResponsesResponse


SDK_RESPONSE = TypeAdapter(Response)
SDK_EVENT = TypeAdapter(ResponseStreamEvent)
USAGE = {
    "input_tokens": 19,
    "input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 3},
    "output_tokens": 11,
    "output_tokens_details": {"reasoning_tokens": 5},
    "total_tokens": 30,
}
RAW = "*** Begin Patch\n*** Add File: synthetic.txt\n+Synthetic\n*** End Patch\n"


def message(text="Synthetic answer", **changes):
    return {
        "type": "message",
        "id": "msg_synthetic",
        "role": "assistant",
        "phase": "final_answer",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
        **changes,
    }


def function(suffix="a", namespace="alpha", **changes):
    return {
        "type": "function_call",
        "id": "fc_item_" + suffix,
        "call_id": "call_" + suffix,
        "name": "read",
        "namespace": namespace,
        "arguments": ' {"path": "данные/🌍.txt"} ',
        "status": "completed",
        **changes,
    }


def reasoning(**changes):
    return {
        "type": "reasoning",
        "id": "rs_synthetic",
        "status": "completed",
        "summary": [{"type": "summary_text", "text": "Synthetic summary"}],
        "content": [{"type": "reasoning_text", "text": "Synthetic reasoning text"}],
        "encrypted_content": "SYNTHETIC_OPAQUE_PRESERVE==",
        **changes,
    }


def response(*output, **changes):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_synthetic",
            "object": "response",
            "model": "synthetic-model",
            "created_at": 1800000000.0,
            "status": "completed",
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "output": list(output),
            "usage": deepcopy(USAGE),
            **changes,
        }
    )


@pytest.mark.parametrize("namespace", [False, True])
def test_nullable_response_tool_echoes_preserve_exact_buffered_and_early_snapshots(namespace):
    from gateway7.responses_stream import ResponsesStream

    for mask in range(8):
        leaf = {
            "type": "function",
            "name": "read",
            "parameters": {"type": "object"},
            "strict": True,
            **{
                name: None
                for i, name in enumerate(("allowed_callers", "async", "output_schema"))
                if mask & (1 << i)
            },
        }
        tools = (
            [{"type": "namespace", "name": "alpha", "description": "Synthetic", "tools": [leaf]}]
            if namespace
            else [leaf]
        )
        choice = {
            "type": "function",
            "name": "read",
            **({"namespace": "alpha"} if namespace else {}),
        }
        answer = response(
            message(),
            function(namespace="alpha" if namespace else None),
            tools=tools,
            tool_choice=choice,
        )
        head = ResponsesStreamHead.model_validate(
            {**text_delta().head.wire_dict(), "tools": tuple(tools), "tool_choice": choice}
        )
        encoder = EarlyResponsesEncoder()
        early = publish(encoder, text_delta("Syn", head=head)) + encoder.complete(answer)
        for body in (response_sse(answer), early):
            parsed = sdk_checked_early(body, answer)
            assert all(
                event["response"]["tools"] == tools for event in parsed if "response" in event
            )
            stream = ResponsesStream()
            stream.feed(body)
            assert stream.finish() == response_json(answer)
        assert head.wire_dict()["tools"] == response_json(answer)["tools"] == tools
        changed = answer.model_copy(deep=True)
        owner = changed.tools[0].tools[0] if namespace else changed.tools[0]
        if mask & 1:
            owner.__pydantic_fields_set__.discard("allowed_callers")
        else:
            owner.__pydantic_fields_set__.add("allowed_callers")
        mismatch = EarlyResponsesEncoder()
        publish(mismatch, text_delta("Syn", head=head))
        with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
            mismatch.complete(changed)


def test_nullable_response_tool_echo_presence_activates_bounded_buffered_and_early_preflight(
    monkeypatch,
):
    import gateway7.responses_api as api

    assert not api._needs_compatibility_preflight(response_json(response(message())))
    monkeypatch.setattr(api, "MAX_EVENT_BYTES", 100)
    for field in ("allowed_callers", "async", "output_schema"):
        tools = [{"type": "function", "name": "read", "parameters": {}, field: None}]
        answer = response(message(), tools=tools)
        assert api._needs_compatibility_preflight(response_json(answer))
        with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
            response_sse(answer)
        head = ResponsesStreamHead.model_validate(
            {**text_delta().head.wire_dict(), "tools": tuple(tools)}
        )
        encoder = EarlyResponsesEncoder()
        assert encoder.stage_text(text_delta("Syn", head=head)) == "Syn"
        with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
            encoder.text("Syn")
        assert encoder._sequence == 0


def events(body, fragment_size=4096):
    """Read canonical fixture framing with deliberately arbitrary byte splits."""
    assert b"\ndata: [DONE]\n\n" not in body
    pending = b""
    parsed = []
    for offset in range(0, len(body), fragment_size):
        pending += body[offset : offset + fragment_size]
        while b"\n\n" in pending:
            frame, pending = pending.split(b"\n\n", 1)
            name, data = frame.decode("ascii").split("\n")
            assert name.startswith("event: ") and data.startswith("data: ")
            value = json.loads(data[6:])
            assert value["type"] == name[7:]
            parsed.append(value)
    assert not pending
    assert all(type(event["sequence_number"]) is int for event in parsed)
    assert [event["sequence_number"] for event in parsed] == list(range(len(parsed)))
    return parsed


def reconstruct(parsed, canonical):
    assert parsed[0]["type"] == "response.created"
    assert parsed[1]["type"] == "response.in_progress"
    assert parsed[-1]["type"] == "response." + canonical["status"]
    assert parsed[-1]["response"] == canonical
    assert (
        sum(
            event["type"] in {"response.completed", "response.incomplete", "response.failed"}
            for event in parsed
        )
        == 1
    )
    identity = tuple(canonical[key] for key in ("id", "object", "model", "created_at"))
    added, done, parts, strings = {}, {}, {}, {}
    string_done = set()
    part_done = set()
    for event in parsed:
        kind = event["type"]
        if "response" in event:
            assert (
                tuple(event["response"][key] for key in ("id", "object", "model", "created_at"))
                == identity
            )
            if kind in ("response.created", "response.in_progress"):
                assert event["response"]["status"] == "in_progress"
                assert event["response"]["output"] == []
                assert event["response"]["usage"] is None
                assert event["response"]["error"] is None
                assert event["response"]["incomplete_details"] is None
                assert "completed_at" not in event["response"]
            continue
        index = event["output_index"]
        assert type(index) is int
        if kind == "response.output_item.added":
            assert index == len(added)
            added[index] = event["item"]
            assert event["item"]["status"] == "in_progress"
            continue
        assert index in added and index not in done
        if kind == "response.output_item.done":
            item = event["item"]
            assert item["id"] == added[index]["id"]
            if item["type"] in ("function_call", "custom_tool_call"):
                field = "arguments" if item["type"] == "function_call" else "input"
                assert (index, field, 0) in string_done
                assert strings[index, field, 0] == item[field]
                assert item["call_id"] == added[index]["call_id"]
            elif item["type"] == "message":
                for sub, part in enumerate(item["content"]):
                    assert (index, "content", sub) in part_done
                    assert parts[index, "content", sub] == part
            elif item["type"] == "reasoning":
                for sub, part in enumerate(item["summary"]):
                    assert (index, "summary", sub) in part_done
                    assert parts[index, "summary", sub] == part
                for sub, part in enumerate(item.get("content") or []):
                    assert strings[index, "text", sub] == part["text"]
                    if part["type"] == "reasoning_text":
                        assert (index, "content", sub) in part_done
                        assert parts[index, "content", sub] == part
            done[index] = item
            continue
        assert event["item_id"] == added[index]["id"]
        if "content_part" in kind or "reasoning_summary_part" in kind:
            family = "summary" if "summary" in kind else "content"
            sub = event["summary_index" if family == "summary" else "content_index"]
            key = (index, family, sub)
            if kind.endswith(".added"):
                assert key not in parts
                parts[key] = event["part"]
            else:
                assert key in parts and key not in part_done
                part = event["part"]
                field = (
                    "refusal"
                    if part["type"] == "refusal"
                    else "summary"
                    if family == "summary"
                    else "text"
                )
                assert (index, field, sub) in string_done
                assert (
                    strings[index, field, sub] == part["refusal" if field == "refusal" else "text"]
                )
                parts[key] = part
                part_done.add(key)
        elif kind.endswith(".delta") or kind.endswith(".done"):
            field = (
                "arguments"
                if "function_call_arguments" in kind
                else "input"
                if "custom_tool_call_input" in kind
                else "summary"
                if "reasoning_summary_text" in kind
                else "refusal"
                if "refusal" in kind
                else "text"
            )
            sub = event.get("content_index", event.get("summary_index", 0))
            key = (index, field, sub)
            if kind.startswith("response.web_search_call"):
                continue
            assert key not in string_done
            if field in ("text", "refusal", "summary"):
                family = "summary" if field == "summary" else "content"
                legacy = (
                    kind.startswith("response.reasoning_text")
                    and canonical["output"][index]["content"][sub]["type"] == "text"
                )
                assert legacy or (index, family, sub) in parts
            if kind.endswith(".delta"):
                strings[key] = strings.get(key, "") + event["delta"]
            else:
                assert (
                    strings.get(key, "")
                    == event[field if field in ("arguments", "input", "refusal") else "text"]
                )
                strings[key] = strings.get(key, "")
                string_done.add(key)
    assert [done[index] for index in sorted(done)] == canonical["output"]
    assert set(parts) == part_done


@pytest.mark.parametrize("fragment_size", [1, 13, 4096])
def test_text_unicode_escaping_fragmentation_and_done_snapshots(fragment_size):
    text = 'Synthetic\n"quoted" — 🌍\ud800\nevent: injected\ndata: not-an-event [DONE]' * 30
    answer = response(message(text))
    before = answer.model_dump()
    body = response_sse(answer)
    parsed = events(body, fragment_size)
    reconstruct(parsed, response_json(answer))
    assert (
        "".join(event["delta"] for event in parsed if event["type"] == "response.output_text.delta")
        == text
    )
    assert answer.model_dump() == before
    assert response_sse(answer) == body
    assert b"\\ud800" in body and b"\\n" in body
    assert sum(event["type"] == "response.output_text.delta" for event in parsed) > 1


def test_parallel_namespace_custom_raw_input_and_original_output_order_are_preserved():
    custom = {
        "type": "custom_tool_call",
        "id": "ctc_item_patch",
        "call_id": "call_patch",
        "name": "apply_patch",
        "namespace": "functions",
        "status": "completed",
        "input": RAW,
    }
    answer = response(function(), function("b", "beta"), custom, message())
    canonical = response_json(answer)
    parsed = events(response_sse(answer))
    reconstruct(parsed, canonical)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)
    SDK_RESPONSE.validate_python(canonical, strict=True)
    assert [item["namespace"] for item in canonical["output"][:3]] == ["alpha", "beta", "functions"]
    assert canonical["output"][2]["input"] == RAW
    assert all(item["id"] != item["call_id"] for item in canonical["output"][:3])
    assert not any(
        event["type"].startswith("response.function_call_arguments")
        and event["item_id"] == "ctc_item_patch"
        for event in parsed
    )


def test_reasoning_summary_content_and_opaque_values_survive_canonical_snapshots():
    answer = response(reasoning(), message())
    parsed = events(response_sse(answer))
    reconstruct(parsed, response_json(answer))
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)
    assert parsed[2]["item"]["summary"] == []
    assert "encrypted_content" not in parsed[2]["item"]
    done = next(event["item"] for event in parsed if event["type"] == "response.output_item.done")
    assert done["encrypted_content"] == "SYNTHETIC_OPAQUE_PRESERVE=="
    assert done == parsed[-1]["response"]["output"][0]


def test_annotations_refusal_and_multiple_content_parts_have_correct_indices():
    citation = {
        "type": "url_citation",
        "start_index": 0,
        "end_index": 4,
        "title": "Synthetic source",
        "url": "https://synthetic.invalid/",
    }
    answer = response(
        message(
            content=[
                {"type": "output_text", "text": "text", "annotations": [citation]},
                {"type": "refusal", "refusal": "Synthetic refusal"},
                {"type": "output_text", "text": "", "annotations": []},
            ]
        )
    )
    parsed = events(response_sse(answer))
    reconstruct(parsed, response_json(answer))
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)
    annotations = [
        event for event in parsed if event["type"] == "response.output_text.annotation.added"
    ]
    assert len(annotations) == 1
    assert annotations[0]["annotation"] == citation
    assert annotations[0]["content_index"] == annotations[0]["annotation_index"] == 0


@pytest.mark.parametrize("empty", [False, True])
def test_length_incomplete_text_has_one_incomplete_terminal_and_no_completed_claim(empty):
    answer = response(
        message("" if empty else "Synthetic partial", status="incomplete"),
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        usage=None,
    )
    canonical = response_json(answer)
    parsed = events(response_sse(answer))
    reconstruct(parsed, canonical)
    assert parsed[-1]["type"] == "response.incomplete"
    assert canonical["usage"] is None
    assert not any(event["type"] == "response.completed" for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


@pytest.mark.parametrize("status", ["incomplete", "failed"])
@pytest.mark.parametrize("kind", ["function", "custom", "client-search"])
def test_incomplete_executable_items_and_failed_output_cannot_be_delivered(status, kind):
    item = function()
    if kind == "custom":
        item = {
            "type": "custom_tool_call",
            "id": "ctc_item",
            "call_id": "call_custom",
            "name": "patch",
            "input": RAW,
            "status": "completed",
        }
    elif kind == "client-search":
        item = {
            "type": "tool_search_call",
            "id": "ts_item",
            "call_id": "call_search",
            "execution": "client",
            "arguments": {"query": "read"},
            "status": "completed",
        }
    if status == "incomplete":
        item["status"] = "incomplete"
    changes = {"status": status}
    changes.update(
        {"incomplete_details": {"reason": "max_output_tokens"}}
        if status == "incomplete"
        else {"error": {"code": "server_error", "message": "SYNTHETIC_PRIVATE"}}
    )
    answer = response(item, **changes)
    for encode in (response_json, response_sse):
        with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
            encode(answer)


def test_unknown_and_partial_usage_never_get_fabricated_counts_or_details():
    for usage in (None, {"input_tokens": 19}, {"output_tokens_details": {"reasoning_tokens": 5}}):
        answer = response(message(), usage=usage)
        canonical = response_json(answer)
        assert canonical["usage"] == usage
        parsed = events(response_sse(answer))
        reconstruct(parsed, canonical)
        if usage is not None:
            with pytest.raises(ValidationError):
                SDK_RESPONSE.validate_python(canonical, strict=True)
        else:
            SDK_RESPONSE.validate_python(canonical, strict=True)
    assert response_json(response(message()))["usage"] == USAGE


def test_failed_response_uses_a_safe_error_without_upstream_message_param_or_code_replay():
    answer = response(
        status="failed",
        error={
            "code": "SYNTHETIC_PRIVATE_CODE",
            "message": "SYNTHETIC_PRIVATE_MESSAGE",
            "param": "SYNTHETIC_PRIVATE_PARAM",
        },
    )
    canonical = response_json(answer)
    assert canonical["error"] == {"code": "server_error", "message": "Provider request failed"}
    body = response_sse(answer)
    assert b"SYNTHETIC_PRIVATE" not in body
    parsed = events(body)
    reconstruct(parsed, canonical)
    assert [event["type"] for event in parsed] == [
        "response.created",
        "response.in_progress",
        "response.failed",
    ]
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_hosted_and_client_search_items_are_not_misrepresented_as_function_arguments():
    items = [
        {
            "type": "web_search_call",
            "id": "ws_item",
            "status": "completed",
            "action": {"type": "search", "query": "Synthetic"},
        },
        {
            "type": "tool_search_call",
            "id": "ts_server",
            "call_id": "call_server",
            "execution": "server",
            "status": "completed",
            "arguments": {"query": "read"},
        },
        {
            "type": "tool_search_output",
            "id": "tso_item",
            "call_id": "call_server",
            "execution": "server",
            "status": "completed",
            "tools": [
                {
                    "type": "function",
                    "name": "read",
                    "strict": False,
                    "parameters": {"type": "object"},
                    "defer_loading": True,
                }
            ],
        },
        {
            "type": "tool_search_call",
            "id": "ts_client",
            "call_id": "call_client",
            "execution": "client",
            "status": "completed",
            "arguments": {"query": "other"},
        },
    ]
    answer = response(*items)
    parsed = events(response_sse(answer))
    reconstruct(parsed, response_json(answer))
    assert not any(event["type"].startswith("response.function_call_arguments") for event in parsed)
    assert [
        event["item"] for event in parsed if event["type"] == "response.output_item.done"
    ] == items
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "root-extra",
        "nested-extra",
        "invalid-arguments",
        "incomplete-call",
        "missing-id",
        "duplicate-id",
        "duplicate-call-id",
        "unsafe-id",
        "identity-domains-equal",
    ],
)
def test_mutated_models_fail_before_returning_any_encoded_body(mutation):
    answer = response(function(), function("b"))
    if mutation == "root-extra":
        answer = answer.model_copy(update={"unchecked_upstream": "SYNTHETIC_PRIVATE"})
    elif mutation == "nested-extra":
        answer.output[0] = answer.output[0].model_copy(
            update={"unchecked_upstream": "SYNTHETIC_PRIVATE"}
        )
    else:
        updates = {
            "invalid-arguments": {"arguments": '{"x":NaN}'},
            "incomplete-call": {"status": "incomplete"},
            "missing-id": {"id": None},
            "duplicate-id": {"id": "fc_item_b"},
            "duplicate-call-id": {"call_id": "call_b"},
            "unsafe-id": {"id": "unsafe\nevent: injected"},
            "identity-domains-equal": {"call_id": "fc_item_a"},
        }
        answer.output[0] = answer.output[0].model_copy(update=updates[mutation])
    for encode in (response_json, response_sse):
        with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
            encode(answer)


def test_raw_mappings_are_not_an_encoder_entry_point_and_returned_json_is_detached():
    answer = response(message())
    with pytest.raises(ValueError):
        response_sse(answer.wire_dict())
    encoded = response_json(answer)
    encoded["output"][0]["content"][0]["text"] = "changed"
    assert response_json(answer)["output"][0]["content"][0]["text"] == "Synthetic answer"


def test_missing_echo_fields_do_not_get_invented_to_satisfy_sdk_requirements():
    answer = ResponsesResponse.model_validate(
        {
            "id": "resp_minimal",
            "model": "synthetic-model",
            "created_at": 1,
            "status": "completed",
            "output": [],
        }
    )
    canonical = response_json(answer)
    assert canonical["object"] == "response" and canonical["usage"] is None
    assert not {"tools", "tool_choice", "parallel_tool_calls"} & canonical.keys()
    reconstruct(events(response_sse(answer)), canonical)


def test_legacy_native_reasoning_text_is_preserved_without_forging_sdk_part_types():
    answer = response(reasoning(content=[{"type": "text", "text": "Legacy synthetic reasoning"}]))
    canonical = response_json(answer)
    assert canonical["output"][0]["content"][0]["type"] == "text"
    parsed = events(response_sse(answer))
    reconstruct(parsed, canonical)
    assert not any(event["type"].startswith("response.content_part") for event in parsed)
    with pytest.raises(ValidationError):
        SDK_RESPONSE.validate_python(canonical, strict=True)


@pytest.mark.parametrize("hidden", [False, True])
def test_encoder_revalidation_never_serializes_invalid_usage_or_loses_hidden_actual_state(
    hidden, capfd
):
    sensitive = "SYNTHETIC_PRIVATE_INVALID_USAGE"
    answer = response(message()).model_copy(update={"usage": sensitive})
    if hidden:
        answer.__pydantic_fields_set__.discard("usage")
    for encode in (response_json, response_sse):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
                encode(answer)
        assert recorded == []
    captured = capfd.readouterr()
    assert sensitive not in captured.out + captured.err


def test_failed_hosted_search_retains_fallback_without_a_false_completed_search_event():
    search = {
        "type": "web_search_call",
        "id": "ws_failed",
        "status": "failed",
        "action": {"type": "search", "query": "Synthetic"},
    }
    answer = response(search, message("Synthetic fallback"))
    parsed = events(response_sse(answer))
    reconstruct(parsed, response_json(answer))
    assert not any(event["type"] == "response.web_search_call.completed" for event in parsed)
    assert parsed[-1]["type"] == "response.completed"
    assert parsed[-1]["response"]["output"][0]["status"] == "failed"
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_failed_search_without_an_action_preserves_the_native_sdk_impedance():
    answer = response({"type": "web_search_call", "id": "ws_failed", "status": "failed"}, message())
    canonical = response_json(answer)
    assert "action" not in canonical["output"][0]
    reconstruct(events(response_sse(answer)), canonical)
    with pytest.raises(ValidationError):
        SDK_RESPONSE.validate_python(canonical, strict=True)


def test_completed_call_inside_an_incomplete_response_is_not_repaired_or_reclassified():
    answer = response(
        function(), status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    canonical = response_json(answer)
    parsed = events(response_sse(answer))
    reconstruct(parsed, canonical)
    # Codex executes item-done: the only executable payload here is a complete,
    # syntactically validated call, not a fragment or an invented repair call.
    delivered = [event["item"] for event in parsed if event["type"] == "response.output_item.done"]
    assert len(delivered) == 1 and delivered[0]["status"] == "completed"
    assert json.loads(delivered[0]["arguments"]) == {"path": "данные/🌍.txt"}
    assert parsed[-1]["type"] == "response.incomplete"
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_function_and_custom_argument_fragments_reconstruct_exact_source_strings():
    arguments = json.dumps({"path": "Synthetic" * 400})
    raw = RAW * 80
    custom = {
        "type": "custom_tool_call",
        "id": "ctc_fragmented",
        "call_id": "call_custom",
        "name": "apply_patch",
        "status": "completed",
        "input": raw,
    }
    answer = response(function(arguments=arguments), custom)
    parsed = events(response_sse(answer), 13)
    reconstruct(parsed, response_json(answer))
    for prefix, expected in (
        ("response.function_call_arguments", arguments),
        ("response.custom_tool_call_input", raw),
    ):
        fragments = [event["delta"] for event in parsed if event["type"] == prefix + ".delta"]
        assert len(fragments) > 1 and "".join(fragments) == expected


def test_incomplete_response_does_not_invent_individual_item_completion_states():
    item = message()
    item.pop("status")
    answer = response(item, status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
        response_sse(answer)


def text_delta(text="Synthetic", sequence=5, **changes):
    return ResponsesTextDelta.model_validate(
        {
            "head": ResponsesStreamHead(
                id="resp_synthetic",
                created_at=1800000000.0,
                model="synthetic-model",
                parallel_tool_calls=True,
                tool_choice="auto",
                tools=(),
            ),
            "sequence_number": sequence,
            "item_id": "msg_synthetic",
            "output_index": 0,
            "content_index": 0,
            "phase": "final_answer",
            "delta": text,
            "leading_prefix": True,
            **changes,
        }
    )


def publish(encoder, delta):
    staged = encoder.stage_text(delta)
    assert staged == delta.delta
    return encoder.text(staged)


def sdk_checked_early(body, answer):
    parsed = events(body, 13)
    canonical = response_json(answer)
    reconstruct(parsed, canonical)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)
    SDK_RESPONSE.validate_python(canonical, strict=True)
    return parsed


@pytest.mark.parametrize("phase", [None, "commentary", "final_answer"])
@pytest.mark.parametrize("suffix", ["", " answer"])
def test_early_prefix_and_final_tail_reconstruct_once_with_native_identity(phase, suffix):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn", phase=phase))
    body += publish(encoder, text_delta("thetic", sequence=8, phase=phase))
    early = events(body)
    assert not any(event["type"].endswith(".done") for event in early)
    assert [event["type"] for event in early[:4]] == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
    ]
    assert early[0]["response"]["usage"] is None
    answer = response(message("Synthetic" + suffix, phase=phase))
    body += encoder.complete(answer)
    parsed = sdk_checked_early(body, answer)
    assert sum(event["type"] == "response.output_item.added" for event in parsed) == 1
    assert (
        "".join(event["delta"] for event in parsed if event["type"] == "response.output_text.delta")
        == "Synthetic" + suffix
    )


def test_early_first_index_one_permanently_holds_back_later_zero_without_reordering():
    encoder = EarlyResponsesEncoder()
    assert encoder.stage_text(text_delta("SECOND", output_index=1, item_id="msg_second")) is None
    assert encoder.stage_text(text_delta("FIRST", sequence=9)) is None
    answer = response(message("FIRST"), message("SECOND", id="msg_second"))
    body = encoder.complete(answer)
    assert body == response_sse(answer)
    parsed = sdk_checked_early(body, answer)
    assert [
        event["item"]["id"] for event in parsed if event["type"] == "response.output_item.done"
    ] == ["msg_synthetic", "msg_second"]


@pytest.mark.parametrize("first", ["reasoning", "function", "refusal"])
def test_early_nontext_first_profiles_use_exact_buffered_output(first):
    encoder = EarlyResponsesEncoder()
    if first == "refusal":
        answer = response(
            message(
                content=[
                    {"type": "refusal", "refusal": "Synthetic refusal"},
                    {"type": "output_text", "text": "Synthetic", "annotations": []},
                ]
            )
        )
        delta = text_delta(content_index=1, leading_prefix=False)
    else:
        answer = response(reasoning() if first == "reasoning" else function(), message("Synthetic"))
        delta = text_delta(output_index=1, leading_prefix=False)
    assert encoder.stage_text(delta) is None
    body = encoder.complete(answer)
    assert body == response_sse(answer)
    sdk_checked_early(body, answer)


@pytest.mark.parametrize(
    "boundary", [{"leading_prefix": False}, {"content_index": 1}, {"output_index": 1}]
)
def test_early_window_never_reopens_after_a_held_boundary(boundary):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn"))
    assert encoder.stage_text(text_delta("held", sequence=7, **boundary)) is None
    assert encoder.stage_text(text_delta("thetic", sequence=9)) is None
    answer = response(message("Synthetic"))
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)
    assert b"held" not in body


def test_early_final_mixed_items_parts_annotations_and_tools_keep_canonical_order():
    citation = {
        "type": "url_citation",
        "start_index": 0,
        "end_index": 4,
        "title": "Synthetic source",
        "url": "https://synthetic.invalid/",
    }
    custom = {
        "type": "custom_tool_call",
        "id": "ctc_patch",
        "call_id": "call_patch",
        "name": "apply_patch",
        "namespace": "functions",
        "input": RAW,
        "status": "completed",
    }
    search = {
        "type": "tool_search_call",
        "id": "ts_server",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "arguments": {"query": "read"},
    }
    loaded = {
        "type": "tool_search_output",
        "id": "tso_server",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "tools": [],
    }
    web = {
        "type": "web_search_call",
        "id": "ws_server",
        "status": "completed",
        "action": {"type": "search", "query": "Synthetic"},
    }
    answer = response(
        message(
            content=[
                {"type": "output_text", "text": "Synthetic answer", "annotations": [citation]},
                {"type": "refusal", "refusal": "Synthetic refusal"},
                {"type": "output_text", "text": "SECOND PART", "annotations": []},
            ]
        ),
        reasoning(),
        search,
        loaded,
        function(),
        custom,
        web,
        message("SECOND ITEM", id="msg_second"),
    )
    before = answer.wire_dict()
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Synthetic "))
    assert b"SYNTHETIC_OPAQUE" not in body and b"apply_patch" not in body
    assert not any(event["type"].endswith(".done") for event in events(body))
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)
    assert answer.wire_dict() == before


@pytest.mark.parametrize("field", ["parallel_tool_calls", "tool_choice", "tools"])
def test_early_missing_sdk_required_head_controls_hold_back(field):
    encoder = EarlyResponsesEncoder()
    source = text_delta().head.model_copy(update={field: None})
    assert encoder.stage_text(text_delta(head=source)) is None
    assert encoder.stage_text(text_delta(sequence=7)) is None
    answer = response(message())
    assert encoder.complete(answer) == response_sse(answer)


@pytest.mark.parametrize("choice", ["web_search", "tool_search"])
def test_early_native_named_hosted_choices_are_held_without_inventing_sdk_controls(choice):
    encoder = EarlyResponsesEncoder()
    source = ResponsesStreamHead.model_validate(
        {**text_delta().head.model_dump(), "tool_choice": {"type": choice}}
    )
    assert encoder.stage_text(text_delta(head=source)) is None
    answer = response(message(), tool_choice={"type": choice})
    assert encoder.complete(answer) == response_sse(answer)


@pytest.mark.parametrize("first_too_large", [False, True])
def test_early_prefix_storage_is_bounded_and_overflow_is_final_only(first_too_large):
    encoder = EarlyResponsesEncoder()
    prefix = "x" * MAX_JSON_BYTES
    if first_too_large:
        assert encoder.stage_text(text_delta(prefix + "y")) is None
        body = b""
    else:
        body = publish(encoder, text_delta(prefix))
    assert encoder.stage_text(text_delta("y", sequence=8)) is None
    assert encoder.stage_text(text_delta("z", sequence=10)) is None
    assert encoder._pending is None
    assert len(encoder._prefix) <= MAX_JSON_BYTES
    answer = response(message(prefix + "yz"))
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)


@pytest.mark.parametrize("code", ["policy_denied", "plugin_error", "provider_error", "timeout"])
def test_early_late_error_is_safe_sdk_failed_without_any_executable_completion(code):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    error = GatewayError(code)
    error.message = "SYNTHETIC_PRIVATE"
    body += encoder.error(error)
    parsed = events(body)
    assert parsed[-1]["type"] == "response.failed"
    assert parsed[-1]["response"]["usage"] is None
    assert parsed[-1]["response"]["output"][0]["status"] == "incomplete"
    assert parsed[-1]["response"]["error"] == {
        "code": "server_error",
        "message": GatewayError(code).message,
    }
    assert b"SYNTHETIC_PRIVATE" not in body
    assert not any(event["type"].endswith(".done") for event in parsed)
    assert not any(event["type"] == "response.completed" for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)
    with pytest.raises(ValueError):
        encoder.complete(response(message()))
    with pytest.raises(ValueError):
        encoder.error(GatewayError(code))


@pytest.mark.parametrize(
    "mutation",
    [
        "response-id",
        "model",
        "created-at",
        "parallel",
        "choice",
        "tools",
        "item-id",
        "phase",
        "different-text",
        "shorter-text",
        "empty-output",
        "nontext-first",
    ],
)
def test_early_final_mismatch_fails_before_any_terminal_or_tool_packets(mutation):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    changes = {
        "response-id": {"id": "resp_other"},
        "model": {"model": "other-model"},
        "created-at": {"created_at": 42.0},
        "parallel": {"parallel_tool_calls": False},
        "choice": {"tool_choice": "none"},
        "tools": {"tools": [{"type": "function", "name": "read", "parameters": {}}]},
    }
    item = message()
    if mutation == "item-id":
        item["id"] = "msg_other"
    elif mutation == "phase":
        item["phase"] = "commentary"
    elif mutation == "different-text":
        item = message("Different")
    elif mutation == "shorter-text":
        item = message("Syn")
    output = [item, function()]
    if mutation == "empty-output":
        output = []
    elif mutation == "nontext-first":
        output = [reasoning(), item, function()]
    answer = response(*output, **changes.get(mutation, {}))
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(answer)
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert parsed[-1]["type"] == "response.failed"
    assert not any(event["type"].endswith(".done") for event in parsed)
    assert not any("function_call" in event["type"] for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


@pytest.mark.parametrize("mutation", ["arguments", "usage", "extra", "incomplete-call"])
def test_early_strict_final_validation_is_atomic_even_after_published_text(mutation):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    answer = response(message(), function())
    if mutation == "arguments":
        answer.output[1] = answer.output[1].model_copy(update={"arguments": '{"x":NaN}'})
    elif mutation == "usage":
        answer = answer.model_copy(update={"usage": "SYNTHETIC_PRIVATE"})
    elif mutation == "extra":
        answer = answer.model_copy(update={"unknown": "SYNTHETIC_PRIVATE"})
    else:
        answer.output[1] = answer.output[1].model_copy(update={"status": "incomplete"})
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValueError):
            encoder.complete(answer)
    assert recorded == []
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert not any(event["type"].endswith(".done") for event in parsed)
    assert b"SYNTHETIC_PRIVATE" not in body
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


@pytest.mark.parametrize(
    "mutation", ["mapping", "extra", "head-id", "head-extra", "empty", "boolean-index", "tool"]
)
def test_early_stage_revalidates_forged_record_state_without_serializers(mutation):
    delta = text_delta()
    if mutation == "mapping":
        delta = delta.model_dump()
    elif mutation == "extra":
        delta = delta.model_copy(update={"raw_event": "SYNTHETIC_PRIVATE"})
        delta.__pydantic_fields_set__.discard("raw_event")
    elif mutation == "head-id":
        delta = delta.model_copy(update={"head": delta.head.model_copy(update={"id": "bad\n"})})
    elif mutation == "head-extra":
        source = delta.head.model_copy(update={"snapshot": "SYNTHETIC_PRIVATE"})
        source.__pydantic_fields_set__.discard("snapshot")
        delta = delta.model_copy(update={"head": source})
    elif mutation == "empty":
        delta = delta.model_copy(update={"delta": ""})
    elif mutation == "boolean-index":
        delta = delta.model_copy(update={"output_index": True})
    else:
        tool = FunctionTool(type="function", name="read", parameters={})
        tool = tool.model_copy(update={"parameters": "SYNTHETIC_PRIVATE"})
        tool.__pydantic_fields_set__.discard("parameters")
        delta = delta.model_copy(update={"head": delta.head.model_copy(update={"tools": (tool,)})})
    encoder = EarlyResponsesEncoder()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValueError, match="^Invalid early Responses stream$") as caught:
            encoder.stage_text(delta)
    assert recorded == []
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
    with pytest.raises(ValueError):
        encoder.stage_text(text_delta(sequence=10))


@pytest.mark.parametrize("operation", ["unstaged", "different", "double-stage", "pending-final"])
def test_early_one_staged_record_rejects_callback_mismatches(operation):
    encoder = EarlyResponsesEncoder()
    if operation != "unstaged":
        assert encoder.stage_text(text_delta()) == "Synthetic"
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        if operation == "double-stage":
            encoder.stage_text(text_delta(sequence=8))
        elif operation == "pending-final":
            encoder.complete(response(message()))
        else:
            encoder.text("Synthetic" if operation == "unstaged" else "Different")
    with pytest.raises(ValueError):
        encoder.complete(response(message()))
    # No published response identity means the app must use its ordinary JSON
    # error path, not an invented native failed response or item identifier.
    with pytest.raises(ValueError):
        encoder.error(GatewayError("provider_error"))


@pytest.mark.parametrize("change", ["sequence", "head", "item", "phase"])
def test_early_late_record_identity_or_source_order_mismatch_is_sticky(change):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    changes = {"sequence": 8}
    if change == "sequence":
        changes["sequence"] = 5
    elif change == "head":
        changes["head"] = text_delta().head.model_copy(update={"id": "resp_other"})
    elif change == "item":
        changes["item_id"] = "msg_other"
    else:
        changes["phase"] = "commentary"
    with pytest.raises(ValueError):
        encoder.stage_text(text_delta(**changes))
    with pytest.raises(ValueError):
        encoder.complete(response(message()))
    body += encoder.error(GatewayError("provider_error"))
    for event in events(body):
        SDK_EVENT.validate_python(event, strict=True)


def test_early_staging_detaches_mutable_head_tools_before_text_callback():
    tool = FunctionTool(type="function", name="read", parameters={"type": "object"})
    source = text_delta().head.model_copy(update={"tools": (tool,)})
    delta = text_delta(head=source)
    encoder = EarlyResponsesEncoder()
    assert encoder.stage_text(delta) == "Synthetic"
    delta.head.tools[0].parameters["type"] = "SYNTHETIC_PRIVATE"
    body = encoder.text("Synthetic")
    answer = response(
        message(), tools=[{"type": "function", "name": "read", "parameters": {"type": "object"}}]
    )
    body += encoder.complete(answer)
    assert b"SYNTHETIC_PRIVATE" not in body
    sdk_checked_early(body, answer)


def test_early_incomplete_final_preserves_partial_text_and_one_incomplete_terminal():
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Synthetic "))
    answer = response(
        message("Synthetic partial", status="incomplete"),
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        usage=None,
    )
    body += encoder.complete(answer)
    parsed = sdk_checked_early(body, answer)
    assert parsed[-1]["type"] == "response.incomplete"
    assert not any(event["type"] == "response.completed" for event in parsed)


def test_early_without_published_text_uses_buffered_bytes_and_cannot_complete_twice():
    encoder = EarlyResponsesEncoder()
    answer = response(function(), message())
    assert encoder.complete(answer) == response_sse(answer)
    with pytest.raises(ValueError):
        encoder.complete(answer)


def test_early_text_record_is_consumed_once_and_failed_text_cannot_complete():
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    with pytest.raises(ValueError):
        encoder.text("Synthetic")
    with pytest.raises(ValueError):
        encoder.complete(response(message()))
    body += encoder.error(GatewayError("provider_error"))
    assert events(body)[-1]["type"] == "response.failed"


@pytest.mark.parametrize("closed", [False, True])
def test_early_changed_head_cannot_hide_behind_holdback_or_missing_controls(closed):
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta())
    if closed:
        assert encoder.stage_text(text_delta(sequence=7, leading_prefix=False)) is None
    changed = text_delta().head.model_copy(update={"tools": None})
    with pytest.raises(ValueError):
        encoder.stage_text(text_delta(sequence=9, head=changed))
    body += encoder.error(GatewayError("provider_error"))
    for event in events(body):
        SDK_EVENT.validate_python(event, strict=True)


def test_early_unicode_and_lone_surrogates_reconcile_without_sse_injection():
    text = "Synthetic 🌍\ud800\nevent: injected\ndata: not-an-event [DONE]" * 30
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta(text[:1300]))
    body += publish(encoder, text_delta(text[1300:1600], sequence=9))
    answer = response(message(text))
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)
    assert b"\\ud800" in body and b"\\n" in body


def test_early_sdk_ready_namespace_head_matches_final_echo_without_mutating_sources():
    tools = [
        {
            "type": "namespace",
            "name": "alpha",
            "description": "Synthetic namespace",
            "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
        }
    ]
    source = ResponsesStreamHead.model_validate(
        {
            **text_delta().head.model_dump(),
            "tools": tuple(tools),
            "tool_choice": {"type": "function", "name": "read", "namespace": "alpha"},
        }
    )
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta(head=source))
    answer = response(message(), function(), tools=tools, tool_choice=source.tool_choice)
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)


def test_early_later_head_rejects_boolean_to_number_schema_change_before_new_bytes():
    source = ResponsesStreamHead.model_validate(
        {
            **text_delta().head.model_dump(),
            "tools": ({"type": "function", "name": "read", "parameters": {"const": True}},),
        }
    )
    changed = ResponsesStreamHead.model_validate(
        {
            **source.model_dump(),
            "tools": ({"type": "function", "name": "read", "parameters": {"const": 1}},),
        }
    )
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn", head=source))
    sequence = encoder._sequence
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.stage_text(text_delta("thetic answer", sequence=8, head=changed))
    assert encoder._sequence == sequence
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(
            response(message(), function(namespace=None), tools=source.wire_dict()["tools"])
        )
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert [event["type"] for event in parsed[sequence:]] == ["response.failed"]
    assert not any(event["type"].endswith(".done") for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_early_final_rejects_boolean_to_number_schema_change_before_tool_or_terminal_bytes():
    source = ResponsesStreamHead.model_validate(
        {
            **text_delta().head.model_dump(),
            "tools": ({"type": "function", "name": "read", "parameters": {"const": True}},),
        }
    )
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn", head=source))
    sequence = encoder._sequence
    answer = response(
        message(),
        function(namespace=None),
        tools=[{"type": "function", "name": "read", "parameters": {"const": 1}}],
    )
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(answer)
    assert encoder._sequence == sequence
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert [event["type"] for event in parsed[sequence:]] == ["response.failed"]
    assert not any(event["type"].endswith(".done") for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_early_head_and_final_allow_reordered_schema_keys_without_changing_json_types():
    parameters = {
        "type": "object",
        "properties": {"flag": {"type": "boolean", "const": True}},
    }
    reordered = {
        "properties": {"flag": {"const": True, "type": "boolean"}},
        "type": "object",
    }
    source = ResponsesStreamHead.model_validate(
        {
            **text_delta().head.model_dump(),
            "tools": ({"type": "function", "name": "read", "parameters": parameters},),
        }
    )
    later = ResponsesStreamHead.model_validate(
        {
            **source.model_dump(),
            "tools": ({"type": "function", "name": "read", "parameters": reordered},),
        }
    )
    assert list(source.tools[0].parameters) != list(later.tools[0].parameters)
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn", head=source))
    body += publish(encoder, text_delta("thetic", sequence=8, head=later))
    answer = response(
        message(),
        function(namespace=None),
        tools=[{"type": "function", "name": "read", "parameters": parameters}],
    )
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)


def known_probability_answer(*, text="Synthetic", statistics=True, **changes):
    probability = {
        "token": "Synthetic",
        "bytes": [83],
        "logprob": -0.5,
        "top_logprobs": [{"token": "Other", "bytes": [79], "logprob": -1.0}],
    }
    return response(
        message(
            content=[
                {
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                    "logprobs": [probability] if statistics is True else statistics,
                }
            ]
        ),
        max_tool_calls=None,
        prompt_cache_retention="in_memory",
        safety_identifier="",
        top_logprobs=1,
        user=None,
        **changes,
    )


@pytest.mark.parametrize("statistics", [None, [], True])
def test_known_subset_probability_json_sse_equivalence_and_sdk_projection(statistics):
    from gateway7.responses_stream import ResponsesStream

    answer = known_probability_answer(statistics=statistics)
    canonical = response_json(answer)
    body = response_sse(answer)
    parsed = sdk_checked_early(body, answer)
    source = canonical["output"][0]["content"][0]["logprobs"]
    if statistics is True:
        deltas = [event for event in parsed if event["type"] == "response.output_text.delta"]
        assert len(deltas) == 1
        assert deltas[0]["delta"] == canonical["output"][0]["content"][0]["text"]
        projected = deltas[0]["logprobs"]
        assert projected == [
            {
                "token": "Synthetic",
                "logprob": -0.5,
                "top_logprobs": [{"token": "Other", "logprob": -1.0}],
            }
        ]
        assert "bytes" not in projected[0] and "bytes" not in projected[0]["top_logprobs"][0]
        assert (
            next(event for event in parsed if event["type"] == "response.output_text.done")[
                "logprobs"
            ]
            == projected
        )
        added = next(event for event in parsed if event["type"] == "response.content_part.added")
        assert added["part"]["logprobs"] == []
        assert source[0]["bytes"] == [83]
    stream = ResponsesStream()
    stream.feed(body)
    assert stream.finish() == canonical


def test_known_subset_late_probability_metadata_after_early_prefix_fails_safely():
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn"))
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(known_probability_answer())
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert parsed[-1]["type"] == "response.failed"
    assert not any(event["type"].endswith(".done") for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


def test_known_subset_nonempty_probability_event_size_is_preflighted_before_returning_bytes():
    from gateway7.responses_stream import MAX_EVENT_BYTES

    answer = known_probability_answer(text="x" * MAX_EVENT_BYTES)
    with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
        response_sse(answer)


def test_known_subset_later_part_statistics_remain_ordered_after_metadata_free_early_prefix():
    from gateway7.responses_stream import ResponsesStream

    probability_part = known_probability_answer().wire_dict()["output"][0]["content"][0]
    first = {"type": "output_text", "text": "Synthetic answer", "annotations": []}
    answer = response(message(content=[first, probability_part]), function())
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn"))
    body += encoder.complete(answer)
    sdk_checked_early(body, answer)
    stream = ResponsesStream()
    stream.feed(body)
    assert stream.finish() == response_json(answer)


def test_known_subset_encoder_revalidates_forged_probability_before_any_serialization():
    answer = known_probability_answer()
    part = answer.output[0].content[0]
    invalid = part.logprobs[0].model_copy(update={"logprob": "SYNTHETIC_PRIVATE"})
    invalid.__pydantic_fields_set__.discard("logprob")
    part.logprobs[0] = invalid
    for encode in (response_json, response_sse):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
                encode(answer)
        assert recorded == []


def bounded_utf8_compatibility_answer(mode):
    from gateway7.responses_stream import MAX_EVENT_BYTES, MAX_RESPONSE_BYTES, ResponsesStream

    unicode_text = "🌍" * 6000
    text = "Synthetic answer" if mode == "user" else unicode_text
    source_events = events(response_sse(response(message(text))))
    for event in source_events:
        if mode == "user":
            if "response" in event:
                event["response"]["user"] = unicode_text
            continue
        statistics = None if mode == "null-logprobs" else []
        parts = []
        if "part" in event:
            parts.append(event["part"])
        if "item" in event:
            parts.extend(event["item"].get("content", []))
        if "response" in event:
            for item in event["response"]["output"]:
                parts.extend(item.get("content", []))
        for part in parts:
            part["logprobs"] = statistics
    frames = [
        (
            "event: "
            + event["type"]
            + "\ndata: "
            + json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            + "\n\n"
        ).encode("utf-8")
        for event in source_events
    ]
    assert max(map(len, frames)) < MAX_EVENT_BYTES
    source = b"".join(frames)
    assert len(source) < MAX_RESPONSE_BYTES
    stream = ResponsesStream()
    stream.feed(source)
    answer = ResponsesResponse.model_validate(stream.finish())
    terminal = {
        "type": "response.completed",
        "sequence_number": 99,
        "response": response_json(answer),
    }
    assert len(json.dumps(terminal, ensure_ascii=True).encode("ascii")) > MAX_EVENT_BYTES
    return answer


@pytest.mark.parametrize("mode", ["user", "null-logprobs", "empty-logprobs"])
def test_p2_unicode_expansion_is_preflighted_before_buffered_output(mode):
    answer = bounded_utf8_compatibility_answer(mode)
    with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
        response_sse(answer)


@pytest.mark.parametrize("mode", ["user", "null-logprobs", "empty-logprobs"])
def test_p2_unicode_expansion_after_published_prefix_fails_without_terminal_success(mode):
    answer = bounded_utf8_compatibility_answer(mode)
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn" if mode == "user" else "🌍"))
    sequence = encoder._sequence
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(answer)
    assert encoder._sequence == sequence
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert [event["type"] for event in parsed[sequence:]] == ["response.failed"]
    assert not any(event["type"].endswith(".done") for event in parsed)
    for event in parsed:
        SDK_EVENT.validate_python(event, strict=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_tool_calls", None),
        ("max_tool_calls", 0),
        ("prompt_cache_retention", None),
        ("prompt_cache_retention", "in_memory"),
        ("safety_identifier", None),
        ("safety_identifier", ""),
        ("top_logprobs", None),
        ("top_logprobs", 0),
        ("user", None),
        ("user", ""),
    ],
)
def test_p2_each_approved_root_echo_activates_preflight_by_presence(field, value):
    from gateway7.responses_api import _needs_compatibility_preflight

    canonical = response_json(response(message(), **{field: value}))
    assert field in canonical
    assert _needs_compatibility_preflight(canonical)


@pytest.mark.parametrize("presence", ["omitted", "null", "empty", "nonempty"])
def test_p2_part_statistics_presence_not_truthiness_selects_preflight(presence):
    from gateway7.responses_api import _needs_compatibility_preflight

    part = {"type": "output_text", "text": "Synthetic", "annotations": []}
    if presence != "omitted":
        statistics = known_probability_answer().wire_dict()["output"][0]["content"][0]["logprobs"]
        part["logprobs"] = {"null": None, "empty": [], "nonempty": statistics}[presence]
    canonical = response_json(response(message(content=[part])))
    assert (
        not {
            "max_tool_calls",
            "prompt_cache_retention",
            "safety_identifier",
            "top_logprobs",
            "user",
        }
        & canonical.keys()
    )
    assert _needs_compatibility_preflight(canonical) is (presence != "omitted")


def test_p2_early_compatibility_body_preflight_includes_already_published_bytes(monkeypatch):
    import gateway7.responses_api as api

    answer = response(message(), user="")
    reference = EarlyResponsesEncoder()
    published = publish(reference, text_delta("Syn"))
    tail = reference.complete(answer)
    assert published and tail
    monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", len(tail))
    encoder = EarlyResponsesEncoder()
    body = publish(encoder, text_delta("Syn"))
    with pytest.raises(ValueError, match="^Invalid early Responses stream$"):
        encoder.complete(answer)
    body += encoder.error(GatewayError("provider_error"))
    parsed = events(body)
    assert parsed[-1]["type"] == "response.failed"
    assert not any(event["type"].endswith(".done") for event in parsed)

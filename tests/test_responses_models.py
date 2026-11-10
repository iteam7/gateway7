"""Native Responses contracts preserve Codex data and reject unsafe narrowing."""

from copy import deepcopy
from functools import partial
import json
import warnings

import pytest
from pydantic import ValidationError

from gateway7.responses_models import (
    ResponsesConsent,
    ResponsesCreateRequest,
    ResponsesRequest,
    ResponsesResponse,
    validate_request,
    validate_response,
)


OPAQUE = ResponsesConsent(allow_opaque=True)
ALL = ResponsesConsent(allow_opaque=True, allow_hosted=True)
SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}
FUNCTION = {"type": "function", "name": "read", "parameters": SCHEMA, "strict": True}
CUSTOM = {
    "type": "custom",
    "name": "apply_patch",
    "description": "Synthetic patch tool",
    "format": {"type": "grammar", "syntax": "lark", "definition": "start: /.+/"},
}
RAW = "*** Begin Patch\n*** Add File: synthetic.txt\n+Synthetic\n*** End Patch\n"


def request(**changes):
    return {
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
        **changes,
    }


def parse(consent=ResponsesConsent(), **changes):
    return ResponsesRequest.model_validate(request(**changes), context={"consent": consent})


def call(suffix="a", *, namespace=None, custom=False, **changes):
    value = {
        "type": "custom_tool_call" if custom else "function_call",
        "id": "item_" + suffix,
        "call_id": "call_" + suffix,
        "name": "apply_patch" if custom else "read",
        "input" if custom else "arguments": RAW if custom else ' {"path": "a.txt"} ',
        "status": "completed",
    }
    if namespace is not None:
        value["namespace"] = namespace
    return {**value, **changes}


def result(suffix="a", *, custom=False, **changes):
    return {
        "type": "custom_tool_call_output" if custom else "function_call_output",
        "call_id": "call_" + suffix,
        "output": "synthetic result",
        **changes,
    }


def response(*output, **changes):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_synthetic",
            "object": "response",
            "created_at": 1800000000,
            "model": "synthetic-model",
            "status": "completed",
            "output": list(output),
            **changes,
        }
    )


@pytest.mark.parametrize("namespace", [False, True])
def test_nullable_response_tool_echoes_preserve_presence_without_request_or_history_expansion(
    namespace,
):
    from gateway7.responses_models import FunctionTool, NamespaceTool, ToolSearchOutputItem

    legacy = {**FUNCTION, "description": "Synthetic retained description"}

    def wrap(leaf):
        return (
            [{"type": "namespace", "name": "alpha", "description": "Synthetic", "tools": [leaf]}]
            if namespace
            else [leaf]
        )

    legacy_tools = wrap(deepcopy(legacy))
    choice = {"type": "function", "name": "read", **({"namespace": "alpha"} if namespace else {})}
    core = parse(tools=legacy_tools, tool_choice=choice, parallel_tool_calls=False)
    before = deepcopy(core.wire_dict())
    fields = ("allowed_callers", "async", "output_schema")
    for mask in range(8):
        leaf = {
            **deepcopy(legacy),
            **{name: None for i, name in enumerate(fields) if mask & (1 << i)},
        }
        tools = wrap(leaf)
        answer = response(
            call(namespace="alpha" if namespace else None),
            tools=tools,
            tool_choice=choice,
            parallel_tool_calls=False,
        )
        checked = validate_response(core, answer)
        assert checked.wire_dict()["tools"] == tools and core.wire_dict() == before
        if mask:
            with pytest.raises(ValidationError):
                parse(tools=tools)
            with pytest.raises(ValidationError):
                ToolSearchOutputItem.model_validate(
                    {
                        "type": "tool_search_output",
                        "execution": "client",
                        "id": "ts_synthetic",
                        "call_id": "call_synthetic",
                        "status": "completed",
                        "tools": tools,
                    }
                )
    typed = (
        NamespaceTool.model_validate(legacy_tools[0])
        if namespace
        else FunctionTool.model_validate(legacy)
    )
    assert response(tools=[typed]).wire_dict()["tools"] == legacy_tools


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed_callers", ["direct"]),
        ("async", False),
        ("output_schema", {"SYNTHETIC_PRIVATE_KEY": "SYNTHETIC_PRIVATE_VALUE"}),
    ],
)
def test_nullable_response_tool_echoes_reject_nonnull_and_forged_state(
    field, value, caplog, capsys
):
    from gateway7.responses_api import response_json
    from gateway7.responses_events import ResponsesStreamHead

    leaf = {**FUNCTION, field: value}
    with pytest.raises(ValidationError) as caught:
        response(tools=[leaf])
    assert "SYNTHETIC_PRIVATE_VALUE" not in str(caught.value)
    with pytest.raises(ValidationError):
        ResponsesStreamHead.model_validate(
            {
                "id": "resp_synthetic",
                "created_at": 1.0,
                "model": "synthetic-model",
                "tools": (leaf,),
            }
        )
    answer = response(tools=[{**FUNCTION, field: None}])
    python_field = "async_" if field == "async" else field
    answer.tools[0] = answer.tools[0].model_copy(update={python_field: value})
    answer.tools[0].__pydantic_fields_set__.discard(python_field)
    with pytest.raises(ValidationError):
        validate_response(parse(tools=[FUNCTION]), answer)
    with pytest.raises(ValueError, match="^Invalid checked Responses response$"):
        response_json(answer)
    captured = capsys.readouterr()
    assert "SYNTHETIC_PRIVATE_VALUE" not in caplog.text + captured.out + captured.err


def test_nullable_response_tool_echoes_keep_plaintext_inspection_and_presence_protection():
    from gateway7.plugin_api import Deny
    from gateway7.responses_policy import apply_policy, protected_snapshot

    leaf = {
        **FUNCTION,
        "description": "SYNTHETIC_DESC_CANARY",
        "parameters": {"SYNTHETIC_KEY_CANARY": "SYNTHETIC_VALUE_CANARY"},
        "allowed_callers": None,
        "async": None,
        "output_schema": None,
    }
    answer = response(tools=[leaf])
    before = deepcopy(answer.wire_dict())
    seen = []

    def inspect(text):
        seen.append(text)
        return text, int("CANARY" in text)

    result, matches = apply_policy(answer, inspect, action="block")
    assert isinstance(result, Deny) and matches == 3
    assert {"SYNTHETIC_DESC_CANARY", "SYNTHETIC_KEY_CANARY", "SYNTHETIC_VALUE_CANARY"} <= set(seen)
    changed = answer.model_copy(deep=True)
    changed.tools[0].__pydantic_fields_set__.discard("async_")
    assert protected_snapshot(changed) != protected_snapshot(answer)
    assert answer.wire_dict() == before


def test_transport_authority_is_absent_from_core_and_consents_are_external():
    dto = ResponsesCreateRequest.model_validate(
        {"model": "synthetic-model", "stream": True, **request()}
    )
    core = dto.core_request()
    assert type(core) is ResponsesRequest
    assert core.max_output_tokens == 1024
    assert (
        not {"model", "stream", "consent", "allow_opaque", "allow_hosted"}
        & core.model_dump().keys()
    )
    assert dto.model == "synthetic-model" and dto.stream is True
    assert "max_output_tokens" in core.wire_dict()
    with pytest.raises(ValidationError):
        OPAQUE.allow_opaque = False
    for authority in ("model", "stream", "allow_opaque", "allow_hosted", "consent"):
        with pytest.raises((ValueError, ValidationError)):
            validate_request(core.model_copy(update={authority: "injected"}))


@pytest.mark.parametrize("value", [0, -1, 4097, True, 1.0, "2", None])
def test_token_limit_rejects_coercion_and_bounds(value):
    with pytest.raises(ValidationError):
        parse(max_output_tokens=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stream", 1),
        ("store", True),
        ("store", 0),
        ("store", None),
        ("parallel_tool_calls", 1),
        ("previous_response_id", "resp_old"),
        ("conversation", "conv_old"),
        ("background", False),
        ("generate", True),
        ("type", "response.create"),
        ("access_programs", {"cyber": "standard"}),
        ("functions", []),
        ("messages", []),
        ("arbitrary_private_extension", "SYNTHETIC"),
    ],
)
def test_unsupported_or_invalid_transport_controls_are_closed(field, value):
    with pytest.raises(ValidationError):
        ResponsesCreateRequest.model_validate(
            {"model": "synthetic-model", **request(), field: value}
        )


def test_parallel_namespace_calls_results_and_raw_arguments_preserve_native_order():
    tools = [
        {"type": "namespace", "name": ns, "description": "Synthetic tools", "tools": [FUNCTION]}
        for ns in ("alpha", "beta")
    ]
    history = [call("a", namespace="alpha"), call("b", namespace="beta"), result("b"), result("a")]
    original = request(input=history, tools=tools, parallel_tool_calls=True)
    before = deepcopy(original)
    core = ResponsesRequest.model_validate(original)
    assert core.wire_dict()["input"] == history
    assert core.wire_dict()["tools"] == tools and original == before
    validated = validate_response(
        core, response(call("c", namespace="alpha"), call("d", namespace="beta"))
    )
    assert [item.call_id for item in validated.output] == ["call_c", "call_d"]


@pytest.mark.parametrize(
    "history",
    [
        [result()],
        [call(), result(call_id="item_a")],
        [call(), result(custom=True)],
        [call(), result(name="other")],
        [call(namespace="alpha"), result(namespace="beta")],
        [call(), result(), result()],
        [call(), result(), call(), result()],
        [call()],
        [call(), call("b", id="item_a"), result(), result("b")],
    ],
)
def test_history_rejects_orphans_duplicates_wrong_kind_and_wrong_identity(history):
    with pytest.raises(ValidationError):
        parse(input=history, tools=[FUNCTION])


def test_custom_lark_and_raw_input_are_never_function_json():
    core = parse(input=[call(custom=True), result(custom=True)], tools=[CUSTOM])
    assert core.wire_dict()["input"][0]["input"] == RAW
    assert core.wire_dict()["tools"][0] == CUSTOM
    assert validate_response(core, response(call("b", custom=True))).output[0].input == RAW


@pytest.mark.parametrize(
    "arguments",
    [
        "[]",
        "null",
        '"scalar"',
        '{"path":',
        '{"x":1,"x":2}',
        '{"n":NaN}',
        '{"n":Infinity}',
        '{"x":' * 66 + "{}" + "}" * 66,
        '{"path":"' + "x" * 65536 + '"}',
    ],
)
def test_function_arguments_are_strict_bounded_json_without_rewriting(arguments):
    with pytest.raises(ValidationError):
        parse(input=[call(arguments=arguments), result()])
    with pytest.raises(ValidationError):
        response(call(arguments=arguments))


def test_reasoning_and_message_phase_preserve_plaintext_and_opaque_values():
    history = [
        {
            "type": "reasoning",
            "id": "rs_history",
            "summary": [{"type": "summary_text", "text": "Synthetic summary"}],
            "content": [{"type": "reasoning_text", "text": "Synthetic reasoning"}],
            "encrypted_content": "SYNTHETIC_OPAQUE==",
        },
        {
            "type": "message",
            "id": "msg_history",
            "role": "assistant",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "Synthetic preamble", "annotations": []}],
        },
    ]
    with pytest.raises(ValidationError):
        parse(input=history)
    core = parse(OPAQUE, input=history, include=["reasoning.encrypted_content"])
    assert core.wire_dict()["input"] == history
    assert validate_request(core, consent=OPAQUE).wire_dict() == core.wire_dict()
    with pytest.raises((ValueError, ValidationError)):
        validate_request(core)


@pytest.mark.parametrize(
    "changes",
    [
        {"include": ["reasoning.encrypted_content"]},
        {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": "data:image/png;base64,aGVsbG8="}
                    ],
                }
            ]
        },
        {
            "input": [
                call(),
                result(output=[{"type": "encrypted_content", "encrypted_content": "SYNTHETIC"}]),
            ]
        },
    ],
)
def test_opaque_data_requires_out_of_payload_consent(changes):
    with pytest.raises(ValidationError):
        parse(**changes)
    assert parse(OPAQUE, **changes)


def test_structured_results_keep_adjacent_text_and_bound_media_without_fetching():
    output = [
        {"type": "input_text", "text": "Synthetic private adjacent text"},
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,aGVsbG8=",
            "detail": "original",
        },
    ]
    for custom in (False, True):
        core = parse(OPAQUE, input=[call(custom=custom), result(custom=custom, output=output)])
        assert core.wire_dict()["input"][1]["output"] == output
    for url in (
        "data:image/png;base64,%%%",
        "data:text/plain;base64,aGVsbG8=",
        "file:///private/image.png",
    ):
        with pytest.raises(ValidationError):
            parse(
                OPAQUE, input=[call(), result(output=[{"type": "input_image", "image_url": url}])]
            )


def test_client_tool_search_definitions_results_and_loaded_namespace_are_typed():
    search = {
        "type": "tool_search",
        "execution": "client",
        "description": "Find synthetic tools",
        "parameters": SCHEMA,
    }
    loaded = [
        {
            "type": "namespace",
            "name": "alpha",
            "description": "Loaded tools",
            "tools": [{**FUNCTION, "defer_loading": True}],
        }
    ]
    history = [
        {
            "type": "tool_search_call",
            "id": "ts_history",
            "call_id": "call_search",
            "execution": "client",
            "status": "completed",
            "arguments": {"path": "read"},
        },
        {
            "type": "tool_search_output",
            "call_id": "call_search",
            "execution": "client",
            "status": "completed",
            "tools": loaded,
        },
    ]
    core = parse(input=history, tools=[search])
    assert core.wire_dict()["input"] == history
    validate_response(core, response(call("loaded", namespace="alpha")))
    for update in ({"execution": "server"}, {"call_id": "wrong"}, {"tools": [{"type": "unknown"}]}):
        with pytest.raises(ValidationError):
            parse(input=[history[0], {**history[1], **update}], tools=[search])


@pytest.mark.parametrize(
    "tool", [{"type": "web_search"}, {"type": "tool_search", "execution": "server"}]
)
def test_hosted_tools_are_explicit_and_not_confused_with_client_tool_search(tool):
    with pytest.raises(ValidationError):
        parse(tools=[tool])
    assert parse(ALL, tools=[tool])
    assert parse(tools=[{"type": "tool_search", "execution": "client"}])


def test_native_controls_schema_and_large_core_client_metadata_are_preserved():
    controls = {
        "max_output_tokens": 4096,
        "reasoning": {"effort": "xhigh", "summary": "auto", "context": "all_turns"},
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "codex_output_schema",
                "strict": True,
                "schema": SCHEMA,
            },
        },
        "prompt_cache_key": "synthetic-cache",
        "client_metadata": {
            "x-codex-turn-metadata": "x" * 1024,
            **{f"key_{i}": "v" for i in range(20)},
        },
        "stream_options": {"reasoning_summary_delivery": "sequential_cutoff"},
    }
    core = parse(**controls)
    assert all(core.wire_dict()[key] == value for key, value in controls.items())
    for schema in ({"value": float("nan")}, {"value": object()}):
        with pytest.raises(ValidationError):
            parse(tools=[{**FUNCTION, "parameters": schema}])


@pytest.mark.parametrize(
    "change",
    [
        {"name": "other"},
        {"namespace": "missing"},
        {"call_id": "call_a"},
        {"id": "item_a"},
        {"type": "custom_tool_call", "input": RAW, "arguments": None},
        {"status": "incomplete"},
    ],
)
def test_response_checks_advertisement_history_reuse_and_executable_completion(change):
    core = parse(input=[call(), result()], tools=[FUNCTION])
    with pytest.raises((ValueError, ValidationError)):
        validate_response(core, response(call("b", **change)))


def test_response_rejects_ambiguous_missing_namespace_disabled_parallel_and_tool_choices():
    tools = [
        {"type": "namespace", "name": ns, "description": "Tools", "tools": [FUNCTION]}
        for ns in ("alpha", "beta")
    ]
    with pytest.raises(ValueError):
        validate_response(parse(tools=tools), response(call()))
    with pytest.raises(ValueError):
        validate_response(
            parse(tools=[FUNCTION], parallel_tool_calls=False), response(call(), call("b"))
        )
    with pytest.raises(ValueError):
        validate_response(parse(tools=[FUNCTION], tool_choice="none"), response(call()))
    with pytest.raises(ValueError):
        validate_response(parse(tools=[FUNCTION], tool_choice="required"), response())
    with pytest.raises(ValidationError):
        parse(tools=[FUNCTION], tool_choice={"type": "function", "name": "missing"})


def test_incomplete_empty_text_preserves_truthful_partial_usage_without_zeroes():
    core = parse()
    answer = response(
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        usage={"input_tokens": 19},
    )
    checked = validate_response(core, answer)
    assert checked.wire_dict()["usage"] == {"input_tokens": 19}
    assert checked.accounting_usage() == {"input_tokens": 19}
    assert response().usage is None
    source_usage = {
        "input_tokens": 19,
        "input_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 3},
        "output_tokens": 11,
        "output_tokens_details": {"reasoning_tokens": 5},
        "total_tokens": 30,
    }
    complete = response(usage=source_usage)
    assert complete.wire_dict()["usage"] == source_usage
    assert complete.accounting_usage() == {"input_tokens": 19, "output_tokens": 11}


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True},
        {"output_tokens": -1},
        {"input_tokens": 2**63},
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 9},
        {"input_tokens": 1, "input_tokens_details": {"cached_tokens": 2}},
        {"output_tokens": 1, "output_tokens_details": {"reasoning_tokens": 2}},
        {"unknown_count": 1},
    ],
)
def test_reported_usage_is_strict_bounded_and_consistent(usage):
    with pytest.raises(ValidationError):
        response(usage=usage)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "in_progress"},
        {"status": "completed", "incomplete_details": {"reason": "max_output_tokens"}},
        {"status": "incomplete"},
        {"status": "failed"},
        {"output": [{"type": "unknown"}]},
    ],
)
def test_terminal_response_shape_rejects_unknown_or_inconsistent_states(changes):
    with pytest.raises(ValidationError):
        response(**changes)


def test_unknown_nested_fields_and_nonassistant_output_are_rejected():
    for changes in (
        {"tools": [{**FUNCTION, "unknown": "private"}]},
        {
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello", "unknown": "private"}],
                }
            ]
        },
        {"reasoning": {"unknown": "private"}},
    ):
        with pytest.raises(ValidationError):
            parse(**changes)
    with pytest.raises((ValueError, ValidationError)):
        validate_response(
            parse(), response({"type": "message", "role": "user", "content": "wrong role"})
        )


def test_model_validation_rechecks_mutable_children_and_never_mutates_originals():
    original = request(tools=[deepcopy(FUNCTION)])
    before = deepcopy(original)
    core = ResponsesRequest.model_validate(original)
    assert json.loads(core.model_dump_json())["tools"][0]["parameters"] == SCHEMA
    core.tools[0].parameters["injected"] = float("nan")
    with pytest.raises((ValueError, ValidationError)):
        validate_request(core)
    assert original == before


def test_revalidation_does_not_normalize_away_an_invalid_storage_edit():
    with pytest.raises((ValueError, ValidationError)):
        validate_request(parse().model_copy(update={"store": True}))


@pytest.mark.parametrize("value", [True, 0, 1])
@pytest.mark.parametrize("field", ["store", "background"])
def test_response_echo_cannot_enable_state_or_coerce_literal_booleans(field, value):
    with pytest.raises(ValidationError):
        response(**{field: value})


def test_completed_response_cannot_contain_incomplete_text():
    item = {
        "type": "message",
        "id": "msg_new",
        "role": "assistant",
        "status": "incomplete",
        "content": [{"type": "output_text", "text": "partial", "annotations": []}],
    }
    with pytest.raises(ValueError):
        validate_response(parse(), response(item))


def test_named_builtin_choice_does_not_authorize_a_different_tool_family():
    core = parse(ALL, tools=[FUNCTION, {"type": "web_search"}], tool_choice={"type": "web_search"})
    with pytest.raises(ValueError):
        validate_response(core, response(call()), consent=ALL)


@pytest.mark.parametrize("parallel", [False, True])
def test_server_tool_search_can_load_typed_tools_only_after_a_correlated_result(parallel):
    core = parse(
        ALL, tools=[{"type": "tool_search", "execution": "server"}], parallel_tool_calls=parallel
    )
    search = {
        "type": "tool_search_call",
        "id": "ts_new",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "arguments": {"query": "read"},
    }
    loaded = {
        "type": "tool_search_output",
        "id": "tso_new",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "tools": [FUNCTION],
    }
    assert validate_response(core, response(search, loaded, call()), consent=ALL)
    for output in (
        (loaded, call()),
        (search, call()),
        (search, {**loaded, "execution": "client"}, call()),
    ):
        with pytest.raises(ValueError):
            validate_response(core, response(*output), consent=ALL)


@pytest.mark.parametrize("item_status", [{}, {"status": None}], ids=["omitted", "null"])
@pytest.mark.parametrize("enclosing_status", ["completed", "incomplete"])
@pytest.mark.parametrize("with_result", [False, True])
def test_server_search_implicit_completion_depends_on_the_enclosing_response(
    item_status, enclosing_status, with_result
):
    core = parse(
        ALL,
        tools=[{"type": "tool_search", "execution": "server"}],
        parallel_tool_calls=False,
    )
    search = {
        "type": "tool_search_call",
        "id": "ts_new",
        "call_id": "call_search",
        "execution": "server",
        "arguments": {"query": "read"},
        **item_status,
    }
    output = [search]
    if with_result:
        output.extend(
            [
                {
                    "type": "tool_search_output",
                    "id": "tso_new",
                    "call_id": "call_search",
                    "execution": "server",
                    "status": "completed",
                    "tools": [FUNCTION],
                },
                call(),
            ]
        )
    details = (
        {"incomplete_details": {"reason": "max_output_tokens"}}
        if enclosing_status == "incomplete"
        else {}
    )
    answer = response(*output, status=enclosing_status, **details)
    before = answer.wire_dict()
    if enclosing_status == "completed" and not with_result:
        with pytest.raises(ValueError, match="^Server tool search omitted its typed result$"):
            validate_response(core, answer, consent=ALL)
    elif enclosing_status == "incomplete" and with_result:
        with pytest.raises(
            ValueError, match="^Provider search output must follow its server-executed call$"
        ):
            validate_response(core, answer, consent=ALL)
    else:
        checked = validate_response(core, answer, consent=ALL)
        assert checked.wire_dict() == before
        assert checked.wire_dict()["output"] == output
        assert checked.output[0].status is None
    assert answer.wire_dict() == before


def test_client_search_output_remains_an_executable_call_not_a_hosted_operation():
    core = parse(tools=[{"type": "tool_search", "execution": "client"}])
    item = {
        "type": "tool_search_call",
        "id": "ts_new",
        "call_id": "call_search",
        "execution": "client",
        "status": "completed",
        "arguments": {"query": "read"},
    }
    assert validate_response(core, response(item)).output[0].call_id == "call_search"


def test_response_opaque_content_requires_consent_even_when_request_was_plaintext():
    item = {"type": "reasoning", "id": "rs_new", "summary": [], "encrypted_content": "SYNTHETIC"}
    with pytest.raises(ValueError):
        validate_response(parse(), response(item))
    assert (
        validate_response(parse(), response(item), consent=OPAQUE).output[0].encrypted_content
        == "SYNTHETIC"
    )


def test_unreported_usage_stays_unknown_but_explicit_zeroes_are_truthful():
    for usage in ({}, {"input_tokens": None}, {"input_tokens_details": {}}):
        assert response(usage=usage).wire_dict()["usage"] is None
    actual = {"input_tokens": 0, "output_tokens": 0}
    assert response(usage=actual).wire_dict()["usage"] == actual


def test_python_attribute_name_is_not_an_accepted_wire_schema_field():
    with pytest.raises(ValidationError):
        parse(
            text={
                "format": {
                    "type": "json_schema",
                    "name": "schema",
                    "strict": True,
                    "schema_": SCHEMA,
                }
            }
        )


@pytest.mark.parametrize("entry", ["core", "transport", "response", "nested-usage"])
def test_invalid_actual_state_is_rejected_without_serializer_warnings(entry, capfd):
    sensitive = "SYNTHETIC_PRIVATE_INVALID_STATE"
    if entry == "core":
        payload = parse().model_copy(update={"max_output_tokens": sensitive})
        operation = partial(validate_request, payload)
    elif entry == "transport":
        payload = ResponsesCreateRequest.model_validate({"model": "synthetic-model", **request()})
        payload = payload.model_copy(update={"max_output_tokens": sensitive})
        operation = payload.core_request
    else:
        payload = response().model_copy(
            update={"usage": sensitive if entry == "response" else {"input_tokens": sensitive}}
        )
        operation = partial(validate_response, parse(), payload)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError) as caught:
            operation()
    assert recorded == []
    assert sensitive not in str(caught.value)
    captured = capfd.readouterr()
    assert sensitive not in captured.out + captured.err


@pytest.mark.parametrize("entry", ["core", "transport"])
@pytest.mark.parametrize(
    "hidden",
    [
        {"include": ["reasoning.encrypted_content"]},
        {"store": True},
        {"parallel_tool_calls": "SYNTHETIC_PRIVATE_INVALID_STATE"},
        {"unknown_native_field": "SYNTHETIC_PRIVATE_INVALID_STATE"},
    ],
)
def test_forged_field_sets_cannot_hide_controls_or_unknown_fields(entry, hidden):
    model = ResponsesRequest if entry == "core" else ResponsesCreateRequest
    values = {"input": "Synthetic", **hidden}
    if entry == "transport":
        values["model"] = "synthetic-model"
    payload = model.model_construct(_fields_set={"input", "model"} & values.keys(), **values)
    # model_construct drops extra fields under extra=forbid; simulate the same
    # unchecked extra-attribute edit that model_copy permits in middleware.
    if "unknown_native_field" in hidden:
        payload = payload.model_copy(update=hidden)
        payload.__pydantic_fields_set__.discard("unknown_native_field")
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError):
            validate_request(payload) if entry == "core" else payload.core_request()
    assert recorded == []


def test_nested_constructed_state_is_checked_even_when_field_sets_claim_it_was_unset():
    from gateway7.responses_models import ResponsesUsage

    invalid = ResponsesUsage.model_construct(
        _fields_set=set(), input_tokens="SYNTHETIC_PRIVATE_INVALID_STATE"
    )
    payload = response().model_copy(update={"usage": invalid})
    payload.__pydantic_fields_set__.discard("usage")
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError):
            validate_response(parse(), payload)
    assert recorded == []


def test_valid_hidden_nondefault_values_are_retained_after_full_state_validation():
    payload = ResponsesRequest.model_construct(
        _fields_set={"input"},
        input="Synthetic",
        include=["web_search_call.action.sources"],
        parallel_tool_calls=False,
    )
    checked = validate_request(payload)
    assert checked.wire_dict()["include"] == ["web_search_call.action.sources"]
    assert checked.wire_dict()["parallel_tool_calls"] is False


def test_revalidation_preserves_legitimate_nested_unset_and_explicit_null_semantics():
    payload = parse(
        input=[{"role": "user", "content": [{"type": "input_text", "text": "Synthetic"}]}],
        reasoning=None,
    )
    assert validate_request(payload).wire_dict() == payload.wire_dict()
    assert "type" not in validate_request(payload).wire_dict()["input"][0]
    assert validate_request(payload).wire_dict()["reasoning"] is None
    answer = response(usage={"input_tokens": 19, "input_tokens_details": {"cached_tokens": None}})
    assert validate_response(payload, answer).wire_dict() == answer.wire_dict()


def test_transport_rejects_copied_extra_native_fields_before_building_core_payload():
    payload = ResponsesCreateRequest.model_validate({"model": "synthetic-model", **request()})
    payload = payload.model_copy(update={"native_extension": "SYNTHETIC_PRIVATE_INVALID_STATE"})
    with pytest.raises(ValidationError):
        payload.core_request()


@pytest.mark.parametrize("hidden", [{"model": True}, {"model": "../unsafe"}, {"stream": 1}])
def test_transport_authority_is_validated_even_when_hidden_by_a_forged_field_set(hidden):
    values = {"input": "Synthetic", "model": "synthetic-model", **hidden}
    payload = ResponsesCreateRequest.model_construct(_fields_set={"input"}, **values)
    with pytest.raises(ValidationError):
        payload.core_request()


def test_failed_hosted_search_can_finish_with_a_successful_assistant_fallback():
    core = parse(ALL, tools=[{"type": "web_search"}])
    search = {"type": "web_search_call", "id": "ws_failed", "status": "failed"}
    fallback = {
        "type": "message",
        "id": "msg_fallback",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "Synthetic fallback", "annotations": []}],
    }
    checked = validate_response(core, response(search, fallback), consent=ALL)
    assert checked.output[0].status == "failed"
    assert checked.output_text == "Synthetic fallback"
    with pytest.raises(ValidationError):
        validate_response(core, response(search, fallback))


@pytest.mark.parametrize("status", ["in_progress", "searching", "incomplete"])
def test_completed_response_still_rejects_unfinished_hosted_search(status):
    core = parse(ALL, tools=[{"type": "web_search"}])
    item = {"type": "web_search_call", "id": "ws_unfinished", "status": status}
    with pytest.raises(ValueError):
        validate_response(core, response(item), consent=ALL)


@pytest.mark.parametrize(
    "usage,expected",
    [
        (None, None),
        ({}, None),
        ({"input_tokens": 19}, {"input_tokens": 19}),
        ({"output_tokens": 11}, {"output_tokens": 11}),
        ({"input_tokens": 0}, {"input_tokens": 0}),
        ({"output_tokens": 0}, {"output_tokens": 0}),
        ({"input_tokens": 0, "output_tokens": 0}, {"input_tokens": 0, "output_tokens": 0}),
        ({"input_tokens": None, "output_tokens": 11}, {"output_tokens": 11}),
        ({"total_tokens": 30}, None),
        ({"output_tokens_details": {"reasoning_tokens": 5}}, None),
        ({"input_tokens": 19, "total_tokens": 30}, {"input_tokens": 19}),
    ],
)
def test_accounting_retains_each_reported_direction_without_inference(usage, expected):
    answer = response(usage=usage)
    before = answer.wire_dict()
    assert answer.accounting_usage() == expected
    assert answer.wire_dict() == before


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True},
        {"output_tokens": -1},
        {"input_tokens": "SYNTHETIC_PRIVATE_INVALID_STATE"},
        {"output_tokens": 2**63},
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 9},
    ],
)
def test_partial_accounting_revalidates_unchecked_usage_without_serializer_warnings(usage):
    answer = response().model_copy(update={"usage": usage})
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError):
            answer.accounting_usage()
    assert recorded == []


@pytest.mark.parametrize("call_id", ["call_search", None])
def test_incomplete_server_search_is_not_an_incomplete_executable_call(call_id):
    core = parse(
        ALL,
        tools=[{"type": "tool_search", "execution": "server"}],
        parallel_tool_calls=False,
    )
    item = {
        "type": "tool_search_call",
        "id": "ts_incomplete",
        "call_id": call_id,
        "execution": "server",
        "status": "incomplete",
        "arguments": {"query": "Synthetic"},
    }
    answer = response(item, status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    assert validate_response(core, answer, consent=ALL).wire_dict() == answer.wire_dict()
    with pytest.raises(ValidationError):
        validate_response(core, answer)
    with pytest.raises(ValueError):
        validate_response(core, response(item), consent=ALL)


@pytest.mark.parametrize("status", ["in_progress", "searching", "failed"])
def test_server_search_still_rejects_invalid_or_unfinished_terminal_status(status):
    core = parse(ALL, tools=[{"type": "tool_search", "execution": "server"}])
    item = {
        "type": "tool_search_call",
        "id": "ts_invalid",
        "execution": "server",
        "status": status,
        "arguments": {"query": "Synthetic"},
    }
    with pytest.raises(ValueError):
        validate_response(
            core,
            response(item, status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
            consent=ALL,
        )


@pytest.mark.parametrize("second", ["function", "custom", "client-search"])
def test_parallel_restriction_still_counts_every_local_executable_family(second):
    tools = [FUNCTION, CUSTOM, {"type": "tool_search", "execution": "client"}]
    core = parse(tools=tools, parallel_tool_calls=False)
    item = call("b", custom=second == "custom")
    if second == "client-search":
        item = {
            "type": "tool_search_call",
            "id": "ts_client",
            "call_id": "call_client",
            "execution": "client",
            "status": "completed",
            "arguments": {"query": "Synthetic"},
        }
    with pytest.raises(ValueError, match="^Parallel tool calls were disabled$"):
        validate_response(core, response(call(), item))


@pytest.mark.parametrize("choice", ["auto", "required", "none"])
def test_server_search_still_counts_as_an_invocation_for_tool_choice(choice):
    core = parse(
        ALL,
        tools=[{"type": "tool_search", "execution": "server"}],
        parallel_tool_calls=False,
        tool_choice=choice,
    )
    search = {
        "type": "tool_search_call",
        "id": "ts_complete",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "arguments": {"query": "Synthetic"},
    }
    result = {
        "type": "tool_search_output",
        "id": "tso_complete",
        "call_id": "call_search",
        "execution": "server",
        "status": "completed",
        "tools": [FUNCTION],
    }
    answer = response(search, result)
    if choice == "none":
        with pytest.raises(ValueError, match="^Tools were disabled$"):
            validate_response(core, answer, consent=ALL)
    else:
        assert validate_response(core, answer, consent=ALL).wire_dict() == answer.wire_dict()
    with pytest.raises(ValueError, match="^Server tool search omitted its typed result$"):
        validate_response(core, response(search), consent=ALL)


@pytest.mark.parametrize("kind", ["function", "custom", "client-search"])
def test_incomplete_local_calls_remain_rejected_in_an_incomplete_response(kind):
    core = parse(tools=[FUNCTION, CUSTOM, {"type": "tool_search", "execution": "client"}])
    item = call(custom=kind == "custom", status="incomplete")
    if kind == "client-search":
        item = {
            "type": "tool_search_call",
            "id": "ts_client",
            "call_id": "call_client",
            "execution": "client",
            "status": "incomplete",
            "arguments": {"query": "Synthetic"},
        }
    answer = response(item, status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    with pytest.raises(ValueError, match="^An incomplete executable call cannot be delivered$"):
        validate_response(core, answer)


def known_probability():
    return {
        "token": "Synthetic",
        "bytes": [83],
        "logprob": -0.25,
        "top_logprobs": [{"token": "Other", "bytes": [79], "logprob": -1.5}],
    }


@pytest.mark.parametrize("statistics", [None, [], [known_probability()]])
def test_known_subset_response_probability_presence_and_request_separation(statistics):
    item = {
        "type": "message",
        "id": "msg_known",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Synthetic", "logprobs": statistics}],
    }
    answer = response(item)
    checked = validate_response(parse(), answer)
    assert checked.output_text == "Synthetic"
    assert checked.wire_dict()["output"][0] == item
    with pytest.raises(ValidationError):
        parse(input=[item])
    absent = deepcopy(item)
    del absent["content"][0]["logprobs"]
    assert "logprobs" not in response(absent).wire_dict()["output"][0]["content"][0]
    assert parse(input=[absent])


@pytest.mark.parametrize(
    "echoes",
    [
        {
            "max_tool_calls": None,
            "prompt_cache_retention": None,
            "safety_identifier": None,
            "top_logprobs": None,
            "user": None,
        },
        {
            "max_tool_calls": 0,
            "prompt_cache_retention": "in_memory",
            "safety_identifier": "",
            "top_logprobs": 0,
            "user": "",
        },
        {
            "max_tool_calls": 2**63 - 1,
            "prompt_cache_retention": "24h",
            "safety_identifier": "s" * 128,
            "top_logprobs": 20,
            "user": "u" * 2048,
        },
    ],
)
def test_known_subset_response_echoes_are_preserved_but_not_request_controls(echoes):
    checked = validate_response(parse(), response(**echoes))
    assert {key: checked.wire_dict()[key] for key in echoes} == echoes
    for key, value in echoes.items():
        with pytest.raises(ValidationError):
            parse(**{key: value})
    assert not echoes.keys() & response().wire_dict().keys()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_tool_calls", True),
        ("max_tool_calls", 1.0),
        ("max_tool_calls", -1),
        ("max_tool_calls", 2**63),
        ("top_logprobs", False),
        ("top_logprobs", 21),
        ("top_logprobs", -1),
        ("top_logprobs", "1"),
        ("safety_identifier", 1),
        ("safety_identifier", "s" * 129),
        ("prompt_cache_retention", "other"),
        ("user", {}),
        ("frequency_penalty", None),
        ("presence_penalty", 0.0),
        ("unknown_metadata", None),
    ],
)
def test_known_subset_response_echoes_remain_closed_and_strict(field, value):
    with pytest.raises(ValidationError):
        response(**{field: value})


@pytest.mark.parametrize(
    "path,value",
    [
        (("logprob",), True),
        (("logprob",), float("nan")),
        (("logprob",), float("inf")),
        (("bytes",), [True]),
        (("bytes",), [-1]),
        (("bytes",), [256]),
        (("bytes",), None),
        (("top_logprobs",), None),
        (("top_logprobs", 0, "bytes"), [False]),
        (("top_logprobs", 0, "logprob"), float("-inf")),
        (("top_logprobs", 0, "unknown"), None),
        (("unknown",), "SYNTHETIC_PRIVATE"),
    ],
)
def test_known_subset_final_probabilities_reject_invalid_or_extra_state(path, value):
    probability = known_probability()
    current = probability
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    item = {
        "type": "message",
        "role": "assistant",
        "id": "msg_known",
        "content": [
            {"type": "output_text", "text": "Synthetic", "logprobs": [probability]},
        ],
    }
    with pytest.raises(ValidationError):
        response(item)


@pytest.mark.parametrize("field", ["token", "bytes", "logprob", "top_logprobs"])
def test_known_subset_final_probability_fields_are_required(field):
    probability = known_probability()
    del probability[field]
    with pytest.raises(ValidationError):
        response(
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_known",
                "content": [
                    {"type": "output_text", "text": "Synthetic", "logprobs": [probability]},
                ],
            }
        )


def test_known_subset_forged_nested_probability_is_checked_before_serialization():
    answer = response(
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_known",
            "content": [
                {"type": "output_text", "text": "Synthetic", "logprobs": [known_probability()]},
            ],
        }
    )
    probability = answer.output[0].content[0].logprobs[0]
    forged = probability.model_copy(update={"bytes": [True]})
    forged.__pydantic_fields_set__.discard("bytes")
    answer.output[0].content[0].logprobs[0] = forged
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError):
            validate_response(parse(), answer)
    assert recorded == []


def test_raw_projection_preserves_retained_presence_without_loosening_dtos():
    from gateway7.responses_models import project_provider_response

    for configuration in (None, {}, {"effort": None, "summary": "none", "context": None}):
        retained = response(metadata={}, user=None, safety_identifier="").wire_dict()
        retained["reasoning"] = configuration
        raw = {**deepcopy(retained), "synthetic_admin_echo": "SYNTHETIC_DISCARD_CANARY"}
        if isinstance(configuration, dict):
            raw["reasoning"]["synthetic_config_echo"] = "SYNTHETIC_CONFIG_CANARY"
        before = deepcopy(raw)
        projected = project_provider_response(raw)
        assert projected == retained and raw == before
        assert ResponsesResponse.model_validate(projected).wire_dict() == retained
        with pytest.raises(ValidationError):
            ResponsesResponse.model_validate(raw)
    absent = response().wire_dict()
    assert project_provider_response(absent) == absent and "reasoning" not in absent
    with pytest.raises(ValidationError):
        parse(reasoning={"context": None, "synthetic_config_echo": None})
    forged = response().model_copy(update={"synthetic_admin_echo": None})
    with pytest.raises(ValidationError):
        validate_response(parse(), forged)


def test_raw_projection_never_filters_semantic_trees_or_invalid_source_state():
    from gateway7.responses_models import project_provider_response

    items = [
        {"type": "message", "role": "assistant", "content": [], "synthetic_extra": None},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "safe", "synthetic_extra": None}],
        },
        {**call(), "synthetic_extra": None},
        {"type": "reasoning", "summary": [], "synthetic_extra": None},
        {
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "safe", "synthetic_extra": None}],
        },
    ]
    for item in items:
        raw = {**response().wire_dict(), "output": [item], "synthetic_admin_echo": None}
        projected = project_provider_response(raw)
        assert projected["output"] is raw["output"]
        assert projected["output"] == [item]
        with pytest.raises(ValidationError):
            ResponsesResponse.model_validate(projected, context={"consent": ALL})
    opaque = {
        **response().wire_dict(),
        "output": [{"type": "reasoning", "encrypted_content": "SYNTHETIC_OPAQUE"}],
        "synthetic_admin_echo": None,
    }
    projected = project_provider_response(opaque)
    assert projected["output"] is opaque["output"]
    assert ResponsesResponse.model_validate(projected, context={"consent": ALL})
    deep = "SYNTHETIC_DISCARD_CANARY"
    for _ in range(65):
        deep = [deep]
    for excluded in (deep, float("nan"), float("inf"), object(), {1: "bad-key"}):
        with pytest.raises(ValueError, match="^Invalid raw provider response$"):
            project_provider_response({"synthetic_admin_echo": excluded})

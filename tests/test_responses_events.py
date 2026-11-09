"""Structured text records share the native DTO constraints and own their state."""

from copy import deepcopy
import warnings

from pydantic import ValidationError
import pytest

from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import FunctionTool


def head(**changes):
    return ResponsesStreamHead.model_validate(
        {
            "id": "resp_synthetic",
            "created_at": 1800000000.0,
            "model": "synthetic-model",
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": (),
            **changes,
        }
    )


def record(**changes):
    values = {
        "head": head(),
        "sequence_number": 5,
        "item_id": "msg_synthetic",
        "output_index": 0,
        "content_index": 0,
        "phase": "final_answer",
        "delta": "Synthetic",
        "leading_prefix": True,
        **changes,
    }
    return ResponsesTextDelta(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "unsafe\nevent: injected"},
        {"id": ""},
        {"model": "../unsafe"},
        {"created_at": -1.0},
        {"created_at": float("nan")},
        {"created_at": float("inf")},
        {"created_at": True},
        {"parallel_tool_calls": 1},
        {"tool_choice": "unknown"},
        {"tools": []},
        {"tools": ({"type": "unknown"},)},
        {"snapshot": {}},
        {"encrypted_content": "SYNTHETIC_PRIVATE"},
    ],
)
def test_head_uses_closed_strict_native_constraints(changes):
    values = {**head().model_dump(), **changes}
    with pytest.raises(ValidationError):
        ResponsesStreamHead.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence_number": True},
        {"sequence_number": -1},
        {"sequence_number": 2**63},
        {"output_index": False},
        {"content_index": "0"},
        {"item_id": "unsafe\n"},
        {"delta": ""},
        {"delta": 1},
        {"phase": "analysis"},
        {"leading_prefix": 1},
        {"raw_event": {}},
    ],
)
def test_delta_uses_closed_strict_native_constraints(changes):
    with pytest.raises(ValidationError):
        record(**changes)


def test_records_are_frozen_and_detached_recursively_from_sources():
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    tool = FunctionTool(type="function", name="read", parameters=deepcopy(schema))
    source = ResponsesStreamHead(
        id="resp_synthetic", created_at=1, model="synthetic", tools=(tool,)
    )
    delta = record(head=source)
    tool.parameters["properties"] = {}
    assert source.tools[0].parameters == schema
    source.tools[0].parameters["properties"] = {}
    assert delta.head.tools[0].parameters == schema
    assert "strict" not in delta.head.tools[0].wire_dict()
    with pytest.raises(ValidationError):
        delta.delta = "changed"
    with pytest.raises(ValidationError):
        delta.head.model = "changed"


@pytest.mark.parametrize("hidden", [False, True])
def test_records_reject_forged_recursive_state_without_serializing_it(hidden):
    tool = FunctionTool(type="function", name="read", parameters={"type": "object"})
    tool = tool.model_copy(update={"parameters": "SYNTHETIC_PRIVATE"})
    if hidden:
        tool.__pydantic_fields_set__.discard("parameters")
    source = head().model_copy(update={"tools": (tool,)})
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ValidationError) as caught:
            record(head=source)
    assert recorded == []
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)


def test_revalidating_a_record_preserves_omission_and_explicit_null():
    source = ResponsesStreamHead(id="resp_synthetic", created_at=0, model="synthetic")
    omitted = ResponsesTextDelta.model_validate(record(head=source))
    assert "tools" not in omitted.head.wire_dict()
    explicit = record(head=source.model_copy(update={"tools": None}))
    assert explicit.head.wire_dict()["tools"] is None


def test_head_owns_nested_namespace_schemas_and_closed_named_choices():
    tools = (
        {
            "type": "namespace",
            "name": "alpha",
            "description": "Synthetic namespace",
            "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
        },
    )
    choice = {"type": "function", "name": "read", "namespace": "alpha"}
    source = head(tools=tools, tool_choice=choice)
    before = source.wire_dict()
    tools[0]["tools"][0]["parameters"]["type"] = "changed"
    choice["name"] = "changed"
    assert source.wire_dict() == before


def test_nonempty_native_text_preserves_lone_surrogates_without_coercion():
    assert record(delta="Synthetic\ud800").delta == "Synthetic\ud800"

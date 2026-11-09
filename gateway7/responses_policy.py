"""Native plaintext traversal, safe text edits, and protected-field snapshots.

Only the DTO's exact media/encryption fields are opaque. Arbitrary JSON keys
named like those fields remain plaintext. Executable strings are inspected but
never rewritten, including JSON-decoded function arguments and raw custom input.
"""

from collections.abc import Callable
from types import UnionType
from typing import Any, Literal, TypeVar, Union, cast, get_args, get_origin

from gateway7.models import argument_object
from gateway7.plugin_api import Deny
from gateway7.responses_models import (
    CustomTool,
    CustomToolCallOutputItem,
    EncryptedPart,
    FunctionCallItem,
    FunctionCallOutputItem,
    FunctionTool,
    InputAudioPart,
    InputImagePart,
    InputTextPart,
    MessageItem,
    NamespaceTool,
    OutputTextPart,
    ReasoningItem,
    ReasoningPart,
    RefusalPart,
    ResponseOutputTextPart,
    ResponsesModel,
    ResponsesRequest,
    ResponsesResponse,
    SummaryPart,
    ToolSearchTool,
)

NativePayload = TypeVar("NativePayload", ResponsesRequest, ResponsesResponse)
_OPAQUE = {
    (InputImagePart, "image_url"),
    (InputAudioPart, "audio_url"),
    (EncryptedPart, "encrypted_content"),
    (ReasoningItem, "encrypted_content"),
    (FunctionCallItem, "encrypted_function_args"),
}
_FREE_TEXT = {
    (ResponsesRequest, "input"),
    (ResponsesRequest, "instructions"),
    (MessageItem, "content"),
    (InputTextPart, "text"),
    (OutputTextPart, "text"),
    (ResponseOutputTextPart, "text"),
    (RefusalPart, "refusal"),
    (SummaryPart, "text"),
    (ReasoningPart, "text"),
    (FunctionCallOutputItem, "output"),
    (CustomToolCallOutputItem, "output"),
    (FunctionTool, "description"),
    (CustomTool, "description"),
    (NamespaceTool, "description"),
    (ToolSearchTool, "description"),
}


def _editable(owner: ResponsesModel, name: str, value: Any) -> bool:
    return (
        isinstance(value, str)
        and (type(owner), name) in _FREE_TEXT
        and not (isinstance(owner, OutputTextPart) and owner.annotations)
        and not (isinstance(owner, ResponseOutputTextPart) and owner.logprobs)
    )


def _literal(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Literal:
        return True
    if origin in (Union, UnionType):
        return all(item is type(None) or _literal(item) for item in get_args(annotation))
    if origin is list:
        return _literal(get_args(annotation)[0])
    return False


def apply_policy(
    payload: NativePayload,
    transform: Callable[[str], tuple[str, int]],
    *,
    action: Literal["block", "log", "redact"] = "redact",
) -> tuple[NativePayload | Deny, int]:
    """Inspect every plaintext field; reject unsafe rewrites rather than drop it."""
    matches = 0
    denied = False

    def visit(value: Any, editable: bool = False, allow_edits: bool = True) -> Any:
        nonlocal matches, denied
        if isinstance(value, str):
            replacement, hits = transform(value)
            matches += hits
            if hits and (action == "block" or action == "redact" and not editable):
                denied = True
            return replacement if action == "redact" and editable else value
        if isinstance(value, ResponsesModel):
            updates = {}
            for name, field in type(value).model_fields.items():
                child = getattr(value, name)
                if (type(value), name) in _OPAQUE or _literal(field.annotation):
                    continue
                if name == "tool_choice" and isinstance(child, str):
                    continue
                can_edit = allow_edits and (
                    not isinstance(value, ResponsesResponse) or name == "output"
                )
                if isinstance(value, FunctionCallItem) and name == "arguments":
                    visit(argument_object(child), allow_edits=False)
                    continue
                updated = visit(child, can_edit and _editable(value, name, child), can_edit)
                if updated != child:
                    updates[name] = updated
            return value.model_copy(update=updates) if updates else value
        if isinstance(value, list):
            return [visit(child, allow_edits=allow_edits) for child in value]
        if isinstance(value, dict):
            for key, child in value.items():
                visit(key, allow_edits=False)
                visit(child, allow_edits=False)
        return value

    result = visit(payload)
    return (Deny() if denied else cast(NativePayload, result)), matches


def protected_snapshot(payload: ResponsesRequest | ResponsesResponse) -> object:
    """Freeze structure, controls, identities, executable data and opaque bytes.

    Native hooks can change free text only. Response echo fields and terminal
    metadata stay provider-owned; array order and explicit field presence stay
    intact. JSON object key order is insignificant; primitive types stay distinct.
    Annotated text stays intact rather than corrupt citation offsets.
    """

    def visit(value: Any, allow_edits: bool = True) -> Any:
        if isinstance(value, ResponsesModel):
            fields = []
            for name in type(value).model_fields:
                child = getattr(value, name)
                can_edit = allow_edits and (
                    not isinstance(value, ResponsesResponse) or name == "output"
                )
                fields.append(
                    (
                        name,
                        ("free_text",)
                        if can_edit and _editable(value, name, child)
                        else visit(child, can_edit),
                    )
                )
            return type(value), frozenset(value.model_fields_set), tuple(fields)
        if isinstance(value, list):
            return tuple(visit(child, allow_edits) for child in value)
        if isinstance(value, dict):
            return {key: visit(child, False) for key, child in value.items()}
        return type(value), value

    return visit(payload)

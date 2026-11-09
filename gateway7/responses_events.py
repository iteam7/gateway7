"""Detached, closed metadata for the native leading-text callback window."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Self, TypeAlias

from pydantic import Field, ModelWrapValidatorHandler, field_validator, model_validator

from gateway7.config import ModelId
from gateway7.responses_models import (
    Count,
    NativeId,
    ResponseTool,
    ResponsesModel,
    ToolChoice,
    _full_state,
    _restore_unset,
)

__all__ = ["ResponsesStreamHead", "ResponsesTextDelta", "ResponsesTextSink"]


class _StreamRecord(ResponsesModel):
    @model_validator(mode="wrap")
    @classmethod
    def detached_state(cls, value: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        # Read actual recursive state, not serializers or claimed field sets.
        # Rebuilding also detaches nested tool schemas from mutable source DTOs.
        checked = handler(_full_state(value))
        if isinstance(value, ResponsesModel):
            _restore_unset(value, checked)
        elif isinstance(value, dict):
            for name in cls.model_fields:
                if name in value:
                    _restore_unset(value[name], getattr(checked, name))
        return checked


class ResponsesStreamHead(_StreamRecord):
    """Provider-checked identity and request controls, never a raw snapshot."""

    id: NativeId
    created_at: float = Field(ge=0, allow_inf_nan=False)
    model: ModelId
    parallel_tool_calls: bool | None = None
    tool_choice: ToolChoice | None = None
    tools: tuple[ResponseTool, ...] | None = Field(default=None, max_length=128)


class ResponsesTextDelta(_StreamRecord):
    """One assistant text fragment with its native identity and window proof."""

    head: ResponsesStreamHead
    sequence_number: Count
    item_id: NativeId
    output_index: Count
    content_index: Count
    phase: Literal["commentary", "final_answer"] | None = None
    delta: str
    leading_prefix: bool

    @field_validator("delta")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        # A length-constrained Pydantic string rejects lone surrogates, unlike
        # the native text DTO. Keep the same strings and escape them on the wire.
        if not value:
            raise ValueError("A text delta must not be empty")
        return value


ResponsesTextSink: TypeAlias = Callable[[ResponsesTextDelta], Awaitable[None]]

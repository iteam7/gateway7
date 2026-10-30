"""Validated provider-neutral messages, including bounded function-tool turns."""

import json
import math
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ToolName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ToolCallId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class StrictPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")

    def check(item: object, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("JSON nesting exceeds the supported bound")
        if isinstance(item, dict):
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("JSON object keys must be strings")
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Unsupported JSON value")
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")

    check(value)
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 65_536:
        raise ValueError("JSON object exceeds the supported bound")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def argument_object(arguments: str) -> dict[str, Any]:
    """Decode once at trust boundaries; never rewrite executable JSON with regex."""
    try:
        return _json_object(json.loads(arguments, object_pairs_hook=_unique_object))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError("Tool arguments must be a bounded JSON object") from None


class FunctionDefinition(StrictPayload):
    name: ToolName
    description: str | None = Field(default=None, max_length=16_384)
    parameters: dict[str, Any]
    strict: bool | None = None

    @field_validator("parameters")
    @classmethod
    def valid_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _json_object(value)


class ToolDefinition(StrictPayload):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class FunctionCall(StrictPayload):
    name: ToolName
    arguments: str = Field(max_length=65_536)

    @field_validator("arguments")
    @classmethod
    def valid_arguments(cls, value: str) -> str:
        argument_object(value)
        return value


class ToolCall(StrictPayload):
    id: ToolCallId
    type: Literal["function"] = "function"
    function: FunctionCall


class NamedFunctionChoice(StrictPayload):
    name: ToolName


class NamedToolChoice(StrictPayload):
    type: Literal["function"] = "function"
    function: NamedFunctionChoice


ToolChoice = Literal["auto", "none", "required"] | NamedToolChoice


class Message(StrictPayload):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=1)
    tool_call_id: ToolCallId | None = None

    @model_validator(mode="after")
    def valid_tool_shape(self) -> "Message":
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistant messages can contain tool calls")
        if self.content is None and not (self.role == "assistant" and self.tool_calls):
            raise ValueError("Null content requires an assistant tool call")
        if (self.role == "tool") != (self.tool_call_id is not None):
            raise ValueError("Tool results require their call identifier")
        return self


class ChatRequest(StrictPayload):
    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(default=256, ge=1, le=4096)
    tools: list[ToolDefinition] = Field(default_factory=list, max_length=128)
    tool_choice: ToolChoice | None = None
    parallel_tool_calls: Literal[False] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, allow_inf_nan=False)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, allow_inf_nan=False)
    seed: int | None = Field(default=None, ge=-(2**63), le=2**63 - 1)
    stop: str | list[str] | None = None

    @field_validator("parallel_tool_calls", mode="before")
    @classmethod
    def serial_calls_only(cls, value: object) -> object:
        if value is not None and (type(value) is not bool or value):
            raise ValueError("Only serial tool calls are supported")
        return value

    @field_validator("stop")
    @classmethod
    def bounded_stop(cls, value: str | list[str] | None) -> str | list[str] | None:
        parts = value if isinstance(value, list) else [] if value is None else [value]
        if value is not None and (not parts or len(parts) > 4):
            raise ValueError("Specify one to four stop sequences")
        if any(not part or len(part) > 1024 for part in parts):
            raise ValueError("Stop sequences must be nonempty and bounded")
        return value

    @model_validator(mode="after")
    def valid_tool_history(self) -> "ChatRequest":
        names = [tool.function.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")
        if isinstance(self.tool_choice, NamedToolChoice):
            if self.tool_choice.function.name not in names:
                raise ValueError("Named tool choice must refer to an advertised tool")
        elif self.tool_choice == "required" and not names:
            raise ValueError("Required tool choice needs an advertised tool")
        if self.parallel_tool_calls is not None and not names:
            raise ValueError("Tool parallelism control needs an advertised tool")
        seen: set[str] = set()
        pending: str | None = None
        for message in self.messages:
            if message.role == "tool":
                if pending is None or message.tool_call_id != pending:
                    raise ValueError("Tool results must match the preceding call")
                pending = None
                continue
            if pending is not None:
                raise ValueError("Tool calls must have their result before another turn")
            for call in message.tool_calls:
                if call.id in seen:
                    raise ValueError("Tool call identifiers must be unique")
                seen.add(call.id)
                pending = call.id
        if pending is not None:
            raise ValueError("Tool history is missing a result")
        return self

    @property
    def requires_tools(self) -> bool:
        return bool(self.tools) or any(
            message.tool_calls or message.role == "tool" for message in self.messages
        )


class ChatResponse(StrictPayload):
    text: str
    usage: dict[str, int] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=1)
    # Provider metadata is snapshotted by the runner before response middleware.
    finish_reason: Literal["stop", "length", "tool_calls"] = "stop"

    @model_validator(mode="after")
    def valid_finish(self) -> "ChatResponse":
        if bool(self.tool_calls) != (self.finish_reason == "tool_calls"):
            raise ValueError("Tool-call output requires the matching finish reason")
        return self


def _json_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _json_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_strings(child)


def tool_text(payload: ChatRequest | ChatResponse) -> Iterator[str]:
    """All structured tool strings are inspected without mutating their structure."""
    if isinstance(payload, ChatRequest):
        for tool in payload.tools:
            yield tool.function.name
            if tool.function.description is not None:
                yield tool.function.description
            yield from _json_strings(tool.function.parameters)
        calls = [call for message in payload.messages for call in message.tool_calls]
        for message in payload.messages:
            if message.tool_call_id is not None:
                yield message.tool_call_id
    else:
        calls = payload.tool_calls
    for call in calls:
        yield call.id
        yield call.function.name
        yield from _json_strings(argument_object(call.function.arguments))

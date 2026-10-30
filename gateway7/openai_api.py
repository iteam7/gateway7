"""Explicit OpenAI Chat Completions subset with checked, buffered SSE output."""

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gateway7.config import ModelId
from gateway7.errors import GatewayError
from gateway7.models import ChatRequest, ChatResponse, Message, ToolCall, ToolChoice, ToolDefinition


class NativeChatRequest(ChatRequest):
    model: ModelId | None = None

    @model_validator(mode="before")
    @classmethod
    def native_contract(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if "model" in value and value["model"] is None:
                raise ValueError("Omit model to use the configured default")
            if set(value) - {"model", "messages", "max_tokens"}:
                raise ValueError("Native chat accepts only text messages and a token limit")
            messages = value.get("messages")
            if isinstance(messages, list):
                for item in messages:
                    if isinstance(item, dict) and (
                        set(item) - {"role", "content"}
                        or item.get("role") not in ("system", "user", "assistant")
                    ):
                        raise ValueError("Native chat accepts only text messages")
        return value

    def core_request(self) -> ChatRequest:
        return ChatRequest(messages=self.messages, max_tokens=self.max_tokens)


class OpenAIMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | None
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=1)
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def message_contract(self) -> "OpenAIMessage":
        Message.model_validate(
            {
                **self.model_dump(exclude_none=True),
                "role": "system" if self.role == "developer" else self.role,
                "content": self.content,
            }
        )
        return self


class StreamOptions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    include_usage: bool = False


class OpenAIChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    model: ModelId
    messages: list[OpenAIMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=4096)
    stream: bool = False
    stream_options: StreamOptions | None = None
    n: int = Field(default=1, ge=1, le=1)
    store: bool = False
    tools: list[ToolDefinition] = Field(default_factory=list, max_length=128)
    tool_choice: ToolChoice | None = None
    parallel_tool_calls: Literal[False] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, allow_inf_nan=False)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, allow_inf_nan=False)
    seed: int | None = None
    stop: str | list[str] | None = None

    @field_validator("parallel_tool_calls", mode="before")
    @classmethod
    def serial_calls_only(cls, value: object) -> object:
        if value is not None and (type(value) is not bool or value):
            raise ValueError("Only serial tool calls are supported")
        return value

    @field_validator("store")
    @classmethod
    def disabled_store(cls, value: bool) -> bool:
        if value:
            raise ValueError("This option must be false")
        return value

    @model_validator(mode="before")
    @classmethod
    def token_limit_contract(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if "max_tokens" in value and "max_completion_tokens" in value:
                raise ValueError("Specify only one token limit")
            if any(
                name in value and value[name] is None
                for name in ("max_tokens", "max_completion_tokens", "stream_options")
            ):
                raise ValueError("Explicit null control fields are unsupported")
        return value

    @model_validator(mode="after")
    def completion_contract(self) -> "OpenAIChatRequest":
        if self.stream_options is not None and not self.stream:
            raise ValueError("Stream options require streaming")
        # The neutral contract owns history, tool identifiers and tool choices.
        self.core_request()
        return self

    def core_request(self) -> ChatRequest:
        values = self.model_dump(
            exclude={"model", "stream", "stream_options", "n", "store", "max_completion_tokens"},
            exclude_none=True,
        )
        values["messages"] = [
            {
                **item.model_dump(exclude_none=True),
                "role": "system" if item.role == "developer" else item.role,
                "content": item.content,
            }
            for item in self.messages
        ]
        values["max_tokens"] = self.max_completion_tokens or self.max_tokens or 256
        return ChatRequest.model_validate(values)

    def needs_openai_provider(self) -> bool:
        return (
            self.stream
            or bool(self.tools)
            or self.tool_choice is not None
            or any(item.role == "tool" or item.tool_calls for item in self.messages)
            or self.parallel_tool_calls is not None
            or any(
                getattr(self, name) is not None
                for name in (
                    "temperature",
                    "top_p",
                    "frequency_penalty",
                    "presence_penalty",
                    "seed",
                    "stop",
                )
            )
        )


def _usage(response: ChatResponse) -> dict[str, int] | None:
    usage = response.usage
    if usage is not None and all(
        type(usage.get(name)) is int and 0 <= usage[name] <= 2**63 - 1
        for name in ("input_tokens", "output_tokens")
    ):
        return {
            "prompt_tokens": usage["input_tokens"],
            "completion_tokens": usage["output_tokens"],
            "total_tokens": usage["input_tokens"] + usage["output_tokens"],
        }
    return None


def completion_response(response: ChatResponse, model: str, request_id: str) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": response.text if response.text or not response.tool_calls else None,
    }
    if response.tool_calls:
        message["tool_calls"] = [item.model_dump() for item in response.tool_calls]
    return {
        "id": "chatcmpl-" + request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": response.finish_reason,
                "logprobs": None,
            }
        ],
        "usage": _usage(response),
    }


def completion_sse(
    response: ChatResponse, model: str, request_id: str, *, include_usage: bool = False
) -> bytes:
    """Encode the already approved response before HTTP headers are sent.

    Provider generation is streamed upstream, but middleware still inspects the
    complete response. No text or executable tool call is released before that.
    """
    identity = {
        "id": "chatcmpl-" + request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }
    events: list[dict[str, Any]] = []

    def choice(delta: dict[str, Any], finish: str | None = None) -> None:
        events.append(
            {
                **identity,
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish, "logprobs": None}
                ],
                "usage": None,
            }
        )

    choice({"role": "assistant", "content": ""})
    if response.text:
        choice({"content": response.text})
    for index, call in enumerate(response.tool_calls):
        choice({"tool_calls": [{"index": index, **call.model_dump()}]})
    choice({}, response.finish_reason)
    if include_usage:
        events.append({**identity, "choices": [], "usage": _usage(response)})
    # ASCII JSON also represents a JSON-escaped lone surrogate safely; defer no
    # encoding or model serialization until after the response has started.
    return (
        b"".join(
            b"data: "
            + json.dumps(event, ensure_ascii=True, allow_nan=False).encode("ascii")
            + b"\n\n"
            for event in events
        )
        + b"data: [DONE]\n\n"
    )


def error_body(
    error: GatewayError, request_id: str, parameter: str | None = None
) -> dict[str, Any]:
    kind = (
        "authentication_error"
        if error.code == "unauthorized"
        else "permission_error"
        if error.code == "model_forbidden"
        else "invalid_request_error"
        if error.status_code < 500
        else "api_error"
    )
    return {
        "error": {"message": error.message, "type": kind, "param": parameter, "code": error.code},
        "request_id": request_id,
    }

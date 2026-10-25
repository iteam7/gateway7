"""Explicit non-streaming, text-only OpenAI Chat Completions compatibility."""

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gateway7.config import ModelId
from gateway7.errors import GatewayError
from gateway7.models import ChatRequest, ChatResponse, Message


class NativeChatRequest(ChatRequest):
    model: ModelId | None = None

    @model_validator(mode="before")
    @classmethod
    def no_null_model(cls, value: Any) -> Any:
        if isinstance(value, dict) and "model" in value and value["model"] is None:
            raise ValueError("Omit model to use the configured default")
        return value

    def core_request(self) -> ChatRequest:
        return ChatRequest(messages=self.messages, max_tokens=self.max_tokens)


class OpenAIMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    role: Literal["system", "developer", "user", "assistant"]
    content: str


class OpenAIChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    model: ModelId
    messages: list[OpenAIMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=4096)
    stream: bool = False
    n: int = Field(default=1, ge=1, le=1)
    store: bool = False

    @field_validator("stream", "store")
    @classmethod
    def disabled_options(cls, value: bool) -> bool:
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
                for name in ("max_tokens", "max_completion_tokens")
            ):
                raise ValueError("Explicit null token limits are unsupported")
        return value

    def core_request(self) -> ChatRequest:
        return ChatRequest(
            messages=[
                Message(
                    role="system" if item.role == "developer" else item.role, content=item.content
                )
                for item in self.messages
            ],
            max_tokens=self.max_completion_tokens or self.max_tokens or 256,
        )


def completion_response(response: ChatResponse, model: str, request_id: str) -> dict[str, Any]:
    usage = response.usage
    normalized_usage = None
    if usage is not None and all(
        type(usage.get(name)) is int and 0 <= usage[name] <= 2**63 - 1
        for name in ("input_tokens", "output_tokens")
    ):
        normalized_usage = {
            "prompt_tokens": usage["input_tokens"],
            "completion_tokens": usage["output_tokens"],
            "total_tokens": usage["input_tokens"] + usage["output_tokens"],
        }
    return {
        "id": "chatcmpl-" + request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.text},
                "finish_reason": response.finish_reason,
                "logprobs": None,
            }
        ],
        "usage": normalized_usage,
    }


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

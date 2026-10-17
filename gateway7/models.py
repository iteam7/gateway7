"""Provider-neutral messages exchanged with plugins and callers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(default=256, ge=1, le=4096)


class ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    text: str
    usage: dict[str, int] | None = None

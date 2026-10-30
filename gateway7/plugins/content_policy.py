"""Apply a bounded literal-term policy without evaluating operator-supplied regex.

Policies are exact substring rules, not a prompt-injection or semantic classifier.
A hit can block, log metadata only, or substitute text in either direction.
"""

import logging
import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from gateway7.models import ChatRequest, ChatResponse, tool_text
from gateway7.plugin_api import Deny, NextHandler, PluginContext, PluginDescriptor

logger = logging.getLogger("gateway7")
Term = Annotated[str, StringConstraints(min_length=1, max_length=256)]


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    terms: tuple[Term, ...] = Field(min_length=1, max_length=32)
    phase: Literal["request", "response", "both"] = "both"
    action: Literal["block", "log", "redact"] = "block"
    replacement: str = Field(default="[removed]", min_length=1, max_length=128)
    case_sensitive: bool = True

    @field_validator("terms", mode="before")
    @classmethod
    def freeze_terms(cls, value: object) -> object:
        # YAML lists are converted to immutable tuples before strict validation;
        # values inside the sequence still use strict string validation.
        return tuple(value) if isinstance(value, list) else value

    @field_validator("terms")
    @classmethod
    def distinct_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not item.strip() for item in value):
            raise ValueError("Policy terms must be distinct and nonblank")
        return value


@dataclass(frozen=True)
class ContentPolicyPlugin:
    settings: Settings
    pattern: re.Pattern[str]

    def _apply(self, text: str) -> tuple[str, int]:
        if self.settings.action == "redact":
            # A callable replacement prevents backslash/group interpolation.
            return self.pattern.subn(lambda _: self.settings.replacement, text)
        return text, sum(1 for _ in self.pattern.finditer(text))

    def _record(self, context: PluginContext, phase: str, matches: int) -> None:
        if matches:
            logger.info(
                "request_id=%s outcome=policy_match component=%s phase=%s action=%s matches=%d",
                context.request_id,
                context.instance_name or "content-policy",
                phase,
                self.settings.action,
                matches,
            )

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse | Deny:
        if self.settings.phase in ("request", "both"):
            messages = []
            structured_hits = sum(len(self.pattern.findall(text)) for text in tool_text(request))
            total = structured_hits
            for message in request.messages:
                text, hits = (
                    self._apply(message.content) if message.content is not None else (None, 0)
                )
                total += hits
                messages.append(message.model_copy(update={"content": text}))
            self._record(context, "request", total)
            if (total and self.settings.action == "block") or (
                structured_hits and self.settings.action == "redact"
            ):
                return Deny()
            if self.settings.action == "redact":
                request = request.model_copy(update={"messages": messages})
        response = await call_next(request)
        if self.settings.phase in ("response", "both"):
            text, hits = self._apply(response.text)
            structured_hits = sum(len(self.pattern.findall(value)) for value in tool_text(response))
            hits += structured_hits
            self._record(context, "response", hits)
            if (hits and self.settings.action == "block") or (
                structured_hits and self.settings.action == "redact"
            ):
                return Deny()
            if self.settings.action == "redact":
                response = response.model_copy(update={"text": text})
        return response


def create(settings: Settings) -> ContentPolicyPlugin:
    # Escaping makes every configured term literal. Longer overlapping terms
    # win at the same position; regex alternation never exposes user regex syntax.
    alternatives = sorted(settings.terms, key=len, reverse=True)
    flags = 0 if settings.case_sensitive else re.IGNORECASE
    return ContentPolicyPlugin(settings, re.compile("|".join(map(re.escape, alternatives)), flags))


PLUGIN = PluginDescriptor(
    id="content-policy", api_version=2, settings_model=Settings, create=create, supports_tools=True
)

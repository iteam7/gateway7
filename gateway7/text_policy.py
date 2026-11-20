"""A small API v2 adapter for pure synchronous text policies.

Free text can be changed. Matches in executable or protected structured data
are denied rather than rewritten. Native Responses keeps its native DTOs.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, TypeVar

from gateway7.models import ChatRequest, ChatResponse, tool_text
from gateway7.plugin_api import (
    Deny,
    EarlyStreamUnsupported,
    NextHandler,
    PluginContext,
    ResponsesContext,
    ResponsesUnsupported,
)
from gateway7.responses_models import ResponsesRequest, ResponsesResponse
from gateway7.responses_policy import apply_policy

TextTransform: TypeAlias = Callable[[str], tuple[str, int]]
PolicyPhase: TypeAlias = Literal["request", "response", "both"]
PolicyAction: TypeAlias = Literal["block", "redact"]
NativePayload = TypeVar("NativePayload", ResponsesRequest, ResponsesResponse)


@dataclass(frozen=True)
class TextPolicyMiddleware:
    """Implement a policy once; the gateway still owns forwarding and deadlines.

    ``transform`` returns replacement text and a nonnegative match count. It
    must be pure, synchronous and nonblocking. A block policy ignores replacement
    text. Early hooks explicitly refuse any response-dependent configuration.
    Descriptors must still opt in to Chat tool support with ``supports_tools``.
    """

    transform: TextTransform
    phase: PolicyPhase = field(default="both", kw_only=True)
    action: PolicyAction = field(default="redact", kw_only=True)

    def __post_init__(self) -> None:
        if type(self.phase) is not str or self.phase not in ("request", "response", "both"):
            raise ValueError("Invalid text policy phase")
        if type(self.action) is not str or self.action not in ("block", "redact"):
            raise ValueError("Invalid text policy action")
        if (
            not callable(self.transform)
            or inspect.iscoroutinefunction(self.transform)
            or inspect.iscoroutinefunction(getattr(self.transform, "__call__", None))
        ):
            raise ValueError("Text policy transforms must be synchronous")

    def _transform(self, text: str) -> tuple[str, int]:
        try:
            result = self.transform(text)
        except Exception:
            raise ValueError("Text policy transform failed") from None
        if inspect.iscoroutine(result):
            result.close()
        if (
            type(result) is not tuple
            or len(result) != 2
            or type(result[0]) is not str
            or type(result[1]) is not int
            or not 0 <= result[1] <= 2**63 - 1
            or result[0] != text
            and result[1] == 0
        ):
            raise ValueError("Invalid text policy transform result")
        return result

    def _request(self, request: ChatRequest) -> ChatRequest | Deny:
        if self.phase not in ("request", "both"):
            return request
        if any(self._transform(text)[1] for text in tool_text(request)):
            return Deny()
        messages = []
        for message in request.messages:
            if message.content is None:
                messages.append(message)
                continue
            replacement, matches = self._transform(message.content)
            if matches and self.action == "block":
                return Deny()
            messages.append(
                message.model_copy(
                    update={"content": replacement if self.action == "redact" else message.content}
                )
            )
        return request.model_copy(update={"messages": messages})

    def _response(self, response: ChatResponse) -> ChatResponse | Deny:
        if self.phase not in ("response", "both"):
            return response
        if any(self._transform(text)[1] for text in tool_text(response)):
            return Deny()
        replacement, matches = self._transform(response.text)
        if matches and self.action == "block":
            return Deny()
        return response.model_copy(
            update={"text": replacement if self.action == "redact" else response.text}
        )

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse | Deny:
        prepared = self._request(request)
        if isinstance(prepared, Deny):
            return prepared
        response = await call_next(prepared)
        return self._response(response)

    async def prepare_early_stream(
        self, request: ChatRequest, context: PluginContext
    ) -> ChatRequest | Deny:
        if self.phase != "request":
            raise EarlyStreamUnsupported
        return self._request(request)

    def _native(self, payload: NativePayload) -> NativePayload | Deny:
        return apply_policy(payload, self._transform, action=self.action)[0]

    async def prepare_responses(
        self, request: ResponsesRequest, context: ResponsesContext
    ) -> ResponsesRequest | Deny:
        if self.phase not in ("request", "both"):
            return request
        return self._native(request)

    async def check_responses(
        self, response: ResponsesResponse, context: ResponsesContext
    ) -> ResponsesResponse | Deny:
        if self.phase not in ("response", "both"):
            return response
        return self._native(response)

    async def prepare_early_responses(
        self, request: ResponsesRequest, context: ResponsesContext
    ) -> ResponsesRequest | Deny:
        if self.phase != "request":
            raise ResponsesUnsupported
        return self._native(request)

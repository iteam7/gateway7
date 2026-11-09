"""Mask three explicit Russian phone formats without retaining original text.

Recognized shapes are ``+7 NNN NNN-NN-NN``, ``8 (NNN) NNN-NN-NN`` and
``+7NNNNNNNNNN`` using ASCII digits and literal spaces. This deliberately
narrow detector does not claim to recognize every phone number.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway7.models import ChatRequest, ChatResponse, tool_text
from gateway7.plugin_api import (
    Deny,
    EarlyStreamUnsupported,
    NextHandler,
    PluginContext,
    PluginDescriptor,
    ResponsesContext,
    ResponsesUnsupported,
)
from gateway7.responses_models import ResponsesRequest, ResponsesResponse
from gateway7.responses_policy import apply_policy


_PHONE_NUMBER = re.compile(
    r"(?<![\w+])"
    r"(?:\+7 [0-9]{3} [0-9]{3}-[0-9]{2}-[0-9]{2}"
    r"|8 \([0-9]{3}\) [0-9]{3}-[0-9]{2}-[0-9]{2}"
    r"|\+7[0-9]{10})"
    r"(?!\w)"
)


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    # Preserve the original request-only behavior for settings: {}.
    phase: Literal["request", "response", "both"] = "request"
    replacement: str = Field(default="[PHONE]", min_length=1, max_length=128)


@dataclass(frozen=True)
class PhoneMaskPlugin:
    settings: Settings

    def _prepare_request(self, request: ChatRequest) -> ChatRequest | Deny:
        if self.settings.phase in ("request", "both"):
            if any(_PHONE_NUMBER.search(text) is not None for text in tool_text(request)):
                return Deny()
            request = request.model_copy(
                update={
                    "messages": [
                        message.model_copy(
                            update={
                                "content": None
                                if message.content is None
                                else _PHONE_NUMBER.sub(
                                    lambda _: self.settings.replacement, message.content
                                )
                            }
                        )
                        for message in request.messages
                    ]
                }
            )
        return request

    async def prepare_early_stream(
        self, request: ChatRequest, context: PluginContext
    ) -> ChatRequest | Deny:
        if self.settings.phase != "request":
            raise EarlyStreamUnsupported
        return self._prepare_request(request)

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse | Deny:
        prepared = self._prepare_request(request)
        if isinstance(prepared, Deny):
            return prepared
        request = prepared
        response = await call_next(request)
        if self.settings.phase in ("response", "both"):
            if any(_PHONE_NUMBER.search(text) is not None for text in tool_text(response)):
                return Deny()
            response = response.model_copy(
                update={
                    "text": _PHONE_NUMBER.sub(lambda _: self.settings.replacement, response.text)
                }
            )
        return response

    def _native_mask(self, text: str) -> tuple[str, int]:
        return _PHONE_NUMBER.subn(lambda _: self.settings.replacement, text)

    async def prepare_responses(
        self, request: ResponsesRequest, context: ResponsesContext
    ) -> ResponsesRequest | Deny:
        if self.settings.phase not in ("request", "both"):
            return request
        return apply_policy(request, self._native_mask)[0]

    async def check_responses(
        self, response: ResponsesResponse, context: ResponsesContext
    ) -> ResponsesResponse | Deny:
        if self.settings.phase not in ("response", "both"):
            return response
        return apply_policy(response, self._native_mask)[0]

    async def prepare_early_responses(
        self, request: ResponsesRequest, context: ResponsesContext
    ) -> ResponsesRequest | Deny:
        if self.settings.phase != "request":
            raise ResponsesUnsupported
        return await self.prepare_responses(request, context)


def create(settings: Settings) -> PhoneMaskPlugin:
    return PhoneMaskPlugin(settings)


PLUGIN = PluginDescriptor(
    id="phone-mask", api_version=2, settings_model=Settings, create=create, supports_tools=True
)

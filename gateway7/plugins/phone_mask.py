"""Mask three explicit Russian phone formats without retaining original text.

Recognized shapes are ``+7 NNN NNN-NN-NN``, ``8 (NNN) NNN-NN-NN`` and
``+7NNNNNNNNNN`` using ASCII digits and literal spaces. This deliberately
narrow detector does not claim to recognize every phone number.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import NextHandler, PluginContext, PluginDescriptor


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

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse:
        if self.settings.phase in ("request", "both"):
            request = request.model_copy(
                update={
                    "messages": [
                        message.model_copy(
                            update={
                                "content": _PHONE_NUMBER.sub(
                                    lambda _: self.settings.replacement, message.content
                                )
                            }
                        )
                        for message in request.messages
                    ]
                }
            )
        response = await call_next(request)
        if self.settings.phase in ("response", "both"):
            response = response.model_copy(
                update={
                    "text": _PHONE_NUMBER.sub(lambda _: self.settings.replacement, response.text)
                }
            )
        return response


def create(settings: Settings) -> PhoneMaskPlugin:
    return PhoneMaskPlugin(settings)


PLUGIN = PluginDescriptor(id="phone-mask", api_version=2, settings_model=Settings, create=create)

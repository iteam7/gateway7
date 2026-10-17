"""Mask three Russian phone-number formats throughout the request history.

Recognized shapes are ``+7 NNN NNN-NN-NN``, ``8 (NNN) NNN-NN-NN`` and
``+7NNNNNNNNNN`` using ASCII digits and literal spaces. This intentionally
narrow detector is a demo, not a general personal-data detector. Word/digit
boundaries prevent matches inside longer identifiers. Originals are neither
retained in plugin state nor logged, and masking is not reversible.
"""

import re

from pydantic import BaseModel, ConfigDict

from gateway7.models import ChatRequest
from gateway7.plugin_api import Continue, PluginContext, PluginDescriptor


_PHONE_NUMBER = re.compile(
    r"(?<![\w+])"
    r"(?:\+7 [0-9]{3} [0-9]{3}-[0-9]{2}-[0-9]{2}"
    r"|8 \([0-9]{3}\) [0-9]{3}-[0-9]{2}-[0-9]{2}"
    r"|\+7[0-9]{10})"
    r"(?!\w)"
)


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PhoneMaskPlugin:
    async def on_request(
        self, request: ChatRequest, context: PluginContext
    ) -> Continue:
        messages = [
            message.model_copy(
                update={"content": _PHONE_NUMBER.sub("[PHONE]", message.content)}
            )
            for message in request.messages
        ]
        return Continue(payload=request.model_copy(update={"messages": messages}))


def create(settings: Settings) -> PhoneMaskPlugin:
    return PhoneMaskPlugin()


PLUGIN = PluginDescriptor(
    id="phone-mask", api_version=1, settings_model=Settings, create=create
)

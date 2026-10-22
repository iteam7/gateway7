"""Synthetic policy middleware: deny the demo marker before calling next."""

from pydantic import BaseModel, ConfigDict

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import Deny, NextHandler, PluginContext, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    marker: str = "BLOCK-ME-TEST"


class GuardPlugin:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse | Deny:
        if any(self.settings.marker in message.content for message in request.messages):
            return Deny()
        return await call_next(request)


def create(settings: Settings) -> GuardPlugin:
    return GuardPlugin(settings)


PLUGIN = PluginDescriptor(id="guard", api_version=2, settings_model=Settings, create=create)

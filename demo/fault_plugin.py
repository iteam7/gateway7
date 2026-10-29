"""Deliberately failing middleware used only by the synthetic demonstration."""

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import NextHandler, PluginContext, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    mode: Literal["error", "timeout", "late"] = "error"
    phase: Literal["request", "response"] = "request"


class FaultPlugin:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fail(self) -> None:
        if self.settings.mode == "timeout":
            await asyncio.sleep(0.3)
        elif self.settings.mode == "late":
            # Swallow the budget's cancellation and carry on as a misbehaving plugin would.
            try:
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                pass
        else:
            raise RuntimeError("synthetic-demo-exception-must-not-be-exposed")

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse:
        if self.settings.phase == "request":
            await self.fail()
        response = await call_next(request)
        if self.settings.phase == "response":
            await self.fail()
        return response


def create(settings: Settings) -> FaultPlugin:
    return FaultPlugin(settings)


PLUGIN = PluginDescriptor(id="demo-fault", api_version=2, settings_model=Settings, create=create)

"""Copy this one file to company_plugins/sample.py and configure its module.

Separate configured instances can use markers such as [A] and [B]. Each
middleware appends its marker before awaiting the next handler and after it
returns. Request order is forward; the returning response unwinds in reverse.
"""

from pydantic import BaseModel, ConfigDict

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import NextHandler, PluginContext, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    marker: str = "[checked-by-sample]"


class SamplePlugin:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def handle(
        self, request: ChatRequest, context: PluginContext, call_next: NextHandler
    ) -> ChatResponse:
        messages = [
            message.model_copy(update={"content": message.content + self.settings.marker})
            if message.role == "user"
            else message
            for message in request.messages
        ]
        response = await call_next(request.model_copy(update={"messages": messages}))
        return response.model_copy(update={"text": response.text + self.settings.marker})


def create(settings: Settings) -> SamplePlugin:
    return SamplePlugin(settings)


PLUGIN = PluginDescriptor(
    id="sample", api_version=2, settings_model=Settings, create=create
)

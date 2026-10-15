"""Copy this one file to company_plugins/sample.py and configure its module.

Separate configured instances can use markers such as [A] and [B]. Each
request hook appends its marker only to user messages; each response hook
appends it to response text. Chain order is therefore visible in both phases.
"""

from pydantic import BaseModel, ConfigDict

from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import Continue, PluginContext, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    marker: str = "[checked-by-sample]"


class SamplePlugin:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def on_request(
        self, request: ChatRequest, context: PluginContext
    ) -> Continue:
        messages = [
            message.model_copy(update={"content": message.content + self.settings.marker})
            if message.role == "user"
            else message
            for message in request.messages
        ]
        return Continue(payload=request.model_copy(update={"messages": messages}))

    async def on_response(
        self, response: ChatResponse, context: PluginContext
    ) -> Continue:
        return Continue(
            payload=response.model_copy(
                update={"text": response.text + self.settings.marker}
            )
        )


def create(settings: Settings) -> SamplePlugin:
    return SamplePlugin(settings)


PLUGIN = PluginDescriptor(
    id="sample", api_version=1, settings_model=Settings, create=create
)

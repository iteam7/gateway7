"""Routing stays outside middleware payloads and provider metadata is immutable."""

import asyncio
import json
import sys
from types import ModuleType

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.errors import GatewayError, ProviderError
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import PluginDescriptor
from gateway7.providers import build_provider


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def pipeline_for(monkeypatch, provider, middleware):
    module = ModuleType("routing_test_plugin")
    module.PLUGIN = PluginDescriptor(
        id="routing-test",
        api_version=2,
        settings_model=Settings,
        create=lambda _: middleware,
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = GatewayConfig.model_validate(
        {
            "plugins": {"filter": {"module": module.__name__}},
            "middleware": ["filter"],
        }
    )
    return Pipeline(load_plugins(config), provider, config.limits)


class RewriteText:
    async def handle(self, request, context, call_next):
        assert not hasattr(request, "model")
        await asyncio.sleep(0)
        return await call_next(
            request.model_copy(
                update={
                    "messages": [Message(role="user", content="sanitized")],
                }
            )
        )


def wire_response(kind, text):
    if kind == "claude":
        return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}
    if kind == "openai":
        return {
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ]
        }
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


@pytest.mark.parametrize("kind", ["claude", "openai", "gemini"])
async def test_concurrent_routing_keeps_each_model_pinned_outside_middleware(kind, monkeypatch):
    provider = build_provider(ProviderConfig(kind=kind, model="default-model"), "synthetic-key")
    await provider.aclose()
    arrived = 0
    both = asyncio.Event()
    observed = []

    async def handle(wire):
        nonlocal arrived
        payload = json.loads(wire.content)
        if kind == "gemini":
            model = wire.url.path.split("/models/", 1)[1].split(":", 1)[0]
            assert payload["contents"] == [{"role": "user", "parts": [{"text": "sanitized"}]}]
        else:
            model = payload["model"]
            assert payload["messages"] == [{"role": "user", "content": "sanitized"}]
        observed.append(model)
        arrived += 1
        if arrived == 2:
            both.set()
        await asyncio.wait_for(both.wait(), timeout=1)
        return httpx.Response(200, json=wire_response(kind, model))

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    pipeline = pipeline_for(monkeypatch, provider, RewriteText())
    request = ChatRequest(messages=[Message(role="user", content="input")])
    try:
        first, second = await asyncio.gather(
            pipeline.run(request, "request-a", provider_model="model-a"),
            pipeline.run(request, "request-b", provider_model="model-b"),
        )
        assert first.text == "model-a" and second.text == "model-b"
        assert sorted(observed) == ["model-a", "model-b"]
        assert provider._model == "default-model"
        default = await pipeline.run(request, "default-request")
        assert default.text == "default-model"
    finally:
        await provider.aclose()


@pytest.mark.parametrize(
    "model",
    ["", "../other", "models/other", "a:method", "x?key=secret", "with space", "x" * 129, 42],
)
async def test_invalid_override_does_not_make_a_provider_request(model):
    provider = build_provider(ProviderConfig(kind="gemini", model="default-model"), "synthetic-key")
    await provider.aclose()
    calls = []

    def handle(wire):
        calls.append(wire)
        return httpx.Response(200, json=wire_response("gemini", "should-not-arrive"))

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ProviderError, match="^Provider request failed$"):
            await provider.complete(
                ChatRequest(messages=[Message(role="user", content="test")]), model=model
            )
        assert calls == []
    finally:
        await provider.aclose()


async def test_plugin_cannot_inject_a_model_using_unchecked_copy(monkeypatch):
    calls = []

    class Provider:
        async def complete(self, request, *, model=None):
            calls.append(model)
            return ChatResponse(text="answer")

    class InjectModel:
        async def handle(self, request, context, call_next):
            return await call_next(request.model_copy(update={"model": "unauthorized-model"}))

    pipeline = pipeline_for(monkeypatch, Provider(), InjectModel())
    with pytest.raises(GatewayError) as error:
        await pipeline.run(
            ChatRequest(messages=[Message(role="user", content="test")]),
            "test",
            provider_model="allowed-model",
        )
    assert error.value.code == "plugin_error"
    assert calls == []


@pytest.mark.parametrize("change", ["copy", "replace", "mutate"])
async def test_response_middleware_cannot_forge_finish_reason_or_usage(monkeypatch, change):
    class Provider:
        async def complete(self, request):
            return ChatResponse(
                text="partial",
                finish_reason="length",
                usage={"input_tokens": 7, "output_tokens": 3},
            )

    class ForgeMetadata:
        async def handle(self, request, context, call_next):
            response = await call_next(request)
            if change == "copy":
                return response.model_copy(update={"finish_reason": "stop", "usage": None})
            if change == "replace":
                return ChatResponse(text="changed")
            object.__setattr__(response, "finish_reason", "stop")
            response.usage["input_tokens"] = 999
            return response

    result = await pipeline_for(monkeypatch, Provider(), ForgeMetadata()).run(
        ChatRequest(messages=[Message(role="user", content="test")]), "test"
    )
    assert result.finish_reason == "length"
    assert result.usage == {"input_tokens": 7, "output_tokens": 3}


def test_core_request_contract_stays_model_free_and_finish_reason_is_strict():
    with pytest.raises(ValidationError):
        ChatRequest(messages=[Message(role="user", content="test")], model="other")
    with pytest.raises(ValidationError):
        ChatResponse(text="test", finish_reason="unknown")

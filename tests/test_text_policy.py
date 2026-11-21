"""The public text adapter preserves the runner's Chat/native safety boundaries."""

import asyncio
import sys
from dataclasses import FrozenInstanceError
from types import ModuleType

import pytest
from pydantic import BaseModel, ConfigDict

from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import (
    EarlyStreamUnsupported,
    PluginDescriptor,
    ResponsesUnsupported,
)
from gateway7.responses_models import ResponsesConsent, ResponsesRequest, ResponsesResponse
from gateway7.text_policy import TextPolicyMiddleware


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


def transform(text):
    return text.replace("PRIVATE-TEST", "[removed]"), text.count("PRIVATE-TEST")


def native_response(text="answer PRIVATE-TEST", *, annotations=None):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_fixture",
            "created_at": 1800000000,
            "model": "model-a",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_fixture",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text, "annotations": annotations or []}
                    ],
                }
            ],
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
    )


class Provider:
    def __init__(self):
        self.calls = []
        self.native = native_response()

    async def complete(self, request, **options):
        self.calls.append(request)
        await asyncio.sleep(0)
        return ChatResponse(
            text="answer PRIVATE-TEST", usage={"input_tokens": 7, "output_tokens": 3}
        )

    async def complete_early(self, request, *, on_text, **options):
        result = await self.complete(request, **options)
        await on_text(result.text)
        return result

    async def complete_responses(self, request, **options):
        self.calls.append(request)
        await asyncio.sleep(0)
        return self.native

    async def complete_responses_early(self, request, *, on_text, **options):
        result = await self.complete_responses(request, **options)
        await on_text(result.output_text)
        return result


def runner(monkeypatch, policy, *, supports_tools=True):
    module = ModuleType("synthetic_text_policy")
    module.PLUGIN = PluginDescriptor(
        "text-policy", 2, Settings, lambda _: policy, supports_tools=supports_tools
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = GatewayConfig.model_validate(
        {
            "plugins": {"company_policy": {"module": module.__name__}},
            "middleware": ["company_policy"],
        }
    )
    provider = Provider()
    return Pipeline(load_plugins(config), provider, config.limits, provider_name="openai"), provider


@pytest.mark.parametrize("phase", ["request", "response", "both"])
@pytest.mark.parametrize("action", ["block", "redact"])
@pytest.mark.parametrize("native", [False, True])
async def test_adapter_phases_actions_and_untouched_provider_metadata(
    monkeypatch, phase, action, native
):
    policy = TextPolicyMiddleware(transform, phase=phase, action=action)
    before = dict(vars(policy))
    pipeline, provider = runner(monkeypatch, policy)
    request = (
        ResponsesRequest(input="ask PRIVATE-TEST")
        if native
        else ChatRequest(messages=[Message(role="user", content="ask PRIVATE-TEST")])
    )
    operation = pipeline.run_responses(request) if native else pipeline.run(request, "fixture")
    if action == "block":
        with pytest.raises(GatewayError) as error:
            await operation
        assert error.value.code == "policy_denied"
        assert error.value.middleware == "company_policy"
        assert len(provider.calls) == (1 if phase == "response" else 0)
    else:
        answer = await operation
        sent = provider.calls[0].input if native else provider.calls[0].messages[0].content
        text = answer.output_text if native else answer.text
        assert sent == ("ask [removed]" if phase in ("request", "both") else "ask PRIVATE-TEST")
        assert text == (
            "answer [removed]" if phase in ("response", "both") else "answer PRIVATE-TEST"
        )
        assert answer.usage.input_tokens == 7 if native else answer.usage["input_tokens"] == 7
        if native:
            assert answer.id == "resp_fixture" and answer.output[0].id == "msg_fixture"
        else:
            assert answer.finish_reason == "stop"
    assert vars(policy) == before


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("phase", ["request", "response", "both"])
async def test_early_requires_explicit_request_only_policy(monkeypatch, native, phase):
    pipeline, provider = runner(monkeypatch, TextPolicyMiddleware(transform, phase=phase))
    output = []

    async def receive(text):
        output.append(text)

    if native:
        operation = pipeline.run_responses_early(
            ResponsesRequest(input="PRIVATE-TEST"), on_text=receive
        )
    else:
        operation = pipeline.run_early(
            ChatRequest(messages=[Message(role="user", content="PRIVATE-TEST")]), on_text=receive
        )
    if phase == "request":
        await operation
        assert output == ["answer PRIVATE-TEST"] and len(provider.calls) == 1
    else:
        with pytest.raises(ResponsesUnsupported if native else EarlyStreamUnsupported):
            await operation
        assert provider.calls == output == []


@pytest.mark.parametrize("action", ["block", "redact"])
async def test_helper_never_rewrites_executable_chat_arguments_or_tool_schema(monkeypatch, action):
    pipeline, provider = runner(
        monkeypatch, TextPolicyMiddleware(transform, phase="request", action=action)
    )
    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "safe"}],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "read", "parameters": {"PRIVATE-TEST": "safe"}},
                }
            ],
        }
    )
    before = request.model_dump()
    with pytest.raises(GatewayError) as error:
        await pipeline.run(request, "fixture")
    assert error.value.code == "policy_denied" and provider.calls == []
    assert request.model_dump() == before


async def test_helper_does_not_implicitly_opt_descriptor_into_chat_tools(monkeypatch):
    pipeline, provider = runner(monkeypatch, TextPolicyMiddleware(transform), supports_tools=False)
    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "safe"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {}}}],
        }
    )
    with pytest.raises(GatewayError) as error:
        await pipeline.run(request, "fixture")
    assert error.value.code == "invalid_request" and provider.calls == []


async def test_native_opaque_data_stays_exact_and_protected_matches_deny(monkeypatch):
    pipeline, provider = runner(monkeypatch, TextPolicyMiddleware(transform, phase="request"))
    consent = ResponsesConsent(allow_opaque=True)
    request = ResponsesRequest.model_validate(
        {
            "input": [
                {"type": "reasoning", "encrypted_content": "PRIVATE-TEST"},
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "PRIVATE-TEST"},
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,UFJJVkFURS1URVNU",
                        },
                    ],
                },
            ]
        },
        context={"consent": consent},
    )
    before = request.model_dump()
    await pipeline.run_responses(request, consent=consent)
    sent = provider.calls[0]
    assert sent.input[0].encrypted_content == "PRIVATE-TEST"
    assert sent.input[1].content[0].text == "[removed]"
    assert sent.input[1].content[1].image_url == "data:image/png;base64,UFJJVkFURS1URVNU"
    assert request.model_dump() == before
    protected = ResponsesRequest(input="safe", client_metadata={"PRIVATE-TEST": "safe"})
    with pytest.raises(GatewayError) as error:
        await pipeline.run_responses(protected)
    assert error.value.code == "policy_denied" and len(provider.calls) == 1


async def test_native_annotations_are_not_shifted_by_redaction(monkeypatch):
    pipeline, provider = runner(monkeypatch, TextPolicyMiddleware(transform, phase="response"))
    provider.native = native_response(
        annotations=[
            {
                "type": "url_citation",
                "start_index": 7,
                "end_index": 19,
                "title": "fixture",
                "url": "https://fixture.invalid",
            }
        ]
    )
    original = provider.native.model_dump()
    with pytest.raises(GatewayError) as error:
        await pipeline.run_responses(ResponsesRequest(input="safe"))
    assert error.value.code == "policy_denied" and len(provider.calls) == 1
    assert provider.native.model_dump() == original


async def test_same_immutable_helper_is_safe_for_concurrent_requests(monkeypatch):
    helper = TextPolicyMiddleware(transform, phase="request")
    before = dict(vars(helper))
    pipeline, provider = runner(monkeypatch, helper)
    requests = [
        ChatRequest(messages=[Message(role="user", content=value)])
        for value in ("first PRIVATE-TEST", "second safe")
    ]
    await asyncio.gather(
        *(pipeline.run(request, str(index)) for index, request in enumerate(requests))
    )
    assert sorted(request.messages[0].content for request in provider.calls) == [
        "first [removed]",
        "second safe",
    ]
    assert requests[0].messages[0].content == "first PRIVATE-TEST"
    assert vars(helper) == before
    with pytest.raises(FrozenInstanceError):
        helper.phase = "both"


@pytest.mark.parametrize(
    "bad",
    [
        lambda text: (None, 1),
        lambda text: (text, True),
        lambda text: (text, -1),
        lambda text: ("changed", 0),
        lambda text: [text, 0],
    ],
)
async def test_invalid_transform_is_a_sanitized_plugin_failure_before_provider(
    monkeypatch, bad, caplog
):
    pipeline, provider = runner(monkeypatch, TextPolicyMiddleware(bad, phase="request"))
    with pytest.raises(GatewayError) as error:
        await pipeline.run(
            ChatRequest(messages=[Message(role="user", content="SYNTHETIC_PRIVATE_TEXT")]),
            "fixture",
        )
    assert error.value.code == "plugin_error" and provider.calls == []
    assert "SYNTHETIC_PRIVATE_TEXT" not in caplog.text + str(error.value)


def test_async_transform_is_rejected_without_running_it():
    async def unsupported(text):
        pytest.fail("Async transforms must not be executed")

    with pytest.raises(ValueError, match="synchronous"):
        TextPolicyMiddleware(unsupported)

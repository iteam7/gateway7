"""Synthetic-fixture coverage for the masking and drop-in example plugins."""

import asyncio
import importlib
import shutil
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from examples import sample_plugin
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.plugin_api import Continue, PluginContext
from gateway7.plugins import phone_mask


def context() -> PluginContext:
    return PluginContext(request_id="synthetic-plugin-test", deadline=time.monotonic() + 10, state={})


def apply_request(plugin, request: ChatRequest, plugin_context=None) -> ChatRequest:
    result = asyncio.run(plugin.on_request(request, plugin_context or context()))
    assert isinstance(result, Continue)
    assert isinstance(result.payload, ChatRequest)
    # The result remains a validated model tree, not a list of raw dicts.
    assert all(isinstance(message, Message) for message in result.payload.messages)
    return ChatRequest.model_validate(result.payload.model_dump())


def test_phone_mask_covers_entire_history_without_changing_roles_or_other_text(caplog):
    original = ChatRequest(
        messages=[
            Message(role="system", content="Contact +7 900 000-00-00."),
            Message(role="user", content="Earlier number: 8 (900) 000-00-00."),
            Message(role="assistant", content="You said +79000000000."),
            Message(role="user", content="Order ORDER-2026-1001 shipped on 2026-10-08"),
        ],
        max_tokens=37,
    )
    before = original.model_dump()
    plugin = phone_mask.PLUGIN.create(phone_mask.Settings())
    plugin_context = context()

    masked = apply_request(plugin, original, plugin_context)

    assert masked.model_dump() == {
        "messages": [
            {"role": "system", "content": "Contact [PHONE]."},
            {"role": "user", "content": "Earlier number: [PHONE]."},
            {"role": "assistant", "content": "You said [PHONE]."},
            {"role": "user", "content": "Order ORDER-2026-1001 shipped on 2026-10-08"},
        ],
        "max_tokens": 37,
    }
    assert original.model_dump() == before
    assert plugin_context.state == {}
    assert vars(plugin) == {}
    assert caplog.text == ""


@pytest.mark.parametrize(
    "content",
    [
        "Order ORDER-2026-1001 shipped on 2026-10-08",
        "ID+79000000000",
        "+79000000000suffix",
        "123+79000000000",
        "+790000000001",
        "18 (900) 000-00-00",
        "8 (900) 000-00-001",
        "item_8 (900) 000-00-00",
        "+7 900 000-00-00_extra",
        "++79000000000",
        "+7-900-000-00-00",  # Outside this deliberately narrow demo detector.
        "8 900 000-00-00",
        "+7９０００００００００",  # Only ASCII digits are supported.
    ],
)
def test_phone_mask_preserves_nonmatches(content):
    request = ChatRequest(messages=[Message(role="user", content=content)])
    plugin = phone_mask.PLUGIN.create(phone_mask.Settings())
    assert apply_request(plugin, request) == request


def test_phone_mask_handles_punctuation_and_is_idempotent():
    request = ChatRequest(
        messages=[
            Message(
                role="user",
                content="(+7 900 000-00-00), [8 (900) 000-00-00]; '+79000000000'!",
            )
        ]
    )
    plugin = phone_mask.PLUGIN.create(phone_mask.Settings())
    masked = apply_request(plugin, request)
    assert masked.messages[0].content == "([PHONE]), [[PHONE]]; '[PHONE]'!"
    assert apply_request(plugin, masked) == masked


def test_sample_instances_show_request_order_and_preserve_non_user_messages():
    first = sample_plugin.PLUGIN.create(sample_plugin.Settings(marker="[A]"))
    second = sample_plugin.PLUGIN.create(sample_plugin.Settings(marker="[B]"))
    request = ChatRequest(
        messages=[
            Message(role="system", content="System"),
            Message(role="user", content="Earlier"),
            Message(role="assistant", content="Answer"),
            Message(role="user", content="Latest"),
        ],
        max_tokens=17,
    )

    forward = apply_request(second, apply_request(first, request))
    reverse = apply_request(first, apply_request(second, request))

    assert [message.content for message in forward.messages] == [
        "System", "Earlier[A][B]", "Answer", "Latest[A][B]"
    ]
    assert [message.content for message in reverse.messages] == [
        "System", "Earlier[B][A]", "Answer", "Latest[B][A]"
    ]
    assert [message.role for message in forward.messages] == [
        message.role for message in request.messages
    ]
    assert forward.max_tokens == 17
    assert request.messages[-1].content == "Latest"


def test_sample_response_chain_can_use_a_different_order():
    first = sample_plugin.PLUGIN.create(sample_plugin.Settings(marker="[A]"))
    second = sample_plugin.PLUGIN.create(sample_plugin.Settings(marker="[B]"))
    response = ChatResponse(text="Synthetic answer", usage={"total_tokens": 3})

    async def respond():
        second_result = await second.on_response(response, context())
        return await first.on_response(second_result.payload, context())

    result = asyncio.run(respond())
    assert result.payload == ChatResponse(
        text="Synthetic answer[B][A]", usage={"total_tokens": 3}
    )
    assert response.text == "Synthetic answer"


def test_sample_can_load_as_one_file_in_a_company_namespace(tmp_path, monkeypatch):
    company_plugins = tmp_path / "company_plugins"
    company_plugins.mkdir()
    source = Path(__file__).resolve().parents[1] / "examples" / "sample_plugin.py"
    shutil.copyfile(source, company_plugins / "sample.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    # Avoid any other test's demo copy deciding which module this import loads.
    saved = {
        key: sys.modules.pop(key)
        for key in ("company_plugins.sample", "company_plugins")
        if key in sys.modules
    }
    try:
        module = importlib.import_module("company_plugins.sample")
        plugin = module.PLUGIN.create(module.PLUGIN.settings_model.model_validate({}))
        request = ChatRequest(messages=[Message(role="user", content="Hello")])
        assert apply_request(plugin, request).messages[0].content == "Hello[checked-by-sample]"
        assert not (company_plugins / "__init__.py").exists()
    finally:
        sys.modules.pop("company_plugins.sample", None)
        sys.modules.pop("company_plugins", None)
        sys.modules.update(saved)


@pytest.mark.parametrize("settings_model", [phone_mask.Settings, sample_plugin.Settings])
def test_plugin_settings_reject_unknown_keys(settings_model):
    with pytest.raises(ValidationError):
        settings_model.model_validate({"unknown": True})


def test_sample_settings_reject_non_string_markers():
    with pytest.raises(ValidationError):
        sample_plugin.Settings(marker=123)

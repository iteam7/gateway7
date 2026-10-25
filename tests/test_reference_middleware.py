"""Synthetic contract tests for the reusable reference middleware catalog."""

import logging
import time

import pytest
from pydantic import ValidationError

from gateway7.config import GatewayConfig, LimitsConfig, PluginConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import PluginContext
from gateway7.plugins import content_policy, email_mask


class RecordingProvider:
    def __init__(self, text="Synthetic reply"):
        self.requests = []
        self.response = ChatResponse(text=text, usage={"input_tokens": 8, "output_tokens": 5})

    async def complete(self, request):
        self.requests.append(request)
        return self.response


def pipeline(module, settings, provider, *, name="reference"):
    config = GatewayConfig(
        plugins={name: PluginConfig(module=module, settings=settings)},
        middleware=[name],
    )
    return Pipeline(load_plugins(config), provider, LimitsConfig())


def request(text):
    return ChatRequest(messages=[Message(role="user", content=text)])


@pytest.mark.parametrize("value", [
    "user@example.com", "first.last+tag@sub.example.org", "O'Hara@example.net",
    "someone@x.co", "UPPER.CASE@EXAMPLE.COM", "a_b%tag@my-domain.example",
])
async def test_email_masks_supported_addresses_through_entire_history_and_output(value):
    messages = [Message(role=role, content=f"Contact <{value}>.") for role in ("system", "user", "assistant")]
    original = ChatRequest(messages=messages, max_tokens=37)
    before = original.model_dump()
    provider = RecordingProvider(f"Reply to {value}.")
    runner = pipeline("gateway7.plugins.email_mask", {}, provider)
    answer = await runner.run(original, "synthetic-email")
    assert [item.content for item in provider.requests[0].messages] == ["Contact <[EMAIL]>."] * 3
    assert [item.role for item in provider.requests[0].messages] == ["system", "user", "assistant"]
    assert provider.requests[0].max_tokens == 37
    assert answer.text == "Reply to [EMAIL]."
    assert answer.usage == provider.response.usage
    assert original.model_dump() == before
    assert provider.response.text == f"Reply to {value}."


@pytest.mark.parametrize("value", [
    "ORDER-2026-1001", "2026-10-25", "name@localhost", "not-an-email",
    "a..b@example.com", ".a@example.com", "a.@example.com", "a@-example.com",
    "a@example-.com", "a@127.0.0.1", '"quoted local"@example.com',
    "почта@example.com", "name@пример.рф", "кириллицаuser@example.com",
    "user@example.comхвост", "a@example.c", "@a@example.com",
    "a" * 65 + "@example.com", "a." * 33 + "a@example.com",
    "a@" + "b" * 64 + ".com", "a@" + ".".join(["b" * 63] * 4) + ".com",
])
async def test_email_preserves_nonmatches_without_masking_partial_identifiers(value):
    provider = RecordingProvider(value)
    answer = await pipeline("gateway7.plugins.email_mask", {}, provider).run(request(value), "synthetic-nonmatch")
    assert provider.requests[0].messages[0].content == value
    assert answer.text == value


async def test_email_punctuation_quotes_multiple_addresses_and_idempotence():
    content = '"user@example.com", (other@example.net); [third@example.org].'
    once = email_mask.mask_email(content, "[EMAIL]")
    assert once == '"[EMAIL]", ([EMAIL]); [[EMAIL]].'
    assert email_mask.mask_email(once, "[EMAIL]") == once


@pytest.mark.parametrize("module,value,marker", [
    ("gateway7.plugins.phone_mask", "+7 900 000-00-00", "[PHONE]"),
    ("gateway7.plugins.email_mask", "user@example.com", "[EMAIL]"),
])
@pytest.mark.parametrize("phase", ["request", "response", "both"])
async def test_phase_controls_both_maskers_independently(module, value, marker, phase):
    provider = RecordingProvider(value)
    answer = await pipeline(module, {"phase": phase}, provider).run(request(value), "synthetic-phase")
    assert provider.requests[0].messages[0].content == (marker if phase in ("request", "both") else value)
    assert answer.text == (marker if phase in ("response", "both") else value)


async def test_phone_empty_settings_still_only_mask_request():
    provider = RecordingProvider("+79000000000")
    answer = await pipeline("gateway7.plugins.phone_mask", {}, provider).run(request("+79000000000"), "synthetic-default")
    assert provider.requests[0].messages[0].content == "[PHONE]"
    assert answer.text == "+79000000000"


@pytest.mark.parametrize("module,value", [
    ("gateway7.plugins.phone_mask", "+79000000000"),
    ("gateway7.plugins.email_mask", "user@example.com"),
])
async def test_replacements_are_literal_not_regex_backreferences(module, value):
    provider = RecordingProvider(value)
    marker = r"[redacted\1]"
    answer = await pipeline(module, {"phase": "both", "replacement": marker}, provider).run(request(value), "synthetic-literal")
    assert provider.requests[0].messages[0].content == marker
    assert answer.text == marker


async def test_request_policy_blocks_any_history_role_before_provider(caplog):
    caplog.set_level(logging.INFO, logger="gateway7")
    provider = RecordingProvider()
    messages = [Message(role="system", content="BLOCK-ME-TEST"), Message(role="user", content="Allowed latest")]
    with pytest.raises(GatewayError) as caught:
        await pipeline("gateway7.plugins.content_policy", {
            "terms": ["BLOCK-ME-TEST"], "phase": "request", "action": "block",
        }, provider, name="company_guard").run(ChatRequest(messages=messages), "synthetic-block")
    assert caught.value.code == "policy_denied"
    assert provider.requests == []
    assert "BLOCK-ME-TEST" not in caplog.text
    assert "action=block" in caplog.text
    assert "component=company_guard" in caplog.text


async def test_response_policy_blocks_delivery_after_exactly_one_provider_call():
    provider = RecordingProvider("SECRET-TEST")
    with pytest.raises(GatewayError) as caught:
        await pipeline("gateway7.plugins.content_policy", {
            "terms": ["SECRET-TEST"], "phase": "response", "action": "block",
        }, provider).run(request("Allowed request"), "synthetic-output-block")
    assert caught.value.code == "policy_denied"
    assert len(provider.requests) == 1


async def test_log_policy_keeps_both_payloads_unchanged_and_logs_only_metadata(caplog):
    caplog.set_level(logging.INFO, logger="gateway7")
    marker = "SYNTHETIC-PRIVATE-TERM"
    provider = RecordingProvider(f"Response {marker}")
    original = request(f"Request {marker} and {marker}")
    answer = await pipeline("gateway7.plugins.content_policy", {
        "terms": [marker], "action": "log", "phase": "both",
    }, provider, name="audit_only").run(original, "synthetic-log")
    assert provider.requests[0] == original
    assert answer == provider.response
    assert marker not in caplog.text
    policy_logs = [record.message for record in caplog.records if "outcome=policy_match" in record.message]
    assert len(policy_logs) == 2
    assert any("phase=request action=log matches=2" in item for item in policy_logs)
    assert any("phase=response action=log matches=1" in item for item in policy_logs)
    assert all("component=audit_only" in item for item in policy_logs)


async def test_redaction_handles_literal_regex_symbols_overlaps_and_preserves_usage():
    provider = RecordingProvider("A+B and A+B+C and SECRET-TEST")
    runner = pipeline("gateway7.plugins.content_policy", {
        "terms": ["A+B", "A+B+C", "SECRET-TEST"], "action": "redact", "phase": "response",
    }, provider)
    answer = await runner.run(request("A+B"), "synthetic-redact")
    assert provider.requests[0].messages[0].content == "A+B"
    assert answer.text == "[removed] and [removed] and [removed]"
    assert answer.usage == {"input_tokens": 8, "output_tokens": 5}
    assert provider.response.text == "A+B and A+B+C and SECRET-TEST"


async def test_request_redaction_preserves_history_roles_and_generation_options():
    provider = RecordingProvider("Allowed")
    original = ChatRequest(messages=[Message(role=role, content="SECRET-TEST") for role in ("system", "user", "assistant")], max_tokens=29)
    await pipeline("gateway7.plugins.content_policy", {
        "terms": ["SECRET-TEST"], "action": "redact", "phase": "request", "replacement": r"redacted\1",
    }, provider).run(original, "synthetic-redact-history")
    assert provider.requests[0].max_tokens == 29
    assert [item.role for item in provider.requests[0].messages] == ["system", "user", "assistant"]
    assert [item.content for item in provider.requests[0].messages] == [r"redacted\1"] * 3
    assert original.messages[0].content == "SECRET-TEST"


@pytest.mark.parametrize("case_sensitive,expected", [(True, "secret-test"), (False, "[removed]")])
async def test_literal_policy_case_matching_is_explicit(case_sensitive, expected):
    provider = RecordingProvider("secret-test")
    answer = await pipeline("gateway7.plugins.content_policy", {
        "terms": ["SECRET-TEST"], "action": "redact", "case_sensitive": case_sensitive,
    }, provider).run(request("safe"), "synthetic-case")
    assert answer.text == expected


async def test_allowed_policy_preserves_request_and_response(caplog):
    caplog.set_level(logging.INFO, logger="gateway7")
    provider = RecordingProvider("Ordinary response")
    original = request("Ordinary request")
    answer = await pipeline("gateway7.plugins.content_policy", {
        "terms": ["BLOCK-ME-TEST"], "action": "block",
    }, provider).run(original, "synthetic-allow")
    assert provider.requests[0] == original
    assert answer == provider.response
    assert "outcome=policy_match" not in caplog.text


@pytest.mark.parametrize("module,settings", [
    ("gateway7.plugins.email_mask", {"phase": "before"}),
    ("gateway7.plugins.email_mask", {"replacement": ""}),
    ("gateway7.plugins.email_mask", {"replacement": 1}),
    ("gateway7.plugins.phone_mask", {"phase": "after"}),
    ("gateway7.plugins.phone_mask", {"replacement": "x" * 129}),
    ("gateway7.plugins.content_policy", {"terms": ["SECRET-TEST"], "action": "explode"}),
    ("gateway7.plugins.content_policy", {"terms": []}),
    ("gateway7.plugins.content_policy", {"terms": [""]}),
    ("gateway7.plugins.content_policy", {"terms": [" "]}),
    ("gateway7.plugins.content_policy", {"terms": ["one", "one"]}),
    ("gateway7.plugins.content_policy", {"terms": ["x" * 257]}),
    ("gateway7.plugins.content_policy", {"terms": [str(n) for n in range(33)]}),
    ("gateway7.plugins.content_policy", {"terms": [1]}),
    ("gateway7.plugins.content_policy", {"terms": ["term"], "case_sensitive": "true"}),
    ("gateway7.plugins.content_policy", {"terms": ["term"], "regex": True}),
])
def test_invalid_reference_settings_fail_at_startup_without_echoing_values(module, settings):
    config = GatewayConfig(plugins={"guard": PluginConfig(module=module, settings=settings)}, middleware=["guard"])
    with pytest.raises(StartupError, match="^Invalid settings for plugin instance guard$"):
        load_plugins(config)


async def test_instances_hold_only_immutable_configuration_not_originals_or_request_state(caplog):
    context = PluginContext("synthetic-state", time.monotonic() + 10, {}, "guard")
    plugin = content_policy.create(content_policy.Settings(terms=["SECRET-TEST"], action="redact"))
    provider = RecordingProvider("SECRET-TEST")
    answer = await plugin.handle(request("SECRET-TEST"), context, provider.complete)
    assert answer.text == "[removed]"
    assert context.state == {}
    assert plugin.settings.terms == ("SECRET-TEST",)
    with pytest.raises(ValidationError):
        plugin.settings.action = "log"
    assert set(vars(plugin)) == {"settings", "pattern"}

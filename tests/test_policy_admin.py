"""Data-only policy edits preserve durable bindings and real middleware contracts."""

import json
import os

import pytest
from pydantic import ValidationError

from gateway7.admin_runtime import CreateClient
from gateway7.admin_store import AdminStore
from gateway7.client_policies import build_client_pipelines
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_auth import OperatorPrincipal
from gateway7.identity_admin import KeyRequest
from gateway7.loader import load_plugins
from gateway7.models import ChatRequest, Message
from gateway7.pipeline import Pipeline
from gateway7.policy_admin import (
    PolicyAdmin,
    PolicyAssignments,
    PolicyPreview,
    PolicySpec,
    restore_policy_config,
    validate_policy_document,
)
from gateway7.postgres_store import PostgresAdminStore
from gateway7.responses_models import ResponsesRequest
from test_identity_admin import identity as identity_fixture, options
from test_usage import AccountingProvider, MODES

identity = identity_fixture


def spec(identity="guard", **values):
    return PolicySpec.model_validate(
        {
            "id": identity,
            "label": "Synthetic policy",
            "template": "literal_guard",
            "phase": "request",
            "terms": ["PRIVATE"],
            **values,
        }
    )


def assignments(global_=(), **clients):
    return PolicyAssignments.model_validate({"global": list(global_), "clients": clients})


async def prepare(identity):
    manager, state = identity
    await manager.create(CreateClient(id="developer"), **options(state))
    return manager, state, PolicyAdmin(state)


async def invoke(pipeline, mode, text="PRIVATE"):
    async def discard(_):
        pass

    chat = ChatRequest(messages=[Message(role="user", content=text)])
    native = ResponsesRequest(input=text)
    if mode == "chat":
        return await pipeline.run(chat, "synthetic-policy-request")
    if mode == "early_chat":
        return await pipeline.run_early(chat, "synthetic-policy-request", on_text=discard)
    if mode == "responses":
        return await pipeline.run_responses(native, "synthetic-policy-request")
    return await pipeline.run_responses_early(native, "synthetic-policy-request", on_text=discard)


@pytest.mark.parametrize("mode", MODES)
async def test_hot_guard_and_update_use_real_pipeline_and_keep_admitted_snapshot(identity, mode):
    _, state, policies = await prepare(identity)
    state.pipeline.provider = AccountingProvider(text="safe answer")
    state.pipeline.provider_name = "openai"
    provider = state.pipeline.provider
    await policies.create(spec(), **options(state))
    await policies.assignments(assignments(developer=["guard"]), **options(state))
    admitted = state.client_pipelines["developer"]
    with pytest.raises(GatewayError) as caught:
        await invoke(admitted, mode)
    assert caught.value.code == "policy_denied" and provider.calls == 0
    await policies.update("guard", spec(terms=["different"]), **options(state))
    await invoke(state.client_pipelines["developer"], mode)
    assert provider.calls == 1
    with pytest.raises(GatewayError) as caught:
        await invoke(admitted, mode)
    assert caught.value.code == "policy_denied" and provider.calls == 1


async def test_global_and_client_order_preserves_configured_plugins_without_recreating_them(
    identity,
):
    manager, state = identity
    data = state.config.model_dump()
    data["plugins"] = {
        "static_required": {"module": "gateway7.plugins.phone_mask", "required": True},
        "static_client": {"module": "gateway7.plugins.email_mask"},
    }
    data["middleware"] = ["static_required"]
    state.config = GatewayConfig.model_validate(data)
    state.pipeline.plugins = load_plugins(state.config)
    await manager.create(
        CreateClient(id="developer", additional_middleware=["static_client"]), **options(state)
    )
    original = dict(state.pipeline.plugins.instances)
    policies = PolicyAdmin(state)
    await policies.create(spec("global_guard"), **options(state))
    await policies.create(spec("private_guard"), **options(state))
    await policies.assignments(
        assignments(["global_guard"], developer=["private_guard"]), **options(state)
    )
    assert state.config.middleware == ["static_required", "policy_global_guard"]
    assert state.config.auth.clients["developer"].additional_middleware == [
        "static_client",
        "policy_private_guard",
    ]
    assert [
        plugin.name for plugin in state.client_pipelines["developer"].plugins.middleware_chain
    ] == ["static_required", "policy_global_guard", "static_client", "policy_private_guard"]
    assert all(state.pipeline.plugins.instances[name] is value for name, value in original.items())
    await policies.assignments(assignments(), **options(state))
    assert state.config.middleware == ["static_required"]
    assert state.config.auth.clients["developer"].additional_middleware == ["static_client"]
    assert all(state.pipeline.plugins.instances[name] is value for name, value in original.items())


async def test_persistence_restart_backup_and_unrelated_identity_updates_preserve_policy_bindings(
    identity,
):
    manager, state, policies = await prepare(identity)
    seed = state.config
    await policies.create(spec(), **options(state))
    await policies.assignments(assignments(developer=["guard"]), **options(state))
    await manager.create_key("developer", KeyRequest(), **options(state))
    assert state.config.auth.clients["developer"].additional_middleware == ["policy_guard"]
    control = await state.db.call(state.admin_store.read_control)
    backup = await state.db.call(state.admin_store.backup_snapshot)
    clients, _ = await state.db.call(state.admin_store.load_clients)
    postgres = state.admin_store._backend_postgres
    address = (
        os.environ["GATEWAY7_TEST_POSTGRES_DSN"]
        if postgres
        else state.admin_store._db.execute("PRAGMA database_list").fetchone()[2]
    )
    await state.db.call(state.admin_store.close)
    restarted = await state.db.call(
        PostgresAdminStore if postgres else AdminStore, address, GatewayConfig()
    )
    try:
        assert await state.db.call(restarted.read_control) == control
        assert await state.db.call(restarted.backup_snapshot) == backup
        data = seed.model_dump()
        data["auth"]["clients"] = {name: row.model_dump() for name, row in clients.items()}
        restored = restore_policy_config(GatewayConfig.model_validate(data), control)
        loaded = load_plugins(restored)
        assert loaded.instances["policy_guard"].descriptor.supports_tools
        assert restored.auth.clients["developer"].additional_middleware == ["policy_guard"]
    finally:
        await state.db.call(restarted.close)
    if postgres:
        import psycopg

        with psycopg.connect(address, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
    destination = await state.db.call(
        PostgresAdminStore if postgres else AdminStore,
        address if postgres else address + ".restored",
        GatewayConfig(),
    )
    try:
        await state.db.call(destination.restore_backup, backup)
        assert await state.db.call(destination.backup_snapshot) == backup
        restored = restore_policy_config(GatewayConfig.model_validate(data), control)
        provider = AccountingProvider(text="safe answer")
        loaded = load_plugins(restored)
        pipeline = Pipeline(loaded, provider, restored.limits, provider_name="openai")
        pipelines = build_client_pipelines(restored, loaded, pipeline)
        with pytest.raises(GatewayError) as caught:
            await invoke(pipelines["developer"], "chat")
        assert caught.value.code == "policy_denied" and provider.calls == 0
    finally:
        await state.db.call(destination.close)


async def test_revision_roles_delete_conflicts_and_audit_do_not_leak_terms(identity):
    _, state, policies = await prepare(identity)
    before = state.control["revision"]
    await policies.create(spec(terms=["synthetic-private-term"]), **options(state))
    with pytest.raises(GatewayError) as caught:
        await policies.update("guard", spec(), **{**options(state), "expected_revision": before})
    assert caught.value.code == "conflict"
    with pytest.raises(GatewayError) as caught:
        await policies.create(
            spec("other"), **{**options(state), "actor": OperatorPrincipal("viewer", "viewer")}
        )
    assert caught.value.code == "operator_forbidden"
    await policies.assignments(assignments(["guard"]), **options(state))
    with pytest.raises(GatewayError) as caught:
        await policies.delete("guard", **options(state))
    assert caught.value.code == "conflict"
    audit = await state.db.call(state.admin_store.list_audit)
    assert "synthetic-private-term" not in json.dumps(audit)
    assert any(row["action"] == "policy.assign" for row in audit["items"])
    await policies.assignments(assignments(), **options(state))
    result = await policies.delete("guard", **options(state))
    assert result["items"] == []


async def test_storage_failure_never_publishes_candidate(identity, monkeypatch):
    _, state, policies = await prepare(identity)
    previous = (state.config, state.pipeline, state.control, state.access)

    def fail(*args, **kwargs):
        raise StartupError("Synthetic storage unavailable")

    monkeypatch.setattr(state.admin_store, "write_control", fail)
    with pytest.raises(GatewayError) as caught:
        await policies.create(spec(), **options(state))
    assert caught.value.code == "unavailable"
    assert (state.config, state.pipeline, state.control, state.access) == previous
    assert await state.db.call(state.admin_store.read_control) == previous[2]


@pytest.mark.parametrize(
    "template,text,expected",
    [
        ("literal_guard", "a PRIVATE word", None),
        ("literal_redact", "a PRIVATE word", "a [REDACTED] word"),
        ("email_mask", "person@example.test", "[EMAIL]"),
        ("phone_mask", "+79991234567", "[PHONE]"),
    ],
)
def test_preview_uses_real_pure_factory_without_persisting_or_provider(template, text, expected):
    payload = spec(template=template, terms=["PRIVATE"] if template.startswith("literal") else [])
    result = PolicyAdmin.preview(PolicyPreview(spec=payload, text=text))
    assert result["text"] == expected and result["matched"] == 1
    assert result["provider_calls"] == 0 and result["scope"] == "plain_text_only"


@pytest.mark.parametrize(
    "value",
    [
        {"module": "os"},
        {"code": "print('no')"},
        {"template": "regex"},
        {"terms": []},
        {"terms": [" "]},
        {"terms": ["PRIVATE", "PRIVATE"]},
        {"terms": ["a" * 129]},
        {"id": "a" * 57},
        {"replacement": "unexpected"},
        {"phase": "log"},
        {"action": "log"},
    ],
)
def test_closed_policy_spec_rejects_arbitrary_code_and_unbounded_or_ambiguous_input(value):
    with pytest.raises(ValidationError):
        spec(**value)


def test_literal_regex_characters_are_literal_and_replacement_is_not_interpolated():
    result = PolicyAdmin.preview(
        PolicyPreview(
            spec=spec(template="literal_redact", terms=["a.*"], replacement=r"\1"),
            text="a.* and abc",
        )
    )
    assert result["text"] == r"\1 and abc"


def test_persisted_policy_validation_and_source_name_collision_fail_closed():
    document = {
        "version": 1,
        "definitions": {"guard": {**spec().model_dump(), "action": "deny"}},
        "global": ["guard"],
    }
    normalized = validate_policy_document(document)
    for changed in ({**document, "version": True}, {**document, "global": ["missing"]}):
        with pytest.raises(ValueError):
            validate_policy_document(changed)
    config = GatewayConfig.model_validate(
        {"plugins": {"policy_guard": {"module": "gateway7.plugins.phone_mask"}}}
    )
    with pytest.raises(StartupError):
        restore_policy_config(config, {"data": {"policies": normalized}})


class RecordingProvider(AccountingProvider):
    received = None

    async def complete(self, request, **options):
        self.received = request
        return await super().complete(request, **options)

    async def complete_early(self, request, **options):
        self.received = request
        return await super().complete_early(request, **options)

    async def complete_responses(self, request, **options):
        self.received = request
        return await super().complete_responses(request, **options)

    async def complete_responses_early(self, request, **options):
        self.received = request
        return await super().complete_responses_early(request, **options)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "template,text,expected",
    [
        ("literal_redact", "PRIVATE data", "[REDACTED] data"),
        ("email_mask", "person@example.test", "[EMAIL]"),
        ("phone_mask", "+79991234567", "[PHONE]"),
    ],
)
async def test_mask_templates_change_actual_provider_input_in_every_api_mode(
    identity, mode, template, text, expected
):
    _, state, policies = await prepare(identity)
    state.pipeline.provider = provider = RecordingProvider(text="safe answer")
    state.pipeline.provider_name = "openai"
    await policies.create(
        spec(template=template, terms=["PRIVATE"] if template.startswith("literal") else []),
        **options(state),
    )
    await policies.assignments(assignments(["guard"]), **options(state))
    await invoke(state.client_pipelines["developer"], mode, text)
    assert provider.calls == 1
    value = provider.received
    assert (
        value.messages[0].content if isinstance(value, ChatRequest) else value.input
    ) == expected


@pytest.mark.parametrize("mode", ["early_chat", "early_responses"])
@pytest.mark.parametrize("phase", ["response", "both"])
async def test_response_policies_keep_early_streaming_unsupported_before_provider(
    identity, mode, phase
):
    from gateway7.plugin_api import EarlyStreamUnsupported, ResponsesUnsupported

    _, state, policies = await prepare(identity)
    state.pipeline.provider = provider = RecordingProvider(text="PRIVATE answer")
    state.pipeline.provider_name = "openai"
    await policies.create(spec(template="literal_redact", phase=phase), **options(state))
    await policies.assignments(assignments(["guard"]), **options(state))
    with pytest.raises(EarlyStreamUnsupported if mode == "early_chat" else ResponsesUnsupported):
        await invoke(state.client_pipelines["developer"], mode, "safe input")
    assert provider.calls == 0


@pytest.mark.parametrize("native", [False, True])
async def test_redaction_never_rewrites_executable_tool_payloads(identity, native):
    _, state, policies = await prepare(identity)
    state.pipeline.provider = provider = RecordingProvider(text="safe answer")
    state.pipeline.provider_name = "openai"
    await policies.create(spec(template="literal_redact"), **options(state))
    await policies.assignments(assignments(["guard"]), **options(state))
    pipeline = state.client_pipelines["developer"]
    tool = {
        "name": "PRIVATE_lookup",
        "description": "Safe tool description",
        "parameters": {"type": "object"},
    }
    with pytest.raises(GatewayError) as caught:
        if native:
            request = ResponsesRequest.model_validate(
                {"input": "safe", "tools": [{"type": "function", **tool}]}
            )
            await pipeline.run_responses(request, "synthetic-protected-tool")
        else:
            request = ChatRequest.model_validate(
                {
                    "messages": [{"role": "user", "content": "safe"}],
                    "tools": [{"type": "function", "function": tool}],
                }
            )
            await pipeline.run(request, "synthetic-protected-tool")
    assert caught.value.code == "policy_denied" and provider.calls == 0

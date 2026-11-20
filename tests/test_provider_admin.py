"""Live provider updates keep encrypted durable state and runtime publication coherent."""

import asyncio
import hashlib
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest

from gateway7.admin_store import AdminStore
from gateway7.config import GatewayConfig
from gateway7.control_store import ControlConflict
from gateway7.errors import GatewayError, StartupError, ProviderError, ProviderErrorReason
from gateway7.identity_auth import OperatorPrincipal
from gateway7.loader import LoadedPlugins
from gateway7.metrics import Metrics
from gateway7.models import ChatResponse
from gateway7.pipeline import Pipeline
from gateway7.provider_admin import ProviderAdmin, ProviderUpdate, restore_provider_config

OLD_KEY = "synthetic-provider-admin-old-key"
NEW_KEY = "synthetic-provider-admin-new-key"
OPERATOR_KEY = "synthetic-provider-admin-operator"
ACTOR = OperatorPrincipal("bootstrap", "admin", is_bootstrap=True)


class Database:
    async def call(self, function, *args, **kwargs):
        return await asyncio.to_thread(function, *args, **kwargs)


class Provider:
    def __init__(self, *, reachable=True):
        self.closed = False
        self.reachable = reachable
        self.calls = 0

    async def complete(self, request, **options):
        self.calls += 1
        if not self.reachable:
            raise TimeoutError
        return ChatResponse(
            text="synthetic connection check", usage={"input_tokens": 1, "output_tokens": 1}
        )

    async def aclose(self):
        self.closed = True


@pytest.fixture
def managed_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_ADMIN_KEY", OLD_KEY)
    monkeypatch.setenv("PROVIDER_ADMIN_OPERATOR", OPERATOR_KEY)
    monkeypatch.setenv("GATEWAY7_CONTROL_KEY", Fernet.generate_key().decode())
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "key_env": "PROVIDER_ADMIN_KEY", "model": "fake"},
            "auth": {
                "enabled": True,
                "management_db": str(tmp_path / "admin.db"),
                "operator_token_env": "PROVIDER_ADMIN_OPERATOR",
            },
        }
    )
    store = AdminStore(str(tmp_path / "admin.db"), config)
    store.write_control(
        0,
        {"identity": {"users": {}, "keys": {}, "operators": {}}},
        {"actor": "bootstrap", "action": "identity.initialize", "target": "identity", "diff": {}},
    )
    provider = Provider()
    state = SimpleNamespace(
        config=config,
        admin_store=store,
        db=Database(),
        metrics=Metrics(),
        token_digests={},
        management_mutation_lock=asyncio.Lock(),
        control=store.read_control(),
        provider_aliases={},
    )
    state.pipeline = Pipeline(
        LoadedPlugins({}, ()), provider, config.limits, metrics=state.metrics, provider_name="fake"
    )
    state.admission = SimpleNamespace(update=lambda value: None)
    state.retired = []
    state.retire_provider = state.retired.append
    state.created = []

    def factory(config, key, **options):
        created = Provider()
        state.created.append(created)
        return created

    state.provider_factory = factory
    try:
        yield state, ProviderAdmin(state), store
    finally:
        store.close()


def update(**changes):
    return ProviderUpdate(
        kind="fake",
        model="alternate",
        allowed_models=["alternate"],
        aliases={"team-model": "alternate"},
        **changes,
    )


async def test_live_provider_encrypts_secret_and_restores_without_plaintext_leak(
    managed_provider, monkeypatch
):
    state, service, store = managed_provider
    original = state.pipeline.provider
    result = await service.update(update(credential=NEW_KEY), 1, ACTOR)
    assert result["provider"]["model"] == "alternate"
    assert state.pipeline.provider is state.created[0]
    assert state.retired == [original] and not original.closed
    assert state.provider_aliases == {"team-model": "alternate"}
    control = store.read_control()
    audit = store.list_audit()
    assert NEW_KEY not in json.dumps([control, audit, result])
    assert control["data"]["provider"]["credential_ciphertext"]
    restored, key = restore_provider_config(state.config, control)
    assert key == NEW_KEY and restored.provider.model == "alternate"
    assert state.provider_credential_digest == hashlib.sha256(NEW_KEY.encode()).digest()
    monkeypatch.setenv("GATEWAY7_CONTROL_KEY", Fernet.generate_key().decode())
    with pytest.raises(StartupError, match="decrypt"):
        restore_provider_config(state.config, control)


async def test_stale_revision_never_probes_or_changes_current_provider(managed_provider):
    state, service, store = managed_provider
    store.write_control(
        1, {}, {"actor": "bootstrap", "action": "test", "target": "test", "diff": {}}
    )
    original = state.pipeline.provider
    with pytest.raises(ControlConflict):
        await service.update(update(), 1, ACTOR)
    assert state.pipeline.provider is original and state.created == []


async def test_failed_probe_retains_committed_and_active_configuration(managed_provider):
    state, service, store = managed_provider
    broken = Provider(reachable=False)
    state.provider_factory = lambda *_args, **_options: broken
    original = state.pipeline.provider
    with pytest.raises(GatewayError) as error:
        await service.update(update(), 1, ACTOR)
    assert error.value.code == "unavailable"
    assert state.pipeline.provider is original and state.config.provider.model == "fake"
    assert store.read_control()["revision"] == 1 and broken.closed


async def test_access_preparation_failure_is_before_durable_commit(managed_provider):
    state, service, store = managed_provider
    original = state.pipeline.provider

    def invalid(*args):
        raise StartupError("synthetic invalid credential registry")

    state.prepare_management_access = invalid
    with pytest.raises(StartupError):
        await service.update(update(), 1, ACTOR)
    assert state.pipeline.provider is original
    assert store.read_control()["revision"] == 1 and state.created[0].closed


async def test_operator_revoked_during_probe_cannot_commit(managed_provider):
    state, service, store = managed_provider
    calls = 0

    def validate(actor):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise GatewayError("operator_forbidden")

    state.validate_operator = validate
    with pytest.raises(GatewayError):
        await service.update(update(), 1, ACTOR)
    assert store.read_control()["revision"] == 1
    assert state.config.provider.model == "fake" and state.created[0].closed


async def test_new_provider_key_cannot_be_operator_credential(managed_provider):
    state, service, store = managed_provider
    with pytest.raises(GatewayError):
        await service.update(update(credential=OPERATOR_KEY), 1, ACTOR)
    assert state.created == [] and store.read_control()["revision"] == 1


async def test_encrypted_provider_restore_rejects_new_bootstrap_credential_collision(
    managed_provider, monkeypatch
):
    state, service, store = managed_provider
    await service.update(update(credential=NEW_KEY), 1, ACTOR)
    monkeypatch.setenv("PROVIDER_ADMIN_OPERATOR", NEW_KEY)
    with pytest.raises(StartupError, match="must differ"):
        restore_provider_config(state.config, store.read_control())


@pytest.mark.parametrize("aliases", [{"a": "b", "b": "c"}, {"a": "a"}, {"team-model": "org/model"}])
def test_aliases_cannot_chain_cycle_or_escape_provider_model_validation(aliases):
    with pytest.raises(ValueError):
        ProviderUpdate(kind="gemini", model="model", aliases=aliases)


async def test_explicit_health_check_does_not_reuse_a_warm_catalog(managed_provider):
    state, service, store = managed_provider
    original = state.pipeline.provider
    data = state.config.model_dump()
    data["provider"] = {
        "kind": "openai",
        "model": "configured-model",
        "key_env": "PROVIDER_ADMIN_KEY",
    }
    state.config = GatewayConfig.model_validate(data)
    active_catalog_calls = 0

    async def warm_catalog():
        nonlocal active_catalog_calls
        active_catalog_calls += 1
        return ()

    original.get_models = warm_catalog
    probe = Provider()

    async def unavailable():
        raise ProviderError(ProviderErrorReason.UNAVAILABLE)

    probe.get_models = unavailable
    state.provider_factory = lambda *_args, **_options: probe
    result = await service.test(actor=ACTOR)
    assert result["status"] == "unavailable"
    assert active_catalog_calls == 0
    assert probe.closed and not original.closed
    assert store.read_control()["revision"] == 1

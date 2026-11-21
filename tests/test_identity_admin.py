"""Identity changes are revision checked, attributable and secret-free on both stores."""

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from gateway7.admin_runtime import ClientPolicy, CreateClient
from gateway7.admin_store import AdminStore
from gateway7.config import GatewayConfig
from gateway7.db_execution import DBExecutor
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_admin import IdentityAdmin, KeyRequest, OperatorRequest, OperatorUpdate
from gateway7.identity_auth import OperatorPrincipal
from gateway7.identity_records import validate_identity
from gateway7.loader import load_plugins
from gateway7.metrics import Metrics
from gateway7.pipeline import Pipeline
from gateway7.usage import PersistentUsageLedger

ROOT = "synthetic-identity-bootstrap-credential"
PROVIDER = "synthetic-identity-provider-credential"
BOOTSTRAP = OperatorPrincipal("bootstrap", "admin", is_bootstrap=True)


class Admission:
    def update(self, config):
        self.config = config


class Provider:
    async def aclose(self):
        pass


@pytest.fixture(params=["sqlite", "postgres"])
async def identity(request, tmp_path, monkeypatch):
    monkeypatch.setenv("IDENTITY_TEST_OPERATOR", ROOT)
    monkeypatch.setenv("FAKE_LLM_API_KEY", PROVIDER)
    db = DBExecutor()
    config = GatewayConfig.model_validate(
        {
            "provider": {"model": "model-a", "allowed_models": ["model-a", "model-b"]},
            "auth": {
                "enabled": True,
                "operator_token_env": "IDENTITY_TEST_OPERATOR",
                "management_db": str(tmp_path / "identity.sqlite3"),
            },
        }
    )
    if request.param == "postgres":
        dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
        if not dsn:
            await db.close()
            pytest.skip("Set GATEWAY7_TEST_POSTGRES_DSN to test a disposable PostgreSQL database")
        import psycopg
        from gateway7.postgres_store import PostgresAdminStore

        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
        config = config.model_copy(
            update={
                "auth": config.auth.model_copy(
                    update={
                        "management_db": None,
                        "management_database_url_env": "IDENTITY_TEST_DATABASE",
                    }
                )
            }
        )
        monkeypatch.setenv("IDENTITY_TEST_DATABASE", dsn)
        store = await db.call(PostgresAdminStore, dsn, config)
    else:
        store = await db.call(AdminStore, config.auth.management_db, config)
    state = SimpleNamespace(
        db=db,
        admin_store=store,
        config=config,
        token_digests={},
        ready=True,
        usage_ledger=await db.call(PersistentUsageLedger, store, []),
        pipeline=Pipeline(load_plugins(config), Provider(), config.limits, metrics=Metrics()),
        client_pipelines={},
        admission=Admission(),
        provider_credential_digest=hashlib.sha256(PROVIDER.encode()).digest(),
    )
    manager = IdentityAdmin(state)
    await manager.initialize()
    try:
        yield manager, state
    finally:
        await db.call(store.close)
        await db.close()
        if request.param == "postgres":
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


def options(state, actor=BOOTSTRAP):
    return {
        "actor": actor,
        "expected_revision": state.control["revision"],
        "request_id": "synthetic-request",
    }


def headers(token):
    return [(b"authorization", ("Bearer " + token).encode())]


async def test_separate_named_keys_revoke_and_expire_without_interrupting_other_application(
    identity,
):
    manager, state = identity
    first = await manager.create(
        CreateClient(
            id="developer",
            models=["model-a"],
            owner="team-one",
            tags=["backend"],
            default_model="model-a",
        ),
        **options(state),
    )
    second = await manager.create_key("developer", KeyRequest(label="CI"), **options(state))
    a, b = first["token"], second["token"]
    assert (
        state.access.authenticate(headers(a)).key_id != state.access.authenticate(headers(b)).key_id
    )
    assert state.access.authenticate(headers(b)).default_model == "model-a"
    assert len(second["client"]["keys"]) == 2
    await manager.revoke_key("developer", first["key"]["id"], **options(state))
    with pytest.raises(GatewayError, match="Missing or invalid"):
        state.access.authenticate(headers(a))
    assert state.access.authenticate(headers(b)).client_id == "developer"
    expiry = datetime.fromisoformat(second["key"]["expires_at"])
    state.access._clock = lambda: expiry
    with pytest.raises(GatewayError, match="Missing or invalid"):
        state.access.authenticate(headers(b))
    public = await manager.snapshot(BOOTSTRAP)
    audit = await state.db.call(state.admin_store.list_audit)
    for secret in (
        a,
        b,
        hashlib.sha256(a.encode()).hexdigest(),
        hashlib.sha256(b.encode()).hexdigest(),
        ROOT,
        PROVIDER,
    ):
        assert secret not in json.dumps(public) + json.dumps(audit)


async def test_stale_editor_cannot_restore_models_or_overwrite_new_limit(identity):
    manager, state = identity
    await manager.create(
        CreateClient(id="developer", models=["model-a", "model-b"]), **options(state)
    )
    old_revision = state.control["revision"]
    await manager.update(
        "developer",
        ClientPolicy(models=["model-a"], limits={"requests_per_minute": 5}),
        **options(state),
    )
    before = copy.deepcopy(state.control)
    with pytest.raises(GatewayError) as error:
        await manager.update(
            "developer",
            ClientPolicy(models=["model-a", "model-b"], limits={"requests_per_minute": 20}),
            actor=BOOTSTRAP,
            expected_revision=old_revision,
        )
    assert error.value.code == "conflict"
    assert state.control == before == await state.db.call(state.admin_store.read_control)
    assert state.config.auth.clients["developer"].models == ["model-a"]
    assert state.config.auth.clients["developer"].limits.requests_per_minute == 5


async def test_named_viewer_cannot_mutate_and_demoted_or_revoked_admin_cannot_use_old_principal(
    identity,
):
    manager, state = identity
    viewer = await manager.create_operator(
        OperatorRequest(id="analyst", label="Usage analyst", role="viewer"), **options(state)
    )
    viewer_actor = state.operator_access.authenticate(headers(viewer["token"]))
    assert viewer_actor.role == "viewer"
    with pytest.raises(GatewayError) as error:
        await manager.create(CreateClient(id="forbidden"), **options(state, viewer_actor))
    assert error.value.code == "operator_forbidden"
    admin = await manager.create_operator(
        OperatorRequest(id="owner", label="Named owner", role="admin"), **options(state)
    )
    admin_actor = state.operator_access.authenticate(headers(admin["token"]))
    await manager.create(
        CreateClient(id="permitted", models=["model-a"]), **options(state, admin_actor)
    )
    await manager.update_operator(
        "owner", OperatorUpdate(role="viewer", label="Now read only"), **options(state)
    )
    with pytest.raises(GatewayError) as error:
        await manager.create(CreateClient(id="stale_admin"), **options(state, admin_actor))
    assert error.value.code == "operator_forbidden"
    await manager.revoke_operator("analyst", **options(state))
    with pytest.raises(GatewayError):
        state.operator_access.authenticate(headers(viewer["token"]))
    assert state.operator_access.authenticate(headers(ROOT)).is_bootstrap
    with pytest.raises(GatewayError) as error:
        await manager.revoke_operator("bootstrap", **options(state))
    assert error.value.code == "operator_forbidden"
    audit = await state.db.call(state.admin_store.list_audit, actor="owner")
    assert [row["action"] for row in audit["items"]] == ["user.create"]
    assert (
        "permitted" not in state.config.auth.clients
        or state.config.auth.clients["permitted"].enabled
    )


async def test_key_last_use_does_not_advance_management_revision(identity):
    manager, state = identity
    result = await manager.create(
        CreateClient(id="developer", models=["model-a"]), **options(state)
    )
    revision = state.control["revision"]
    instant = datetime.now(timezone.utc).isoformat()
    await state.db.call(state.admin_store.touch_key, result["key"]["id"], instant)
    listed = await manager.list_keys("developer")
    assert datetime.fromisoformat(listed["items"][0]["last_used_at"]) == datetime.fromisoformat(
        instant
    )
    assert (
        listed["revision"]
        == revision
        == (await state.db.call(state.admin_store.read_control))["revision"]
    )


async def test_failed_atomic_commit_changes_neither_auth_live_profile_nor_audit(
    identity, monkeypatch
):
    manager, state = identity
    initial = await manager.create(
        CreateClient(id="developer", models=["model-a"]), **options(state)
    )
    before = await manager.snapshot()
    audit = await state.db.call(state.admin_store.list_audit)

    def fail(*args, **kwargs):
        raise StartupError("synthetic-private-database-information")

    monkeypatch.setattr(state.admin_store, "write_control", fail)
    with pytest.raises(GatewayError) as error:
        await manager.revoke_key("developer", initial["key"]["id"], **options(state))
    assert error.value.code == "unavailable"
    assert await manager.snapshot() == before
    assert await state.db.call(state.admin_store.list_audit) == audit
    assert state.access.authenticate(headers(initial["token"])).client_id == "developer"


async def test_user_directory_search_tags_status_and_pages(identity):
    manager, state = identity
    for name, owner, tags in (
        ("alice", "team-one", ["backend"]),
        ("bob", "team-one", ["frontend"]),
        ("service", "team-two", ["backend", "CI"]),
    ):
        await manager.create(
            CreateClient(id=name, models=["model-a"], owner=owner, tags=tags), **options(state)
        )
    first = await manager.list_users(owner="team-one", limit=1)
    second = await manager.list_users(owner="team-one", offset=1, limit=1)
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] == "alice" and second["items"][0]["id"] == "bob"
    assert [row["id"] for row in (await manager.list_users(tag="CI"))["items"]] == ["service"]
    assert (await manager.list_users(q="TEAM-TWO"))["total"] == 1
    await manager.revoke("service", **options(state))
    assert [row["id"] for row in (await manager.list_users(status="revoked"))["items"]] == [
        "service"
    ]


async def test_restart_retains_named_keys_roles_expiry_audit_and_recovery(identity):
    manager, state = identity
    client = await manager.create(
        CreateClient(id="developer", models=["model-a"]), **options(state)
    )
    operator = await manager.create_operator(
        OperatorRequest(id="analyst", label="Analyst", role="viewer"), **options(state)
    )
    before = copy.deepcopy(state.control)
    await IdentityAdmin(state).initialize()
    assert state.control == before
    assert state.access.authenticate(headers(client["token"])).client_id == "developer"
    assert state.operator_access.authenticate(headers(operator["token"])).role == "viewer"
    expiry = datetime.fromisoformat(operator["operator"]["expires_at"])
    state.operator_access._clock = lambda: expiry
    with pytest.raises(GatewayError):
        state.operator_access.authenticate(headers(operator["token"]))
    assert state.operator_access.authenticate(headers(ROOT)).role == "admin"


@pytest.mark.parametrize(
    "expiry", ["2026-01-01", "2026-01-01T00:00:00", "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z"]
)
async def test_invalid_key_expiry_never_changes_state(identity, expiry):
    manager, state = identity
    await manager.create(CreateClient(id="developer", models=["model-a"]), **options(state))
    before = copy.deepcopy(state.control)
    with pytest.raises(GatewayError) as error:
        await manager.create_key(
            "developer", KeyRequest(label="invalid", expires_at=expiry), **options(state)
        )
    assert error.value.code == "invalid_request"
    assert state.control == before


async def test_explicit_default_and_alias_permissions_are_canonical_and_effective(identity):
    manager, state = identity
    for profile in (
        CreateClient(id="forbidden", models=["model-a"], default_model="model-b"),
        CreateClient(id="denyall", models=[], default_model="model-a"),
    ):
        with pytest.raises(GatewayError) as error:
            await manager.create(profile, **options(state))
        assert error.value.code == "invalid_request"
    await manager.create(
        CreateClient(id="allowed", models=["model-a"], default_model="model-a"), **options(state)
    )
    rotated = await manager.rotate("allowed", **options(state))
    assert (
        state.access.authenticate(headers(rotated["token"])).select_model(None, "model-b")
        == "model-a"
    )


def test_corrupt_identity_records_never_silently_become_empty_registry():
    for malformed in (
        {},
        {"users": [], "keys": {}, "operators": {}},
        {"users": {}, "keys": {}, "operators": {}, "private": "SYNTHETIC_PRIVATE"},
    ):
        with pytest.raises(StartupError) as error:
            validate_identity(malformed)
        assert "SYNTHETIC_PRIVATE" not in str(error.value)

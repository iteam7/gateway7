"""Explicit management backend selection and offline migration with synthetic data."""

import importlib
import logging
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway7 import cli
from gateway7.admin_migration import migrate_sqlite, sqlite_snapshot
from gateway7.admin_store import AdminStore
from gateway7.analytics import Analytics
from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.management_store import open_management_store, postgres_url_from_environment
from gateway7.models import ChatResponse
from gateway7.telemetry import Telemetry

TOKENS = {
    name: "synthetic-migration-token-" + name
    for name in ("active", "suspended", "revoked", "deleted")
}
OPERATOR = "synthetic-migration-operator-token"
KEY = "synthetic-migration-provider-token"


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("MIGRATION_OPERATOR", OPERATOR)
    monkeypatch.setenv("FAKE_LLM_API_KEY", KEY)
    for name, token in TOKENS.items():
        monkeypatch.setenv("MIGRATION_" + name.upper(), token)
    path = tmp_path / "private" / "source.sqlite3"
    config = GatewayConfig.model_validate(
        {
            "provider": {"model": "model-a"},
            "auth": {
                "enabled": True,
                "operator_token_env": "MIGRATION_OPERATOR",
                "management_db": str(path),
                "clients": {
                    name: {
                        "token_env": "MIGRATION_" + name.upper(),
                        "enabled": name != "suspended",
                        "models": ["model-a"],
                        "limits": {"max_concurrent_requests": 2, "requests_per_minute": 30},
                        "additional_middleware": ["phone"],
                    }
                    for name in TOKENS
                },
            },
            "plugins": {"phone": {"module": "gateway7.plugins.phone_mask"}},
        }
    )
    store = AdminStore(str(path), config)
    clients, digests = store.load_clients()
    clients.pop("deleted")
    digests.pop("deleted")
    digests.pop("revoked")
    store.save_clients(clients, digests)
    for name in TOKENS:
        store.record_usage(
            name, "model-a", "complete", {"input_tokens": 2**63 - 1, "output_tokens": 3}
        )
        store.record_usage(name, "model-b", "provider_error", None)
    with store._db:
        store._db.execute("UPDATE usage SET day='2026-10-01' WHERE model='model-a'")
    expected = store.export_snapshot()
    store.close()
    return path, config, expected


@pytest.fixture
def postgres(monkeypatch):
    dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GATEWAY7_TEST_POSTGRES_DSN to test a disposable PostgreSQL database")
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", dsn)
    yield dsn
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


def pg_config(config):
    data = config.model_dump()
    data["auth"]["management_db"] = None
    data["auth"]["management_database_url_env"] = "MIGRATION_DATABASE_URL"
    return GatewayConfig.model_validate(data)


def test_backend_selector_rejects_ambiguous_or_unauthenticated_configuration():
    for auth in (
        {
            "enabled": True,
            "operator_token_env": "OPERATOR",
            "management_db": "private.sqlite3",
            "management_database_url_env": "DATABASE",
        },
        {
            "enabled": False,
            "operator_token_env": "OPERATOR",
            "management_database_url_env": "DATABASE",
        },
        {"enabled": True, "management_database_url_env": "DATABASE"},
        {
            "enabled": True,
            "operator_token_env": "OPERATOR",
            "management_database_url_env": "postgresql://private:secret@example/database",
        },
    ):
        with pytest.raises(ValidationError):
            GatewayConfig.model_validate({"auth": auth})
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "OPERATOR",
                "management_database_url_env": "DATABASE",
            }
        }
    )
    assert config.auth.management_enabled
    assert not GatewayConfig().auth.management_enabled


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "sqlite:///private.sqlite3",
        "host=private password=secret",
        "postgresql://private:secret@host",
        "postgresql://private:secret@host/database#secret",
        "postgresql://private:secret@host:99999/database",
        "postgresql://private:secret@host/data base",
    ],
)
def test_database_url_errors_never_reveal_secret_or_fallback(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("MIGRATION_DATABASE_URL", value)
    with pytest.raises(StartupError) as error:
        postgres_url_from_environment("MIGRATION_DATABASE_URL")
    assert "secret" not in str(error.value) and "private" not in str(error.value)


def test_database_factory_failure_does_not_create_sqlite_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "OPERATOR",
                "management_database_url_env": "MIGRATION_DATABASE_URL",
            }
        }
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StartupError):
        open_management_store(config)
    assert list(tmp_path.iterdir()) == []


def test_readonly_snapshot_preserves_bytes_permissions_and_refuses_missing_online_sources(
    source, tmp_path
):
    path, config, expected = source
    before = path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns
    with sqlite_snapshot(str(path)) as snapshot:
        assert snapshot == expected
    assert (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) == before
    missing = tmp_path / "typo.sqlite3"
    with pytest.raises(StartupError):
        with sqlite_snapshot(str(missing)):
            pass
    assert not missing.exists()
    store = AdminStore(str(path), config)
    try:
        with pytest.raises(StartupError):
            with sqlite_snapshot(str(path)):
                pass
    finally:
        store.close()
    symlink = tmp_path / "source-link.sqlite3"
    symlink.symlink_to(path)
    with pytest.raises(StartupError):
        with sqlite_snapshot(str(symlink)):
            pass


def test_migration_copies_every_record_and_preserves_source_bytes(source, postgres, monkeypatch):
    from gateway7.postgres_store import PostgresAdminStore

    path, config, expected = source
    before = path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns
    result = migrate_sqlite(str(path), "MIGRATION_DATABASE_URL")
    assert result == {"clients": 3, "deleted_identities": 1, "usage_rows": 8}
    assert (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) == before
    store = PostgresAdminStore(postgres, pg_config(config))
    assert store.export_snapshot() == expected
    store.close()
    for name in TOKENS:
        monkeypatch.delenv("MIGRATION_" + name.upper())

    class Provider:
        async def complete(self, request, **options):
            return ChatResponse(
                text="synthetic answer", usage={"input_tokens": 1, "output_tokens": 1}
            )

        async def aclose(self):
            pass

    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: Provider()
    )
    app = create_app(
        config=pg_config(config), analytics=Analytics.disabled(), telemetry=Telemetry.disabled()
    )
    with TestClient(app) as client:
        payload = {
            "model": "model-a",
            "messages": [{"role": "user", "content": "synthetic prompt"}],
        }
        for name, token in TOKENS.items():
            response = client.post(
                "/chat", headers={"Authorization": "Bearer " + token}, json=payload
            )
            assert response.status_code == (200 if name == "active" else 401)
        response = client.post(
            "/operator/clients",
            headers={"Authorization": "Bearer " + OPERATOR, "X-Gateway7-Operator": "true"},
            json={"id": "deleted"},
        )
        assert response.status_code == 422
        state = client.get(
            "/operator/state", headers={"Authorization": "Bearer " + OPERATOR}
        ).json()
        for secret in (postgres, TOKENS["active"], str(path), "management_database_url_env"):
            assert secret not in str(state)


def test_migration_refuses_initialized_destination_even_when_it_has_no_clients(source, postgres):
    from gateway7.postgres_store import PostgresAdminStore

    path, config, _ = source
    empty = pg_config(config).model_copy(
        update={"auth": pg_config(config).auth.model_copy(update={"clients": {}})}
    )
    store = PostgresAdminStore(postgres, empty)
    before = store.export_snapshot()
    store.close()
    with pytest.raises(StartupError):
        migrate_sqlite(str(path), "MIGRATION_DATABASE_URL")
    store = PostgresAdminStore(postgres, empty)
    assert store.export_snapshot() == before
    store.close()


def test_migration_cli_outputs_only_counts_and_retries_do_not_overwrite(source, postgres, capsys):
    path, _, _ = source
    logger = logging.getLogger("gateway7")
    previous = logger.handlers[:], logger.level, logger.propagate
    try:
        assert (
            cli.main(
                [
                    "admin",
                    "migrate",
                    "--sqlite",
                    str(path),
                    "--database-url-env",
                    "MIGRATION_DATABASE_URL",
                ]
            )
            == 0
        )
        output = capsys.readouterr()
        assert "Management migration completed" in output.out and "clients" in output.out
        assert (
            cli.main(
                [
                    "admin",
                    "migrate",
                    "--sqlite",
                    str(path),
                    "--database-url-env",
                    "MIGRATION_DATABASE_URL",
                ]
            )
            == 1
        )
        failed = capsys.readouterr()
        combined = output.out + output.err + failed.out + failed.err
        for secret in (postgres, str(path), *TOKENS.values(), OPERATOR, KEY):
            assert secret not in combined
        assert "Traceback" not in combined
    finally:
        logger.handlers, logger.level, logger.propagate = previous


def test_migration_rejects_explicit_unknown_source_schema_without_modifying_it(source):
    import sqlite3

    path, _, _ = source
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO metadata(name,value) VALUES ('schema_version','999')")
    before = path.read_bytes()
    with pytest.raises(StartupError):
        with sqlite_snapshot(str(path)):
            pass
    assert path.read_bytes() == before

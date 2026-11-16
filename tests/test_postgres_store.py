"""Real PostgreSQL storage checks; opt in with an isolated disposable test DSN."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import psycopg
import pytest

from gateway7.admin_store import AdminStore, validate_snapshot
from gateway7.config import ClientConfig, GatewayConfig
from gateway7.errors import StartupError
from gateway7.postgres_store import PostgresAdminStore
from gateway7.usage import PersistentUsageLedger

TOKEN = "synthetic-postgres-client-token"
OPERATOR = "synthetic-postgres-operator-token"


@pytest.fixture
def pg_dsn():
    dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("GATEWAY7_TEST_POSTGRES_DSN is not set")
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
    yield dsn
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


@pytest.fixture
def seed(monkeypatch):
    monkeypatch.setenv("PG_SYNTHETIC_CLIENT", TOKEN)
    monkeypatch.setenv("PG_SYNTHETIC_OPERATOR", OPERATOR)
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-postgres-provider-token")
    return GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "PG_SYNTHETIC_OPERATOR",
                "clients": {
                    "synthetic_client": {"token_env": "PG_SYNTHETIC_CLIENT", "models": ["fake"]}
                },
            }
        }
    )


def test_postgres_bootstrap_once_persists_revocation_deletion_and_no_raw_tokens(
    pg_dsn, seed, monkeypatch
):
    store = PostgresAdminStore(pg_dsn, seed)
    clients, digests = store.load_clients()
    assert clients == seed.auth.clients
    assert digests == {"synthetic_client": hashlib.sha256(TOKEN.encode()).digest()}
    store.ensure_available()
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        records = str(list(connection.execute("SELECT * FROM gateway7_admin.clients")))
        assert TOKEN not in records and OPERATOR not in records
        assert (
            dict(connection.execute("SELECT name,value FROM gateway7_admin.metadata"))[
                "schema_version"
            ]
            == "1"
        )
    store.save_clients(clients, {})
    store.close()
    monkeypatch.delenv("PG_SYNTHETIC_CLIENT")
    reopened = PostgresAdminStore(pg_dsn, seed)
    assert reopened.load_clients() == (clients, {})
    reopened.save_clients({}, {})
    with pytest.raises(ValueError, match="cannot be reused"):
        reopened.save_clients(clients, digests)
    reopened.close()
    empty = PostgresAdminStore(pg_dsn, seed)
    assert empty.load_clients() == ({}, {})
    empty.close()


def test_postgres_second_owner_fails_and_released_lock_can_be_reacquired(pg_dsn, seed):
    owner = PostgresAdminStore(pg_dsn, seed)
    with pytest.raises(StartupError) as error:
        PostgresAdminStore(pg_dsn, seed)
    assert pg_dsn not in str(error.value)
    assert TOKEN not in str(error.value)
    owner.ensure_available()
    owner.close()
    next_owner = PostgresAdminStore(pg_dsn, seed)
    next_owner.close()


def test_postgres_invalid_registry_update_is_atomic(pg_dsn, seed):
    store = PostgresAdminStore(pg_dsn, seed)
    original = store.load_clients()
    clients, digests = store.load_clients()
    clients["synthetic_second"] = ClientConfig(token_env="PG_SYNTHETIC_SECOND")
    digests["synthetic_second"] = digests["synthetic_client"]
    with pytest.raises(ValueError, match="distinct"):
        store.save_clients(clients, digests)
    assert store.load_clients() == original
    store.close()


def test_postgres_usage_survives_restart_and_filters_days_models_and_deleted_clients(
    pg_dsn, seed, monkeypatch
):
    import gateway7.postgres_store as storage_module

    store = PostgresAdminStore(pg_dsn, seed)
    ledger = PersistentUsageLedger(store, seed.auth.clients)

    class DayOne(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 15, 23, 59, tzinfo=timezone.utc)

    class DayTwo(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 16, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(storage_module, "datetime", DayOne)
    ledger.observer("synthetic_client", "synthetic-a")("complete", {"input_tokens": 7})
    monkeypatch.setattr(storage_module, "datetime", DayTwo)
    ledger.observer("synthetic_client", "synthetic-b")("cancelled", {"output_tokens": 3})
    snapshot = ledger.snapshot()
    assert snapshot["clients"]["synthetic_client"]["provider_attempts"] == 2
    assert snapshot["clients"]["synthetic_client"]["known_input_tokens"] == 7
    assert snapshot["clients"]["synthetic_client"]["input_usage_unknown_attempts"] == 1
    assert (
        ledger.snapshot(model="synthetic-a")["clients"]["synthetic_client"]["provider_attempts"]
        == 1
    )
    assert (
        ledger.snapshot(start="2026-11-16", end="2026-11-16")["rows"][0]["model"] == "synthetic-b"
    )
    assert ledger.snapshot(end="2026-11-14")["rows"] == []
    store.save_clients({}, {})
    store.close()
    restarted = PostgresAdminStore(pg_dsn, seed)
    assert PersistentUsageLedger(restarted, []).snapshot() == snapshot
    restarted.close()


def test_postgres_concurrent_observations_preserve_arbitrary_precision(pg_dsn, seed):
    store = PostgresAdminStore(pg_dsn, seed)
    observe = PersistentUsageLedger(store, seed.auth.clients).observer("synthetic_client", "fake")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: observe("complete", {"input_tokens": 2**63 - 1}), range(40)))
    row = store.usage_rows(client_id=None, model=None, start=None, end=None)[0]
    assert row["provider_attempts"] == 40
    assert row["known_input_tokens"] == 40 * (2**63 - 1)
    assert row["output_usage_unknown_attempts"] == 40
    store.close()


def test_postgres_lost_owner_session_never_reconnects_or_writes(pg_dsn, seed):
    store = PostgresAdminStore(pg_dsn, seed)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        pid = store._db.info.backend_pid
        assert connection.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
    with pytest.raises(StartupError):
        store.ensure_available()
    with pytest.raises(StartupError):
        store.save_clients({}, {})
    store.close()
    next_owner = PostgresAdminStore(pg_dsn, seed)
    assert set(next_owner.load_clients()[0]) == {"synthetic_client"}
    next_owner.close()


@pytest.mark.parametrize("corruption", ["version", "counters", "metadata"])
def test_postgres_corrupted_or_unknown_schema_fails_closed(pg_dsn, seed, corruption):
    store = PostgresAdminStore(pg_dsn, seed)
    PersistentUsageLedger(store, seed.auth.clients).observer("synthetic_client", "fake")(
        "complete", None
    )
    store.close()
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        if corruption == "version":
            connection.execute(
                "UPDATE gateway7_admin.metadata SET value='999' WHERE name='schema_version'"
            )
        elif corruption == "metadata":
            connection.execute("DELETE FROM gateway7_admin.metadata WHERE name='started_at'")
        else:
            row = json.loads(
                connection.execute("SELECT counts FROM gateway7_admin.usage").fetchone()[0]
            )
            row["provider_attempts"] = -1
            connection.execute("UPDATE gateway7_admin.usage SET counts=%s", (json.dumps(row),))
    with pytest.raises(StartupError, match="unavailable or invalid"):
        PostgresAdminStore(pg_dsn, seed)


def test_postgres_invalid_seed_rolls_back_initialization_and_corrected_seed_retries(pg_dsn, seed):
    data = seed.model_dump()
    data["auth"]["clients"]["synthetic_client"]["additional_middleware"] = ["missing_policy"]
    with pytest.raises(StartupError):
        PostgresAdminStore(pg_dsn, GatewayConfig.model_validate(data))
    corrected = PostgresAdminStore(pg_dsn, seed)
    assert corrected.load_clients()[0] == seed.auth.clients
    corrected.close()


def test_postgres_import_keeps_entire_sqlite_snapshot_and_refuses_repeat(pg_dsn, seed, tmp_path):
    source = AdminStore(str(tmp_path / "synthetic.sqlite3"), seed)
    clients, digests = source.load_clients()
    clients["synthetic_deleted"] = ClientConfig(token_env="PG_SYNTHETIC_DELETED", enabled=False)
    source.save_clients(clients, digests)
    ledger = PersistentUsageLedger(source, clients)
    ledger.observer("synthetic_deleted", "synthetic-model")("complete", {"input_tokens": 9})
    source.save_clients(seed.auth.clients, digests)
    snapshot = source.export_snapshot()
    source.close()
    destination = PostgresAdminStore(pg_dsn, seed, initialize=False)
    destination.import_snapshot(snapshot)
    assert destination.export_snapshot() == snapshot
    with pytest.raises(ValueError, match="empty"):
        destination.import_snapshot(snapshot)
    destination.close()
    reopened = PostgresAdminStore(pg_dsn, seed)
    assert reopened.export_snapshot() == snapshot
    with pytest.raises(ValueError, match="cannot be reused"):
        reopened.save_clients(clients, digests)
    reopened.close()


def test_postgres_invalid_snapshot_never_partially_imports(pg_dsn, seed, tmp_path):
    source = AdminStore(str(tmp_path / "synthetic.sqlite3"), seed)
    snapshot = source.export_snapshot()
    source.close()
    destination = PostgresAdminStore(pg_dsn, seed, initialize=False)
    invalid = {**snapshot, "tombstones": {"synthetic_client"}}
    with pytest.raises(ValueError, match="Invalid management migration snapshot"):
        destination.import_snapshot(invalid)
    assert destination.load_clients() == ({}, {})
    destination.import_snapshot(snapshot)
    assert destination.export_snapshot() == snapshot
    destination.close()


def test_snapshot_validator_rejects_duplicate_usage_keys(seed, tmp_path):
    source = AdminStore(str(tmp_path / "synthetic.sqlite3"), seed)
    PersistentUsageLedger(source, seed.auth.clients).observer("synthetic_client", "fake")(
        "complete", None
    )
    snapshot = source.export_snapshot()
    snapshot["usage_rows"] *= 2
    with pytest.raises(ValueError):
        validate_snapshot(snapshot)
    source.close()


def test_postgres_database_error_rolls_back_entire_snapshot_import(pg_dsn, seed, tmp_path):
    source = AdminStore(str(tmp_path / "synthetic.sqlite3"), seed)
    PersistentUsageLedger(source, seed.auth.clients).observer(
        "synthetic_client", "synthetic-reject"
    )("complete", {"input_tokens": 4})
    snapshot = source.export_snapshot()
    source.close()
    destination = PostgresAdminStore(pg_dsn, seed, initialize=False)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute(
            "ALTER TABLE gateway7_admin.usage ADD CONSTRAINT synthetic_rejection "
            "CHECK (model <> 'synthetic-reject')"
        )
    with pytest.raises(StartupError, match="migration could not be completed"):
        destination.import_snapshot(snapshot)
    assert destination.load_clients() == ({}, {})
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        assert dict(connection.execute("SELECT name,value FROM gateway7_admin.metadata")) == {
            "schema_version": "1"
        }
        connection.execute("ALTER TABLE gateway7_admin.usage DROP CONSTRAINT synthetic_rejection")
    destination.import_snapshot(snapshot)
    assert destination.export_snapshot() == snapshot
    destination.close()

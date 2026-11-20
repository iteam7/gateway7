"""Real transactional accounting with synthetic identities, metadata and prices."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os

import pytest

from gateway7.accounting import AccountingService, BudgetDenied
from gateway7.admin_store import AdminStore
from gateway7.config import GatewayConfig
from gateway7.control_store import ControlConflict
from gateway7.postgres_store import PostgresAdminStore


class InlineDB:
    async def call(self, method, *args, **kwargs):
        return method(*args, **kwargs)


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTING_CLIENT", "synthetic-accounting-client-token")
    config = GatewayConfig.model_validate(
        {"auth": {"enabled": True, "clients": {"client_a": {"token_env": "ACCOUNTING_CLIENT"}}}}
    )
    if request.param == "sqlite":
        result = AdminStore(str(tmp_path / "accounting.db"), config)
    else:
        dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("Real PostgreSQL test DSN is not configured")
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
        result = PostgresAdminStore(dsn, config)
    yield result
    result.close()
    if request.param == "postgres":
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


def policy(store, *, tokens=1000, cost=None, mode="hard", period="day"):
    control = store.read_control()
    data = control["data"]
    data["accounting"] = {
        "pricing": {
            "revision": control["revision"] + 1,
            "prices": [
                {
                    "model": "fake",
                    "input_micro_usd_per_million": 1_000_000,
                    "output_micro_usd_per_million": 2_000_000,
                }
            ],
        },
        "budgets": {
            "rules": [
                {
                    "id": "client_budget",
                    "client_id": "client_a",
                    "model": None,
                    "period": period,
                    "tokens": tokens,
                    "micro_usd": cost,
                    "mode": mode,
                    "enabled": True,
                }
            ]
        },
    }
    return store.write_control(
        control["revision"],
        data,
        {"actor": "admin", "action": "budget.update", "target": "accounting", "diff": ["rules"]},
    )


def test_global_revision_atomic_profile_publication_audit_and_last_used(store):
    clients, digests = store.load_clients()
    revision = store.write_control(
        0,
        {
            "identity": {
                "users": {
                    "client_a": {
                        "owner": "synthetic-team",
                        "tags": [],
                        "created_at": "2026-11-16T00:00:00Z",
                    }
                },
                "keys": {},
                "operators": {},
            }
        },
        {
            "actor": "admin",
            "action": "users.update",
            "target": "client_a",
            "diff": {"password": "synthetic-secret", "owner": "synthetic-team"},
        },
        clients=clients,
        digests=digests,
    )
    assert revision == 1
    assert (
        store.read_control()["data"]["identity"]["users"]["client_a"]["owner"] == "synthetic-team"
    )
    with pytest.raises(ControlConflict):
        store.write_control(0, {}, {"actor": "admin"}, clients={}, digests={})
    assert "client_a" in store.load_clients()[0]
    audit = store.list_audit(actor="admin", action="users.update", target="client_a")
    assert audit["total"] == 1
    assert "synthetic-secret" not in json.dumps(audit)
    store.touch_key("key_a", "2026-11-16T12:00:00Z")
    store.touch_key("key_a", "2026-11-16T11:00:00Z")
    assert store.key_last_used()["key_a"].startswith("2026-11-16T12:00:00")
    assert store.read_control()["revision"] == revision


def test_concurrent_reservations_across_keys_cannot_overbook_user_budget(store):
    policy(store, tokens=1000)

    def attempt(index):
        try:
            return store.reserve_usage("client_a", "fake", 100, 100, key_id=f"key_{index}")
        except BudgetDenied:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(attempt, range(12)))
    assert len([attempt for attempt in attempts if attempt]) == 5
    assert store.list_usage_events()["total"] == 5


async def test_settlement_is_idempotent_and_captures_price_revision(store):
    policy(store, tokens=1000, cost=1000)
    reservation = store.reserve_usage("client_a", "fake", 100, 100)
    service = AccountingService(store, InlineDB())
    await service.update_pricing(
        1,
        [
            {
                "model": "fake",
                "input_micro_usd_per_million": 9_000_000,
                "output_micro_usd_per_million": 9_000_000,
            }
        ],
        {"actor": "admin"},
    )
    first = store.settle_usage(
        reservation["id"], "complete", {"input_tokens": 7, "output_tokens": 3}
    )
    second = store.settle_usage(reservation["id"], "provider_error", None)
    assert first == second
    assert first["charged_cost_micro_usd"] == 13
    assert first["pricing_revision"] == 1
    assert (
        store.usage_rows(client_id=None, model=None, start=None, end=None)[0]["provider_attempts"]
        == 1
    )
    report = await service.report()
    assert report["summary"]["provider_attempts"] == 1
    assert report["summary"]["cost_micro_usd"] == 13


async def test_unknown_usage_retains_allowance_and_pending_is_visible(store):
    policy(store, tokens=200)
    reservation = store.reserve_usage("client_a", "fake", 100, 100)
    service = AccountingService(store, InlineDB())
    assert (await service.report())["summary"]["pending_attempts"] == 1
    store.settle_usage(reservation["id"], "provider_error", None)
    with pytest.raises(BudgetDenied):
        store.reserve_usage("client_a", "fake", 1, 1)
    row = (await service.report())["summary"]
    assert row["known_input_tokens"] == 0 and row["input_usage_unknown_attempts"] == 1
    assert row["unknown_cost_attempts"] == 1


async def test_exact_interval_uses_start_not_settlement_and_paginates(store):
    service = AccountingService(store, InlineDB())
    for at, model in [
        ("2026-11-01T00:00:00Z", "model-a"),
        ("2026-11-01T23:59:59Z", "model-b"),
        ("2026-11-02T00:00:00Z", "model-a"),
    ]:
        event = store.reserve_usage("client_a", model, 100, 100, started_at=at)
        store.settle_usage(event["id"], "complete", {"input_tokens": 7, "output_tokens": 2})
    result = await service.report(
        start="2026-11-01T00:00:00Z", end="2026-11-02T00:00:00Z", bucket="hour", offset=1, limit=1
    )
    assert result["summary"]["provider_attempts"] == 2
    assert result["summary"]["known_input_tokens"] == 14
    assert result["pagination"]["total"] == 2 and len(result["rows"]) == 1
    assert len(result["timeseries"]) == 2
    assert (await service.history(model="model-b"))["total"] == 1
    chunks = [
        chunk
        async for chunk in service.iter_csv(
            start="2026-11-01T00:00:00Z", end="2026-11-02T00:00:00Z"
        )
    ]
    assert "started_at" in chunks[0]
    assert sum(chunk.count("client_a") for chunk in chunks) == 2


async def test_warning_budget_does_not_block_and_retention_preserves_current_window(store):
    policy(store, tokens=10, mode="warn", period="month")
    event = store.reserve_usage("client_a", "fake", 100, 100)
    store.settle_usage(event["id"], "complete", {"input_tokens": 7, "output_tokens": 2})
    service = AccountingService(store, InlineDB())
    assert (await service.budget_status())["items"][0]["warning"]
    with pytest.raises(ValueError):
        await service.update_retention(1, 1, {"actor": "admin"})
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    pending = store.reserve_usage("client_a", "fake", 100, 100, started_at=old)
    complete = store.reserve_usage("client_a", "fake", 100, 100, started_at=old)
    store.settle_usage(complete["id"], "complete", {"input_tokens": 1, "output_tokens": 1})
    result = await service.purge()
    assert result["events_deleted"] == 1
    assert store._get_usage_event(pending["id"])["status"] == "pending"
    assert (await service.budget_status())["items"][0]["used_tokens"] == 9


async def test_http_denials_are_diagnostics_without_provider_usage(store):
    service = AccountingService(store, InlineDB())
    await service.record_http(client_id="client_a", outcome="rate_limited", duration_ms=15)
    report = await service.report()
    assert report["summary"]["provider_attempts"] == 0
    diagnostics = await service.diagnostics(client_id="client_a")
    assert diagnostics["http_outcomes"]["rate_limited"] == 1
    assert diagnostics["mean_latency_ms"] == 15


def test_same_backend_backup_roundtrip_and_nonempty_restore_rejected(store, tmp_path):
    policy(store, tokens=1000)
    event = store.reserve_usage("client_a", "fake", 100, 100, key_id="synthetic_key")
    store.settle_usage(event["id"], "complete", {"input_tokens": 7, "output_tokens": 3})
    snapshot = store.backup_snapshot()
    assert snapshot["format"] == "gateway7-backup"
    assert "synthetic-accounting-client-token" not in json.dumps(snapshot)
    with pytest.raises(ValueError, match="empty"):
        store.restore_backup(snapshot)
    if snapshot["backend"] == "sqlite":
        destination = AdminStore(str(tmp_path / "restored.db"), GatewayConfig())
        destination.restore_backup(snapshot)
        assert destination.backup_snapshot() == snapshot
        destination.close()
    invalid = {**snapshot, "backend": "sqlite" if snapshot["backend"] == "postgres" else "postgres"}
    with pytest.raises(ValueError, match="incompatible"):
        store.restore_backup(invalid)


async def test_unbounded_no_budget_request_is_preserved_but_hard_budget_refuses(store):
    class Request:
        def model_dump(self, **kwargs):
            return {"input": "synthetic text", "max_output_tokens": None}

    service = AccountingService(store, InlineDB())
    before, observer = service.bind("client_a", "fake")
    await before(Request())
    await observer("complete", {"input_tokens": 7, "output_tokens": 3})
    assert (await service.report())["summary"]["provider_attempts"] == 1
    policy(store, tokens=10000)
    before, _ = service.bind("client_a", "fake")
    from gateway7.errors import GatewayError

    with pytest.raises(GatewayError):
        await before(Request())
    assert store.list_usage_events()["total"] == 1


def test_existing_version_one_usage_is_retained_at_day_precision(store):
    # Isolate an authentic v1-shaped metadata/tables snapshot before additive upgrade.
    for table in (
        "control_documents",
        "control_audit",
        "usage_events",
        "key_activity",
        "legacy_usage",
    ):
        store._control_query("DROP TABLE {prefix}" + table)
    store._control_query("DELETE FROM {prefix}metadata WHERE name='control_revision'")
    store._control_query("UPDATE {prefix}metadata SET value='1' WHERE name='schema_version'")
    counts = {
        "provider_attempts": 2,
        "outcomes": {"complete": 1, "provider_error": 1, "cancelled": 0},
        "known_input_tokens": 7,
        "known_output_tokens": 3,
        "input_usage_unknown_attempts": 1,
        "output_usage_unknown_attempts": 1,
    }
    store._control_query(
        "INSERT INTO {prefix}usage(client_id,model,day,counts) VALUES (?,?,?,?)",
        ("client_a", "fake", "2026-11-01", json.dumps(counts)),
    )
    if not store._backend_postgres:
        store._db.commit()
    store._initialize_controls()
    service = AccountingService(store, InlineDB())
    report = asyncio.run(service.report(start="2026-11-01T00:00:00Z", end="2026-11-02T00:00:00Z"))
    assert report["summary"]["provider_attempts"] == 2
    assert report["legacy_daily_precision"]
    partial = asyncio.run(service.report(start="2026-11-01T12:00:00Z", end="2026-11-02T00:00:00Z"))
    assert partial["summary"]["provider_attempts"] == 0
    assert partial["legacy_daily_rows_excluded"] == 1
    assert store.load_clients()[0]["client_a"].enabled


def test_schema_and_revision_corruption_never_silently_downgrade(store):
    store._control_query("UPDATE {prefix}metadata SET value='3' WHERE name='schema_version'")
    if not store._backend_postgres:
        store._db.commit()
    with pytest.raises(ValueError, match="Unsupported"):
        store._initialize_controls()
    store._control_query("UPDATE {prefix}metadata SET value='2' WHERE name='schema_version'")
    store._control_query("UPDATE {prefix}metadata SET value='9' WHERE name='control_revision'")
    if not store._backend_postgres:
        store._db.commit()
    with pytest.raises(ValueError, match="revision metadata"):
        store._initialize_controls()


def reopen_empty(store, tmp_path):
    if store._backend_postgres:
        import psycopg

        dsn = os.environ["GATEWAY7_TEST_POSTGRES_DSN"]
        store.close()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA gateway7_admin CASCADE")
        return PostgresAdminStore(dsn, GatewayConfig())
    return AdminStore(str(tmp_path / "empty-backup.db"), GatewayConfig())


def test_backup_restore_validates_identities_and_audit_and_restores_same_backend(store, tmp_path):
    import copy

    policy(store, tokens=1000)
    reservation = store.reserve_usage("client_a", "fake", 100, 100)
    store.settle_usage(reservation["id"], "complete", {"input_tokens": 7, "output_tokens": 3})
    snapshot = store.backup_snapshot()
    destination = reopen_empty(store, tmp_path)
    try:
        invalid = copy.deepcopy(snapshot)
        invalid["control"]["data"]["identity"] = {
            "users": {},
            "keys": {"invalid": {}},
            "operators": {},
        }
        with pytest.raises(ValueError, match="incompatible"):
            destination.restore_backup(invalid)
        assert destination.read_control() == {"revision": 0, "data": {}}
        invalid = copy.deepcopy(snapshot)
        invalid["audit"][0]["diff"] = {"credential": "synthetic-plaintext-forbidden"}
        with pytest.raises(ValueError, match="incompatible"):
            destination.restore_backup(invalid)
        assert destination.read_control() == {"revision": 0, "data": {}}
        destination.restore_backup(snapshot)
        assert destination.backup_snapshot() == snapshot
    finally:
        destination.close()


def test_nonempty_legacy_rollups_prevent_restore(store, tmp_path):
    from gateway7.admin_store import _empty_counts

    snapshot = store.backup_snapshot()
    destination = reopen_empty(store, tmp_path)
    try:
        destination._control_query(
            "INSERT INTO {prefix}legacy_usage(client_id,model,day,counts) VALUES (?,?,?,?)",
            ("synthetic_history", "fake", "2026-11-01", json.dumps(_empty_counts())),
        )
        if not destination._backend_postgres:
            destination._db.commit()
        with pytest.raises(ValueError, match="empty"):
            destination.restore_backup(snapshot)
        assert destination.read_control() == {"revision": 0, "data": {}}
    finally:
        destination.close()


async def test_pending_reservation_survives_restart_and_never_churns_control_revision(store):
    policy(store, tokens=200)
    revision = store.read_control()["revision"]
    attempt = store.reserve_usage("client_a", "fake", 100, 100)
    assert store.read_control()["revision"] == revision
    postgres = store._backend_postgres
    if postgres:
        address = os.environ["GATEWAY7_TEST_POSTGRES_DSN"]
    else:
        address = store._db.execute("PRAGMA database_list").fetchone()[2]
    store.close()
    reopened = (
        PostgresAdminStore(address, GatewayConfig())
        if postgres
        else AdminStore(address, GatewayConfig())
    )
    try:
        assert reopened._get_usage_event(attempt["id"])["status"] == "pending"
        with pytest.raises(BudgetDenied):
            reopened.reserve_usage("client_a", "fake", 1, 1)
        assert reopened.read_control()["revision"] == revision
    finally:
        reopened.close()


async def test_retention_preserves_daily_totals_and_known_costs(store, tmp_path):
    policy(store, tokens=1000, mode="warn")
    old = datetime.now(timezone.utc) - timedelta(days=100)
    attempt = store.reserve_usage("client_a", "fake", 100, 100, started_at=old.isoformat())
    store.settle_usage(attempt["id"], "complete", {"input_tokens": 7, "output_tokens": 3})
    service = AccountingService(store, InlineDB())
    start = old.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    filters = {"start": start.isoformat(), "end": end.isoformat()}
    before = await service.report(**filters)
    assert (await service.purge())["events_deleted"] == 1
    after = await service.report(**filters)
    assert after["summary"] == before["summary"]
    assert after["rows"][0]["precision"] == "day"
    assert after["retention"]["daily_rollups_retained"]
    assert after["summary"]["cost_micro_usd"] == 13
    output = "".join([chunk async for chunk in service.iter_csv(**filters)])
    assert "day" in output and "client_a" in output
    snapshot = store.backup_snapshot()
    destination = reopen_empty(store, tmp_path)
    try:
        destination.restore_backup(snapshot)
        assert destination.backup_snapshot() == snapshot
        restored = AccountingService(destination, InlineDB())
        assert (await restored.report(**filters))["summary"]["cost_micro_usd"] == 13
    finally:
        destination.close()


async def test_stream_csv_uses_stable_keyset_under_concurrent_insert_and_closes(store):
    import csv
    import io

    start = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    original = set()
    with store._control_transaction():
        for index in range(501):
            at = start + timedelta(seconds=index)
            event = store.reserve_usage("client_a", "fake", 1, 1, started_at=at.isoformat())
            store.settle_usage(event["id"], "complete", {"input_tokens": 1, "output_tokens": 1})
            original.add(event["started_at"])
    service = AccountingService(store, InlineDB())
    stream = service.iter_csv(start="2026-11-01T00:00:00Z", end="2026-11-02T00:00:00Z")
    header = await anext(stream)
    first = await anext(stream)
    inserted = store.reserve_usage("client_a", "fake", 1, 1, started_at="2026-11-01T01:00:00Z")
    store.settle_usage(inserted["id"], "complete", {"input_tokens": 1, "output_tokens": 1})
    remaining = "".join([chunk async for chunk in stream])
    rows = list(csv.DictReader(io.StringIO(header + first + remaining)))
    assert len(rows) == 501
    assert {row["started_at"] for row in rows} == original
    assert service._exports == 0
    abandoned = service.iter_csv()
    await anext(abandoned)
    assert service._exports == 1
    assert (await service.purge())["skipped_active_exports"] == 1
    await abandoned.aclose()
    assert service._exports == 0


async def test_repeated_cancellation_finishes_owned_accounting_settlement(store):
    entered, release = asyncio.Event(), asyncio.Event()

    class DeferredDB(InlineDB):
        async def call(self, method, *args, **kwargs):
            if getattr(method, "__name__", "") == "settle_usage":
                entered.set()
                await release.wait()
            return await super().call(method, *args, **kwargs)

    class Request:
        def model_dump(self, **kwargs):
            return {"messages": [{"role": "user", "content": "synthetic"}], "max_tokens": 256}

    service = AccountingService(store, DeferredDB())
    before, observer = service.bind("client_a", "fake")
    await before(Request())
    work = asyncio.create_task(observer("cancelled", {"input_tokens": 7, "output_tokens": 3}))
    await entered.wait()
    work.cancel()
    await asyncio.sleep(0)
    work.cancel()
    await asyncio.sleep(0)
    assert not work.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    event = store.list_usage_events()["items"][0]
    assert event["status"] == "cancelled"
    assert event["known_input_tokens"] == 7 and event["known_output_tokens"] == 3


def test_schema_upgrade_ddl_and_legacy_copy_roll_back_together_on_corruption(store):
    for table in (
        "control_documents",
        "control_audit",
        "usage_events",
        "key_activity",
        "legacy_usage",
        "archived_usage",
    ):
        store._control_query("DROP TABLE {prefix}" + table)
    store._control_query("DELETE FROM {prefix}metadata WHERE name='control_revision'")
    store._control_query("UPDATE {prefix}metadata SET value='1' WHERE name='schema_version'")
    store._control_query(
        "INSERT INTO {prefix}usage(client_id,model,day,counts) VALUES (?,?,?,?)",
        ("client_a", "fake", "2026-11-01", '{"invalid":"synthetic corruption"}'),
    )
    if not store._backend_postgres:
        store._db.commit()
    with pytest.raises((ValueError, KeyError)):
        store._initialize_controls()
    if store._backend_postgres:
        exists = store._control_query(
            "SELECT to_regclass('gateway7_admin.control_documents')"
        ).fetchone()[0]
    else:
        exists = store._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='control_documents'"
        ).fetchone()
    assert not exists
    assert (
        store._control_query(
            "SELECT value FROM {prefix}metadata WHERE name='schema_version'"
        ).fetchone()[0]
        == "1"
    )

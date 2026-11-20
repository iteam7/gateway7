"""Durable management tests use only temporary databases and synthetic secrets."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gateway7.admin_store import AdminStore
from gateway7.config import ClientConfig, GatewayConfig
from gateway7.errors import StartupError
from gateway7.usage import PersistentUsageLedger

TOKEN = "synthetic-bootstrap-client-token"
OPERATOR = "synthetic-bootstrap-operator-token"
KEY = "synthetic-bootstrap-provider-token"


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv("MANAGED_BOOTSTRAP_TOKEN", TOKEN)
    monkeypatch.setenv("MANAGED_BOOTSTRAP_OPERATOR", OPERATOR)
    monkeypatch.setenv("FAKE_LLM_API_KEY", KEY)
    return GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "MANAGED_BOOTSTRAP_OPERATOR",
                "clients": {
                    "synthetic_client": {
                        "token_env": "MANAGED_BOOTSTRAP_TOKEN",
                        "models": ["fake"],
                    }
                },
            }
        }
    )


def test_database_imports_configuration_once_and_never_resurrects_deleted_clients(
    tmp_path, seeded, monkeypatch
):
    path = tmp_path / "private" / "management.sqlite3"
    store = AdminStore(str(path), seeded)
    clients, digests = store.load_clients()
    assert clients == seeded.auth.clients
    assert digests == {"synthetic_client": hashlib.sha256(TOKEN.encode()).digest()}
    assert TOKEN.encode() not in path.read_bytes()
    assert OPERATOR.encode() not in path.read_bytes()
    assert KEY.encode() not in path.read_bytes()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    store.save_clients({}, {})
    with pytest.raises(ValueError, match="cannot be reused"):
        store.save_clients(clients, digests)
    assert store.load_clients() == ({}, {})
    store.close()
    monkeypatch.delenv("MANAGED_BOOTSTRAP_TOKEN")
    reopened = AdminStore(str(path), seeded)
    assert reopened.load_clients() == ({}, {})
    with pytest.raises(ValueError, match="cannot be reused"):
        reopened.save_clients(clients, digests)
    reopened.close()


def test_revoked_and_suspended_credentials_survive_restart(tmp_path, seeded):
    path = str(tmp_path / "management.sqlite3")
    store = AdminStore(path, seeded)
    clients, _ = store.load_clients()
    clients["synthetic_client"] = ClientConfig(
        token_env="MANAGED_BOOTSTRAP_TOKEN", enabled=False, models=[]
    )
    store.save_clients(clients, {})
    store.close()
    reopened = AdminStore(path, seeded)
    actual, digests = reopened.load_clients()
    assert not actual["synthetic_client"].enabled
    assert actual["synthetic_client"].models == []
    assert digests == {}
    reopened.close()


def test_invalid_registry_update_rolls_back_all_changes(tmp_path, seeded):
    store = AdminStore(str(tmp_path / "management.sqlite3"), seeded)
    original = store.load_clients()
    clients, digests = store.load_clients()
    clients["synthetic_second"] = ClientConfig(token_env="MANAGED_SECOND_TOKEN")
    digests["synthetic_second"] = digests["synthetic_client"]
    with pytest.raises(ValueError, match="distinct"):
        store.save_clients(clients, digests)
    assert store.load_clients() == original
    with pytest.raises(ValueError):
        store.save_clients({"bad id": clients["synthetic_client"]}, {})
    assert store.load_clients() == original
    store.close()


def test_exclusive_store_refuses_a_second_process_connection(tmp_path, seeded):
    path = str(tmp_path / "management.sqlite3")
    first = AdminStore(path, seeded)
    with pytest.raises(StartupError, match="unavailable or invalid"):
        AdminStore(path, seeded)
    assert set(first.load_clients()[0]) == {"synthetic_client"}
    first.close()
    second = AdminStore(path, seeded)
    second.close()


def test_corrupt_database_and_invalid_bootstrap_fail_without_echoing_data(
    tmp_path, seeded, monkeypatch
):
    path = tmp_path / "management.sqlite3"
    marker = "synthetic-private-invalid-database-content"
    path.write_text(marker)
    with pytest.raises(StartupError) as caught:
        AdminStore(str(path), seeded)
    assert marker not in str(caught.value)
    path.unlink()
    monkeypatch.setenv("MANAGED_BOOTSTRAP_TOKEN", "invalid token with spaces")
    with pytest.raises(StartupError) as caught:
        AdminStore(str(path), seeded)
    assert "invalid token" not in str(caught.value)


def test_database_symlink_is_refused(tmp_path, seeded):
    real = tmp_path / "real.sqlite3"
    link = tmp_path / "link.sqlite3"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("Creating symlinks is unavailable")
    with pytest.raises(StartupError):
        AdminStore(str(link), seeded)
    assert not real.exists()


def test_persistent_usage_counts_models_days_unknowns_and_deleted_history(
    tmp_path, seeded, monkeypatch
):
    path = str(tmp_path / "management.sqlite3")
    store = AdminStore(path, seeded)
    ledger = PersistentUsageLedger(store, seeded.auth.clients)
    import gateway7.admin_store as storage_module

    class DayOne(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 23, 59, tzinfo=timezone.utc)

    class DayTwo(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 15, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(storage_module, "datetime", DayOne)
    observe = ledger.observer("synthetic_client", "synthetic-model-a")
    observe("complete", {"input_tokens": 7, "output_tokens": 3})
    observe("cancelled", {"input_tokens": True, "output_tokens": 5, "prompt": 999})
    monkeypatch.setattr(storage_module, "datetime", DayTwo)
    ledger.observer("synthetic_client", "synthetic-model-b")("unexpected", None)
    result = ledger.snapshot()
    assert result["scope"] == "persistent"
    assert not result["reset_on_restart"]
    assert result["clients"]["synthetic_client"] == {
        "provider_attempts": 3,
        "outcomes": {"complete": 1, "provider_error": 1, "cancelled": 1},
        "known_input_tokens": 7,
        "known_output_tokens": 8,
        "input_usage_unknown_attempts": 2,
        "output_usage_unknown_attempts": 1,
    }
    assert len(result["rows"]) == 2
    assert (
        ledger.snapshot(model="synthetic-model-a")["clients"]["synthetic_client"][
            "provider_attempts"
        ]
        == 2
    )
    assert (
        ledger.snapshot(start="2026-11-15", end="2026-11-15")["rows"][0]["model"]
        == "synthetic-model-b"
    )
    assert ledger.snapshot(end="2026-11-13")["rows"] == []
    assert ledger.snapshot(client_id="synthetic_absent")["clients"] == {}
    assert "prompt" not in json.dumps(result)
    original_started_at = result["started_at"]
    store.save_clients({}, {})
    store.close()
    reopened = AdminStore(path, seeded)
    restarted = PersistentUsageLedger(reopened, [])
    assert restarted.snapshot() == result
    assert restarted.snapshot()["started_at"] == original_started_at
    reopened.close()


def test_concurrent_durable_observations_and_large_counters_are_exact(tmp_path, seeded):
    store = AdminStore(str(tmp_path / "management.sqlite3"), seeded)
    ledger = PersistentUsageLedger(store, seeded.auth.clients)
    observe = ledger.observer("synthetic_client", "synthetic-model")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: observe("complete", {"input_tokens": 2**63 - 1}), range(50)))
    result = ledger.snapshot()["clients"]["synthetic_client"]
    assert result["provider_attempts"] == result["outcomes"]["complete"] == 50
    assert result["known_input_tokens"] == 50 * (2**63 - 1)
    assert result["output_usage_unknown_attempts"] == 50
    ledger.ensure_clients(["synthetic_new"])
    ledger.observer("synthetic_new")("complete", {"output_tokens": 1})
    assert ledger.snapshot()["clients"]["synthetic_new"]["known_output_tokens"] == 1
    with pytest.raises(ValueError):
        ledger.observer("synthetic_unknown")
    store.close()


@pytest.mark.parametrize(
    "filters",
    [
        {"start": "20261115"},
        {"end": "2026-02-30"},
        {"start": "2026-11-16", "end": "2026-11-15"},
        {"client_id": "bad id"},
        {"model": "bad model"},
    ],
)
def test_usage_filters_reject_ambiguous_or_invalid_values(tmp_path, seeded, filters):
    store = AdminStore(str(tmp_path / "management.sqlite3"), seeded)
    ledger = PersistentUsageLedger(store, seeded.auth.clients)
    with pytest.raises(ValueError):
        ledger.snapshot(**filters)
    store.close()


@pytest.mark.parametrize(
    "corruption",
    ["negative", "boolean", "outcome_sum", "extra_text", "missing_start", "invalid_initialized"],
)
def test_corrupted_accounting_and_metadata_fail_closed_at_restart(tmp_path, seeded, corruption):
    import sqlite3

    path = str(tmp_path / "management.sqlite3")
    store = AdminStore(path, seeded)
    ledger = PersistentUsageLedger(store, seeded.auth.clients)
    ledger.observer("synthetic_client", "synthetic-model")("complete", {"input_tokens": 2})
    store.close()
    with sqlite3.connect(path) as connection:
        counts = json.loads(connection.execute("SELECT counts FROM usage").fetchone()[0])
        if corruption == "negative":
            counts["known_input_tokens"] = -1
        elif corruption == "boolean":
            counts["provider_attempts"] = True
        elif corruption == "outcome_sum":
            counts["outcomes"]["cancelled"] = 1
        elif corruption == "extra_text":
            counts["synthetic_private_text"] = "synthetic conversation content"
        elif corruption == "missing_start":
            connection.execute("DELETE FROM metadata WHERE name='started_at'")
        else:
            connection.execute("UPDATE metadata SET value='invalid' WHERE name='initialized'")
        connection.execute("UPDATE usage SET counts=?", (json.dumps(counts),))
    with pytest.raises(StartupError, match="unavailable or invalid"):
        AdminStore(path, seeded)


@pytest.mark.parametrize("selector", ["missing", "disabled", "global", "duplicate"])
def test_invalid_bootstrap_selector_rolls_back_and_corrected_seed_can_initialize(
    tmp_path, seeded, selector
):
    data = seeded.model_dump()
    data["plugins"] = {
        "synthetic_policy": {
            "module": "gateway7.plugins.email_mask",
            "enabled": selector != "disabled",
        }
    }
    if selector == "global":
        data["middleware"] = ["synthetic_policy"]
    extra = "missing_policy" if selector == "missing" else "synthetic_policy"
    data["auth"]["clients"]["synthetic_client"]["additional_middleware"] = (
        [extra, extra] if selector == "duplicate" else [extra]
    )
    invalid = GatewayConfig.model_validate(data)
    path = str(tmp_path / "management.sqlite3")
    with pytest.raises(StartupError, match="unavailable or invalid"):
        AdminStore(path, invalid)
    corrected = AdminStore(path, seeded)
    assert corrected.load_clients()[0] == seeded.auth.clients
    corrected.close()

"""Offline backup drills preserve actual identities, accounting and encrypted state."""

import copy
import json
import logging
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet
import pytest
import yaml

from gateway7.backup import backup_management, read_backup, restore_management
from gateway7.cli import main
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.identity_admin import CreateClient, IdentityAdmin, OperatorRequest
from gateway7.management_store import open_management_store
from gateway7.provider_admin import ProviderUpdate, restore_provider_config
from test_identity_admin import PROVIDER, ROOT, headers, options
from test_identity_admin import identity as identity


def config_file(path, config):
    path.write_text(yaml.safe_dump(config.model_dump(exclude_none=True)))
    return str(path)


async def test_private_backup_cli_restore_drill_keeps_full_control_and_pending_usage(
    identity, tmp_path, monkeypatch, capsys
):
    manager, state = identity
    client = await manager.create(
        CreateClient(id="developer", models=["model-a"], owner="team", tags=["backend"]),
        **options(state),
    )
    operator = await manager.create_operator(
        OperatorRequest(id="analyst", label="Read only", role="viewer"), **options(state)
    )
    await manager.create(CreateClient(id="deleted", models=["model-a"]), **options(state))
    await manager.delete("deleted", **options(state))
    now = datetime.now(timezone.utc).isoformat()
    await state.db.call(state.admin_store.touch_key, client["key"]["id"], now)
    control = copy.deepcopy(state.control)
    master = Fernet.generate_key()
    monkeypatch.setenv("GATEWAY7_CONTROL_KEY", master.decode())
    replacement_provider = "synthetic-backup-encrypted-provider-secret"
    provider = ProviderUpdate(
        kind="fake", model="model-a", allowed_models=["model-a", "model-b"]
    ).model_dump(exclude={"credential"})
    provider.update(
        {
            "credential_ciphertext": Fernet(master).encrypt(replacement_provider.encode()).decode(),
            "credential_updated_at": now,
        }
    )
    control["data"]["provider"] = provider
    control["data"]["accounting"] = {
        "budgets": {
            "rules": [
                {
                    "id": "daily",
                    "client_id": "developer",
                    "model": "model-a",
                    "period": "day",
                    "tokens": 1000,
                    "micro_usd": None,
                    "mode": "hard",
                    "enabled": True,
                }
            ]
        }
    }
    revision = await state.db.call(
        state.admin_store.write_control,
        control["revision"],
        control["data"],
        {"actor": "bootstrap", "action": "policy.update", "target": "control"},
    )
    state.control = {"revision": revision, "data": control["data"]}
    pending = await state.db.call(
        state.admin_store.reserve_usage, "developer", "model-a", 100, 50, key_id=client["key"]["id"]
    )
    expected = await state.db.call(state.admin_store.backup_snapshot)
    source_config = config_file(tmp_path / "source.yaml", state.config)
    output = tmp_path / "private-backup.json"
    with pytest.raises(StartupError):
        backup_management(source_config, str(output))
    await state.db.call(state.admin_store.close)
    logger = logging.getLogger("gateway7")
    previous = logger.handlers[:], logger.level, logger.propagate
    try:
        assert main(["backup", "--config", source_config, "--output", str(output)]) == 0
        printed = capsys.readouterr()
        assert "Management backup completed" in printed.out
        if os.name == "posix":
            assert output.stat().st_mode & 0o777 == 0o600
        snapshot = read_backup(str(output))
        assert snapshot == expected
        raw = output.read_text()
        for secret in (
            client["token"],
            operator["token"],
            ROOT,
            PROVIDER,
            replacement_provider,
            master.decode(),
        ):
            assert secret not in raw + printed.out + printed.err
        before = output.read_bytes()
        with pytest.raises(StartupError):
            backup_management(source_config, str(output))
        assert output.read_bytes() == before
        if state.config.auth.management_db is not None:
            data = state.config.model_dump()
            data["auth"]["management_db"] = str(tmp_path / "restored.sqlite3")
            target_config = GatewayConfig.model_validate(data)
        else:
            import psycopg

            dsn = os.environ[state.config.auth.management_database_url_env]
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute("DROP SCHEMA gateway7_admin CASCADE")
            target_config = state.config
        destination = config_file(tmp_path / "target.yaml", target_config)
        assert main(["restore", "--config", destination, "--input", str(output)]) == 0
        assert "Management restore completed" in capsys.readouterr().out
        restored = open_management_store(target_config)
        try:
            actual = restored.backup_snapshot()
            assert actual == expected
            assert any(
                row["id"] == pending["id"] and row["status"] == "pending"
                for row in actual["events"]
            )
            assert "deleted" in actual["tombstones"]
            assert (
                restore_provider_config(target_config, actual["control"])[1] == replacement_provider
            )
            fresh = copy.copy(state)
            fresh.config = GatewayConfig.model_validate(
                {
                    **target_config.model_dump(),
                    "auth": {
                        **target_config.auth.model_dump(),
                        "clients": {
                            name: value.model_dump()
                            for name, value in restored.load_clients()[0].items()
                        },
                    },
                }
            )
            fresh.admin_store = restored
            fresh.token_digests = restored.load_clients()[1]
            fresh.provider_credential_digest = None
            await IdentityAdmin(fresh).initialize()
            assert fresh.access.authenticate(headers(client["token"])).client_id == "developer"
            assert fresh.operator_access.authenticate(headers(operator["token"])).role == "viewer"
            assert fresh.operator_access.authenticate(headers(ROOT)).is_bootstrap
        finally:
            restored.close()
        with pytest.raises(StartupError):
            restore_management(destination, str(output))
    finally:
        logger.handlers, logger.level, logger.propagate = previous


def test_backup_checksums_private_permissions_and_source_typos_fail_closed(tmp_path):
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "operator_token_env": "UNUSED_BACKUP_OPERATOR",
                "management_db": str(tmp_path / "missing.sqlite3"),
            }
        }
    )
    path = config_file(tmp_path / "config.yaml", config)
    with pytest.raises(StartupError):
        backup_management(path, str(tmp_path / "never-created.json"))
    assert not (tmp_path / "missing.sqlite3").exists()
    bad = tmp_path / "corrupt.json"
    bad.write_text(
        json.dumps(
            {
                "format": "gateway7-private-backup",
                "version": 1,
                "sha256": "0" * 64,
                "snapshot": {"format": "gateway7-backup", "version": 2},
            }
        )
    )
    bad.chmod(0o600)
    with pytest.raises(StartupError):
        read_backup(str(bad))
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"format":"gateway7-private-backup","version":1,"version":1}')
    duplicate.chmod(0o600)
    with pytest.raises(StartupError):
        read_backup(str(duplicate))
    if os.name == "posix":
        bad.chmod(0o644)
        with pytest.raises(StartupError):
            read_backup(str(bad))

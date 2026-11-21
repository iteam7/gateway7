"""Offline private backups; restore refuses populated or different-backend stores."""

import hashlib
import hmac
import json
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import Any

from gateway7.config import GatewayConfig, load_config
from gateway7.errors import StartupError
from gateway7.management_store import open_management_store, postgres_url_from_environment

MAX_BACKUP_BYTES = 64 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate backup member")
        result[name] = value
    return result


def _private_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and (
        os.name != "posix" or info.st_uid == os.geteuid() and not info.st_mode & 0o077
    )


def _existing_source(config: GatewayConfig) -> None:
    """A typo must not initialize a new empty registry during a backup."""
    try:
        if config.auth.management_db is not None:
            path = Path(config.auth.management_db).absolute()
            if not _private_file(path.stat(follow_symlinks=False)):
                raise ValueError
            with closing(
                sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1.0)
            ) as connection:
                metadata = dict(connection.execute("SELECT name,value FROM metadata"))
        elif config.auth.management_database_url_env is not None:
            import psycopg

            dsn = postgres_url_from_environment(config.auth.management_database_url_env)
            with psycopg.connect(
                dsn,
                connect_timeout=5,
                options="-c default_transaction_read_only=on -c statement_timeout=5000",
            ) as connection:
                metadata = dict(
                    connection.execute("SELECT name,value FROM gateway7_admin.metadata")
                )
        else:
            raise ValueError
        if metadata.get("initialized") != "1" or metadata.get("schema_version") != "2":
            raise ValueError
    except Exception:
        raise StartupError(
            "Backup requires an existing offline management database with the current schema"
        ) from None


def _write_private(path: str, document: dict[str, Any]) -> None:
    target = Path(path)
    created = False
    try:
        raw = _canonical(document)
        if len(raw) > MAX_BACKUP_BYTES:
            raise ValueError
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise StartupError("Cannot create a new private management backup file") from None


def read_backup(path: str) -> dict[str, Any]:
    try:
        target = Path(path)
        before = target.stat(follow_symlinks=False)
        if not _private_file(before) or not 0 < before.st_size <= MAX_BACKUP_BYTES:
            raise ValueError
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(target, flags), "rb") as source:
            opened = os.fstat(source.fileno())
            if not _private_file(opened) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise ValueError
            raw = source.read(MAX_BACKUP_BYTES + 1)
        if len(raw) > MAX_BACKUP_BYTES:
            raise ValueError
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if (
            type(document) is not dict
            or set(document) != {"format", "version", "sha256", "snapshot"}
            or document["format"] != "gateway7-private-backup"
            or type(document["version"]) is not int
            or document["version"] != 1
            or type(document["sha256"]) is not str
            or type(document["snapshot"]) is not dict
        ):
            raise ValueError
        digest = hashlib.sha256(_canonical(document["snapshot"])).hexdigest()
        if not hmac.compare_digest(document["sha256"], digest):
            raise ValueError
        snapshot = document["snapshot"]
        if snapshot.get("format") != "gateway7-backup" or snapshot.get("version") != 2:
            raise ValueError
        return snapshot
    except Exception:
        raise StartupError(
            "Management backup is unreadable, incompatible, not private or has an invalid checksum"
        ) from None


def backup_management(config_path: str, output: str) -> dict[str, int]:
    config = load_config(config_path)
    _existing_source(config)
    store = None
    try:
        store = open_management_store(config)
        snapshot = store.backup_snapshot()
        document = {
            "format": "gateway7-private-backup",
            "version": 1,
            "sha256": hashlib.sha256(_canonical(snapshot)).hexdigest(),
            "snapshot": snapshot,
        }
        _write_private(output, document)
        return {
            "clients": len(snapshot["clients"]),
            "audit_events": len(snapshot["audit"]),
            "usage_events": len(snapshot["events"]),
        }
    except Exception:
        raise StartupError(
            "Management backup could not be completed; stop the gateway and use a new private output file"
        ) from None
    finally:
        if store is not None:
            store.close()


def restore_management(config_path: str, source: str) -> dict[str, int]:
    snapshot = read_backup(source)
    config = load_config(config_path)
    backend = "postgres" if config.auth.management_database_url_env is not None else "sqlite"
    if not config.auth.management_enabled or snapshot.get("backend") != backend:
        raise StartupError("Restore requires the same management backend as the backup")
    # The saved registry is authoritative; restoration never imports YAML seeds.
    data = config.model_dump()
    data["auth"]["clients"] = {}
    config = GatewayConfig.model_validate(data)
    store = None
    try:
        store = open_management_store(config)
        store.restore_backup(snapshot)
        return {
            "clients": len(snapshot["clients"]),
            "audit_events": len(snapshot["audit"]),
            "usage_events": len(snapshot["events"]),
        }
    except Exception:
        raise StartupError(
            "Management restore requires an empty, offline database of the same backend"
        ) from None
    finally:
        if store is not None:
            store.close()

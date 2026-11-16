"""Offline, explicit SQLite-to-PostgreSQL transfer without changing its source."""

import json
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from collections.abc import Iterator

from gateway7.admin_store import validate_snapshot
from gateway7.config import ClientConfig, GatewayConfig
from gateway7.errors import StartupError
from gateway7.management_store import postgres_url_from_environment


@contextmanager
def sqlite_snapshot(source: str) -> Iterator[dict[str, Any]]:
    """Hold a read-only exclusive snapshot; missing sources are never created."""
    connection: sqlite3.Connection | None = None
    try:
        path = Path(source).absolute()
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            raise ValueError
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1.0)
        connection.execute("BEGIN EXCLUSIVE")
        metadata = dict(connection.execute("SELECT name,value FROM metadata"))
        if metadata.get("initialized") != "1" or set(metadata) != {"initialized", "started_at"}:
            raise ValueError
        clients, digests = {}, {}
        for client_id, specification, digest in connection.execute(
            "SELECT id,specification,digest FROM clients"
        ):
            clients[client_id] = ClientConfig.model_validate(json.loads(specification))
            if digest is not None:
                digests[client_id] = digest
        snapshot = validate_snapshot(
            {
                "schema_version": 1,
                "started_at": metadata["started_at"],
                "clients": clients,
                "digests": digests,
                "tombstones": {row[0] for row in connection.execute("SELECT id FROM tombstones")},
                "usage_rows": [
                    {"client_id": client_id, "model": model, "day": day, **json.loads(counts)}
                    for client_id, model, day, counts in connection.execute(
                        "SELECT client_id,model,day,counts FROM usage ORDER BY day,client_id,model"
                    )
                ],
            }
        )
    except Exception:
        if connection is not None:
            connection.close()
        raise StartupError(
            "Cannot read an existing, initialized, offline SQLite management database"
        ) from None
    try:
        yield snapshot
    finally:
        connection.close()


def migrate_sqlite(source: str, database_url_env: str) -> dict[str, int]:
    """Transfer the full private snapshot once into an uninitialized destination."""
    from gateway7.postgres_store import PostgresAdminStore

    dsn = postgres_url_from_environment(database_url_env)
    destination = None
    try:
        with sqlite_snapshot(source) as snapshot:
            seed = GatewayConfig.model_validate(
                {
                    "auth": {
                        "enabled": True,
                        "operator_token_env": "GATEWAY7_MIGRATION_UNUSED_OPERATOR",
                        "management_database_url_env": database_url_env,
                    }
                }
            )
            destination = PostgresAdminStore(dsn, seed, initialize=False)
            destination.import_snapshot(snapshot)
            return {
                "clients": len(snapshot["clients"]),
                "deleted_identities": len(snapshot["tombstones"]),
                "usage_rows": len(snapshot["usage_rows"]),
            }
    except StartupError:
        raise
    except Exception:
        raise StartupError(
            "Management migration requires a valid source and an empty PostgreSQL destination"
        ) from None
    finally:
        if destination is not None:
            destination.close()

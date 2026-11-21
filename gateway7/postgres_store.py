"""PostgreSQL management storage with one session owning the gateway registry.

The fixed advisory lock is scoped by PostgreSQL to the current database. It
preserves the gateway's single-owner admission contract, including while idle.
Connections are never automatically recreated after a lost session.
"""

import json
from datetime import datetime, timezone
from threading import RLock
from typing import Any

import psycopg

from gateway7.admin_store import (
    AdminStore,
    _empty_counts,
    _validate_counts,
    _validate_usage_row,
    _valid_client_ids,
)
from gateway7.control_store import ControlStoreMixin
from gateway7.config import ClientConfig, GatewayConfig
from gateway7.errors import StartupError, normalized_usage

# ASCII "G7ADMIN", below signed int64; this is the fixed per-database owner key.
ADVISORY_LOCK_KEY = 0x473741444D494E
SCHEMA_VERSION = "2"


class PostgresAdminStore(ControlStoreMixin):
    _backend_postgres = True

    """Private PostgreSQL registry and exact daily numeric accounting."""

    def __init__(self, dsn: str, seed: GatewayConfig) -> None:
        self._lock = RLock()
        self._connection: psycopg.Connection[tuple[Any, ...]] | None = None
        self.started_at = ""
        try:
            self._connection = psycopg.connect(
                dsn,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=5000 -c lock_timeout=1000",
                application_name="gateway7-admin",
            )
            lock = self._db.execute(
                "SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,)
            ).fetchone()
            if lock is None or lock[0] is not True:
                raise ValueError("Management database already has an owner")
            with self._db.transaction():
                self._db.execute("CREATE SCHEMA IF NOT EXISTS gateway7_admin")
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS gateway7_admin.metadata "
                    "(name TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS gateway7_admin.clients "
                    "(id TEXT PRIMARY KEY, specification TEXT NOT NULL, digest BYTEA)"
                )
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS gateway7_admin.tombstones (id TEXT PRIMARY KEY)"
                )
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS gateway7_admin.usage "
                    "(client_id TEXT NOT NULL, model TEXT NOT NULL, day TEXT NOT NULL, "
                    "counts TEXT NOT NULL, PRIMARY KEY (client_id,model,day))"
                )
                metadata = dict(self._db.execute("SELECT name,value FROM gateway7_admin.metadata"))
                if "schema_version" not in metadata:
                    if metadata or self._has_records():
                        raise ValueError("Missing management schema version")
                    self._db.execute(
                        "INSERT INTO gateway7_admin.metadata(name,value) VALUES ('schema_version',%s)",
                        (SCHEMA_VERSION,),
                    )
                elif metadata["schema_version"] not in ("1", SCHEMA_VERSION):
                    raise ValueError("Unsupported management schema version")
                if "initialized" in metadata:
                    if (
                        set(metadata)
                        - {
                            "schema_version",
                            "initialized",
                            "started_at",
                            "control_revision",
                            "detail_retained_from",
                        }
                        or "started_at" not in metadata
                    ):
                        raise ValueError("Invalid management metadata")
                    if metadata["initialized"] != "1":
                        raise ValueError("Invalid management initialization metadata")
                    self.started_at = metadata["started_at"]
                    if datetime.fromisoformat(self.started_at).tzinfo is None:
                        raise ValueError("Invalid management start timestamp")
                    self._validate_persisted_state()
                else:
                    if self._has_records() or set(metadata) - {"schema_version"}:
                        raise ValueError("Invalid uninitialized management database")
                    clients, digests = AdminStore._seed_clients(seed)
                    self._write_clients(clients, digests)
                    self._initialize(datetime.now(timezone.utc).isoformat())
                self._initialize_controls()
        except Exception:
            self.close()
            raise StartupError("Management database is unavailable or invalid") from None

    @property
    def _db(self) -> psycopg.Connection[tuple[Any, ...]]:
        if self._connection is None or self._connection.closed:
            raise StartupError("Management database is unavailable")
        return self._connection

    def _has_records(self) -> bool:
        row = self._db.execute(
            "SELECT EXISTS(SELECT 1 FROM gateway7_admin.clients) "
            "OR EXISTS(SELECT 1 FROM gateway7_admin.tombstones) "
            "OR EXISTS(SELECT 1 FROM gateway7_admin.usage)"
        ).fetchone()
        if row is None:
            raise StartupError("Management database is unavailable")
        return bool(row[0])

    def _initialize(self, started_at: str) -> None:
        with self._db.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO gateway7_admin.metadata(name,value) VALUES (%s,%s)",
                [("initialized", "1"), ("started_at", started_at)],
            )
        self.started_at = started_at

    def _validate_persisted_state(self) -> None:
        clients, _ = self.load_clients()
        tombstones = {
            row[0] for row in self._db.execute("SELECT id FROM gateway7_admin.tombstones")
        }
        for identity in tombstones:
            _valid_client_ids([identity])
        if tombstones & clients.keys():
            raise ValueError("Invalid deleted client registry")
        identities = clients.keys() | tombstones
        for row in self.usage_rows(client_id=None, model=None, start=None, end=None):
            if row["client_id"] not in identities:
                raise ValueError("Invalid historical usage identity")

    def load_clients(self) -> tuple[dict[str, ClientConfig], dict[str, bytes]]:
        with self._lock:
            try:
                clients: dict[str, ClientConfig] = {}
                digests: dict[str, bytes] = {}
                for identity, specification, digest in self._db.execute(
                    "SELECT id,specification,digest FROM gateway7_admin.clients ORDER BY id"
                ):
                    clients[identity] = ClientConfig.model_validate(json.loads(specification))
                    if digest is not None:
                        if type(digest) is not bytes or len(digest) != 32:
                            raise ValueError("Invalid management digest")
                        digests[identity] = digest
                AdminStore._validate_clients(clients, digests)
                return clients, digests
            except Exception:
                raise StartupError("Management database is unavailable or invalid") from None

    def _write_clients(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        AdminStore._validate_clients(clients, digests)
        existing = {row[0] for row in self._db.execute("SELECT id FROM gateway7_admin.clients")}
        tombstones = {
            row[0] for row in self._db.execute("SELECT id FROM gateway7_admin.tombstones")
        }
        if tombstones & clients.keys():
            raise ValueError("Deleted client identities cannot be reused")
        with self._db.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO gateway7_admin.tombstones(id) VALUES (%s)",
                [(identity,) for identity in existing - clients.keys()],
            )
            cursor.execute("DELETE FROM gateway7_admin.clients")
            cursor.executemany(
                "INSERT INTO gateway7_admin.clients(id,specification,digest) VALUES (%s,%s,%s)",
                [
                    (identity, client.model_dump_json(), digests.get(identity))
                    for identity, client in clients.items()
                ],
            )

    def save_clients(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        with self._lock:
            try:
                with self._db.transaction():
                    self._write_clients(clients, digests)
            except psycopg.Error:
                raise StartupError("Management database is unavailable") from None

    def usage_identities(self) -> set[str]:
        with self._lock:
            try:
                identities = {
                    row[0]
                    for row in self._db.execute(
                        "SELECT id FROM gateway7_admin.clients "
                        "UNION SELECT id FROM gateway7_admin.tombstones "
                        "UNION SELECT client_id FROM gateway7_admin.usage"
                    )
                }
                for identity in identities:
                    _valid_client_ids([identity])
                return identities
            except (psycopg.Error, ValueError):
                raise StartupError("Management database is unavailable or invalid") from None

    def record_usage(
        self, client_id: str, model: str, outcome: str, usage: dict[str, int] | None
    ) -> None:
        counts = normalized_usage(usage) or {}
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            try:
                with self._db.transaction():
                    stored = self._db.execute(
                        "SELECT counts FROM gateway7_admin.usage "
                        "WHERE client_id=%s AND model=%s AND day=%s FOR UPDATE",
                        (client_id, model, day),
                    ).fetchone()
                    row = _validate_counts(json.loads(stored[0])) if stored else _empty_counts()
                    row["provider_attempts"] += 1
                    safe_outcome = outcome if outcome in row["outcomes"] else "provider_error"
                    row["outcomes"][safe_outcome] += 1
                    for direction in ("input", "output"):
                        count = counts.get(direction + "_tokens")
                        if count is None:
                            row[direction + "_usage_unknown_attempts"] += 1
                        else:
                            row["known_" + direction + "_tokens"] += count
                    self._db.execute(
                        "INSERT INTO gateway7_admin.usage(client_id,model,day,counts) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT(client_id,model,day) "
                        "DO UPDATE SET counts=excluded.counts",
                        (client_id, model, day, json.dumps(row, separators=(",", ":"))),
                    )
            except (psycopg.Error, ValueError, KeyError, TypeError):
                raise StartupError("Management accounting is unavailable or invalid") from None

    def usage_rows(
        self, *, client_id: str | None, model: str | None, start: str | None, end: str | None
    ) -> list[dict[str, Any]]:
        query = "SELECT client_id,model,day,counts FROM gateway7_admin.usage WHERE 1=1"
        values: list[str] = []
        for condition, value in (
            ("client_id=%s", client_id),
            ("model=%s", model),
            ("day>=%s", start),
            ("day<=%s", end),
        ):
            if value is not None:
                query += " AND " + condition
                values.append(value)
        query += " ORDER BY day,client_id,model"
        with self._lock:
            try:
                return [
                    {
                        "client_id": identity,
                        "model": name,
                        "day": day,
                        **_validate_usage_row(identity, name, day, counts),
                    }
                    for identity, name, day, counts in self._db.execute(query, values)
                ]
            except (psycopg.Error, ValueError, TypeError):
                raise StartupError("Management accounting is unavailable or invalid") from None

    def ensure_available(self) -> None:
        with self._lock:
            try:
                self._db.execute("SELECT 1").fetchone()
            except psycopg.Error:
                raise StartupError("Management database is unavailable") from None

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except psycopg.Error:
                    pass
                self._connection = None

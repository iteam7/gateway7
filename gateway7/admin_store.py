"""Private, single-process SQLite state for live operator management.

The database contains credential digests and numeric accounting, never bearer
credentials or conversation content. One exclusive connection deliberately
matches the gateway's single-process admission and middleware boundary.
"""

import hashlib
import hmac
import json
import os
import re
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from gateway7.config import ClientConfig, GatewayConfig, validate_model_id
from gateway7.errors import StartupError, normalized_usage

_OUTCOMES = ("complete", "provider_error", "cancelled")
_CLIENT_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")


def _empty_counts() -> dict[str, Any]:
    return {
        "provider_attempts": 0,
        "outcomes": dict.fromkeys(_OUTCOMES, 0),
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "input_usage_unknown_attempts": 0,
        "output_usage_unknown_attempts": 0,
    }


def _validate_counts(value: object) -> dict[str, Any]:
    expected = _empty_counts()
    if type(value) is not dict or value.keys() != expected.keys():
        raise ValueError("Invalid persisted usage counters")
    outcomes = value["outcomes"]
    if type(outcomes) is not dict or outcomes.keys() != expected["outcomes"].keys():
        raise ValueError("Invalid persisted usage outcomes")
    numbers = [count for key, count in value.items() if key != "outcomes"]
    numbers.extend(outcomes.values())
    if any(type(count) is not int or count < 0 for count in numbers):
        raise ValueError("Invalid persisted usage counters")
    attempts = value["provider_attempts"]
    if sum(outcomes.values()) != attempts or any(
        value[direction + "_usage_unknown_attempts"] > attempts for direction in ("input", "output")
    ):
        raise ValueError("Inconsistent persisted usage counters")
    return value


def _validate_usage_row(client_id: str, model: str, day: str, counts: str) -> dict[str, Any]:
    _valid_client_ids([client_id])
    validate_model_id(model)
    if type(day) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is None:
        raise ValueError("Invalid persisted usage day")
    date.fromisoformat(day)
    return _validate_counts(json.loads(counts))


def _add_counts(total: dict[str, Any], counts: dict[str, Any]) -> None:
    for key in total:
        if key == "outcomes":
            for outcome in _OUTCOMES:
                total[key][outcome] += counts[key][outcome]
        else:
            total[key] += counts[key]


def _valid_client_ids(client_ids: Iterable[str]) -> tuple[str, ...]:
    ids = tuple(client_ids)
    if (
        len(ids) > 128
        or len(ids) != len(set(ids))
        or any(type(value) is not str or _CLIENT_ID.fullmatch(value) is None for value in ids)
    ):
        raise ValueError("Invalid managed client identities")
    return ids


def _valid_token(token: str) -> bool:
    return 16 <= len(token) <= 512 and token.isascii() and all(33 <= ord(c) <= 126 for c in token)


class ManagementStore(Protocol):
    """Durable backend boundary shared by SQLite and PostgreSQL."""

    started_at: str

    def load_clients(self) -> tuple[dict[str, ClientConfig], dict[str, bytes]]: ...

    def save_clients(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None: ...

    def usage_identities(self) -> set[str]: ...

    def record_usage(
        self, client_id: str, model: str, outcome: str, usage: dict[str, int] | None
    ) -> None: ...

    def usage_rows(
        self, *, client_id: str | None, model: str | None, start: str | None, end: str | None
    ) -> list[dict[str, Any]]: ...

    def ensure_available(self) -> None: ...

    def export_snapshot(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate a private offline migration snapshot without exposing its contents."""
    try:
        if type(snapshot) is not dict or snapshot.keys() != {
            "schema_version",
            "started_at",
            "clients",
            "digests",
            "tombstones",
            "usage_rows",
        }:
            raise ValueError
        if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
            raise ValueError
        started_at = snapshot["started_at"]
        if type(started_at) is not str or datetime.fromisoformat(started_at).tzinfo is None:
            raise ValueError
        clients, digests = snapshot["clients"], snapshot["digests"]
        if type(clients) is not dict or type(digests) is not dict:
            raise ValueError
        AdminStore._validate_clients(clients, digests)
        tombstones = snapshot["tombstones"]
        if type(tombstones) is not set or tombstones & clients.keys():
            raise ValueError
        for identity in tombstones:
            _valid_client_ids([identity])
        rows = snapshot["usage_rows"]
        if type(rows) is not list:
            raise ValueError
        seen: set[tuple[str, str, str]] = set()
        normalized_rows = []
        for row in rows:
            if type(row) is not dict or row.keys() != {
                "client_id",
                "model",
                "day",
                *_empty_counts().keys(),
            }:
                raise ValueError
            key = (row["client_id"], row["model"], row["day"])
            if key in seen or key[0] not in clients.keys() | tombstones:
                raise ValueError
            seen.add(key)
            counts = {name: row[name] for name in _empty_counts()}
            normalized_rows.append(
                {
                    "client_id": key[0],
                    "model": key[1],
                    "day": key[2],
                    **_validate_usage_row(*key, json.dumps(counts)),
                }
            )
        return {
            "schema_version": 1,
            "started_at": started_at,
            "clients": {
                identity: ClientConfig.model_validate(client.model_dump())
                for identity, client in clients.items()
            },
            "digests": dict(digests),
            "tombstones": set(tombstones),
            "usage_rows": normalized_rows,
        }
    except Exception:
        raise ValueError("Invalid management migration snapshot") from None


class AdminStore:
    """Atomic client policies, token digests, tombstones and daily counters."""

    def __init__(self, path: str, seed: GatewayConfig) -> None:
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        try:
            target = Path(path)
            if not path or path == ":memory:":
                raise ValueError("A persistent management database path is required")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Refuse a symlink database and create new files with private permissions
            # before SQLite opens them. Existing file permissions are tightened too.
            if target.is_symlink():
                raise ValueError("Management database cannot be a symlink")
            descriptor = os.open(
                target, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
                else:
                    target.chmod(0o600)
            finally:
                os.close(descriptor)
            self._connection = sqlite3.connect(target, timeout=1.0, check_same_thread=False)
            self._connection.execute("PRAGMA locking_mode=EXCLUSIVE")
            self._connection.execute("PRAGMA journal_mode=DELETE")
            self._connection.execute("PRAGMA synchronous=FULL")
            with self._connection:
                self._connection.execute("BEGIN EXCLUSIVE")
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS clients "
                    "(id TEXT PRIMARY KEY, specification TEXT NOT NULL, digest BLOB)"
                )
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS tombstones (id TEXT PRIMARY KEY)"
                )
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS usage "
                    "(client_id TEXT NOT NULL, model TEXT NOT NULL, day TEXT NOT NULL, "
                    "counts TEXT NOT NULL, PRIMARY KEY (client_id, model, day))"
                )
                initialized = self._connection.execute(
                    "SELECT value FROM metadata WHERE name='initialized'"
                ).fetchone()
                if initialized is None:
                    if any(
                        self._connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                        for table in ("clients", "tombstones", "usage", "metadata")
                    ):
                        raise ValueError("Missing database initialization metadata")
                    clients, digests = self._seed_clients(seed)
                    self._write_clients(clients, digests)
                    self._connection.executemany(
                        "INSERT INTO metadata (name,value) VALUES (?,?)",
                        [
                            ("initialized", "1"),
                            ("started_at", datetime.now(timezone.utc).isoformat()),
                        ],
                    )
                elif initialized[0] != "1":
                    raise ValueError("Invalid database initialization metadata")
            # Validate stored configuration eagerly; corrupt state never silently
            # falls back to YAML credentials or starts with an empty registry.
            self.load_clients()
            self.started_at = self._db.execute(
                "SELECT value FROM metadata WHERE name='started_at'"
            ).fetchone()[0]
            if datetime.fromisoformat(self.started_at).tzinfo is None:
                raise ValueError("Invalid database start timestamp")
            for row in self._db.execute("SELECT client_id,model,day,counts FROM usage"):
                _validate_usage_row(*row)
            for (client_id,) in self._db.execute("SELECT id FROM tombstones"):
                _valid_client_ids([client_id])
            if self._db.execute(
                "SELECT 1 FROM clients INNER JOIN tombstones USING(id) LIMIT 1"
            ).fetchone():
                raise ValueError("Invalid deleted client registry")
        except Exception:
            self.close()
            raise StartupError("Management database is unavailable or invalid") from None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StartupError("Management database is unavailable")
        return self._connection

    @staticmethod
    def _seed_clients(seed: GatewayConfig) -> tuple[dict[str, ClientConfig], dict[str, bytes]]:
        digests: dict[str, bytes] = {}
        reserved = [os.environ.get(seed.provider.key_env, "")]
        if seed.auth.operator_token_env is not None:
            reserved.append(os.environ.get(seed.auth.operator_token_env, ""))
        reserved_digests = [hashlib.sha256(value.encode()).digest() for value in reserved if value]
        for client_id, client in seed.auth.clients.items():
            additional = client.additional_middleware
            if (
                len(additional) != len(set(additional))
                or any(name in seed.middleware for name in additional)
                or any(
                    name not in seed.plugins or not seed.plugins[name].enabled
                    for name in additional
                )
            ):
                raise ValueError("Invalid bootstrap client middleware")
            token = os.environ.get(client.token_env, "")
            if not _valid_token(token):
                if client.enabled:
                    raise ValueError("Invalid bootstrap credential")
                continue
            digest = hashlib.sha256(token.encode("ascii")).digest()
            if any(hmac.compare_digest(digest, other) for other in reserved_digests):
                raise ValueError("Bootstrap credentials must be distinct")
            if any(hmac.compare_digest(digest, other) for other in digests.values()):
                raise ValueError("Bootstrap credentials must be distinct")
            digests[client_id] = digest
        return dict(seed.auth.clients), digests

    def load_clients(self) -> tuple[dict[str, ClientConfig], dict[str, bytes]]:
        with self._lock:
            try:
                clients: dict[str, ClientConfig] = {}
                digests: dict[str, bytes] = {}
                for client_id, specification, digest in self._db.execute(
                    "SELECT id,specification,digest FROM clients ORDER BY id"
                ):
                    clients[client_id] = ClientConfig.model_validate(json.loads(specification))
                    if digest is not None:
                        if type(digest) is not bytes or len(digest) != 32:
                            raise ValueError("Invalid credential digest")
                        digests[client_id] = digest
                self._validate_clients(clients, digests)
                return clients, digests
            except Exception:
                raise StartupError("Management database is unavailable or invalid") from None

    @staticmethod
    def _validate_clients(clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        _valid_client_ids(clients)
        if set(digests) - clients.keys():
            raise ValueError("Unknown managed credential identity")
        for specification in clients.values():
            ClientConfig.model_validate(specification.model_dump())
        if any(type(value) is not bytes or len(value) != 32 for value in digests.values()):
            raise ValueError("Invalid managed credential digest")
        if len(set(digests.values())) != len(digests):
            raise ValueError("Managed credentials must be distinct")

    def _write_clients(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        self._validate_clients(clients, digests)
        existing = {row[0] for row in self._db.execute("SELECT id FROM clients")}
        removed = existing - clients.keys()
        tombstones = {row[0] for row in self._db.execute("SELECT id FROM tombstones")}
        if tombstones & clients.keys():
            raise ValueError("Deleted client identities cannot be reused")
        self._db.executemany("INSERT INTO tombstones(id) VALUES (?)", [(key,) for key in removed])
        self._db.execute("DELETE FROM clients")
        self._db.executemany(
            "INSERT INTO clients(id,specification,digest) VALUES (?,?,?)",
            [
                (client_id, specification.model_dump_json(), digests.get(client_id))
                for client_id, specification in clients.items()
            ],
        )

    def save_clients(self, clients: dict[str, ClientConfig], digests: dict[str, bytes]) -> None:
        with self._lock:
            try:
                with self._db:
                    self._write_clients(clients, digests)
            except sqlite3.Error:
                raise StartupError("Management database is unavailable") from None

    def usage_identities(self) -> set[str]:
        with self._lock:
            try:
                return {
                    row[0]
                    for row in self._db.execute(
                        "SELECT id FROM clients UNION SELECT id FROM tombstones "
                        "UNION SELECT client_id FROM usage"
                    )
                }
            except sqlite3.Error:
                raise StartupError("Management database is unavailable") from None

    def record_usage(
        self, client_id: str, model: str, outcome: str, usage: dict[str, int] | None
    ) -> None:
        counts = normalized_usage(usage) or {}
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            try:
                with self._db:
                    stored = self._db.execute(
                        "SELECT counts FROM usage WHERE client_id=? AND model=? AND day=?",
                        (client_id, model, day),
                    ).fetchone()
                    row = _validate_counts(json.loads(stored[0])) if stored else _empty_counts()
                    row["provider_attempts"] += 1
                    row["outcomes"][outcome if outcome in _OUTCOMES else "provider_error"] += 1
                    for direction in ("input", "output"):
                        count = counts.get(direction + "_tokens")
                        if count is None:
                            row[direction + "_usage_unknown_attempts"] += 1
                        else:
                            row["known_" + direction + "_tokens"] += count
                    self._db.execute(
                        "INSERT INTO usage(client_id,model,day,counts) VALUES (?,?,?,?) "
                        "ON CONFLICT(client_id,model,day) DO UPDATE SET counts=excluded.counts",
                        (client_id, model, day, json.dumps(row, separators=(",", ":"))),
                    )
            except (sqlite3.Error, ValueError, KeyError, TypeError):
                raise StartupError("Management accounting is unavailable or invalid") from None

    def usage_rows(
        self, *, client_id: str | None, model: str | None, start: str | None, end: str | None
    ) -> list[dict[str, Any]]:
        query = "SELECT client_id,model,day,counts FROM usage WHERE 1=1"
        values: list[str] = []
        for condition, value in (
            ("client_id=?", client_id),
            ("model=?", model),
            ("day>=?", start),
            ("day<=?", end),
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
            except (sqlite3.Error, ValueError, TypeError):
                raise StartupError("Management accounting is unavailable or invalid") from None

    def ensure_available(self) -> None:
        with self._lock:
            try:
                self._db.execute("SELECT 1").fetchone()
            except sqlite3.Error:
                raise StartupError("Management database is unavailable") from None

    def export_snapshot(self) -> dict[str, Any]:
        with self._lock:
            try:
                clients, digests = self.load_clients()
                return validate_snapshot(
                    {
                        "schema_version": 1,
                        "started_at": self.started_at,
                        "clients": clients,
                        "digests": digests,
                        "tombstones": {
                            row[0] for row in self._db.execute("SELECT id FROM tombstones")
                        },
                        "usage_rows": self.usage_rows(
                            client_id=None, model=None, start=None, end=None
                        ),
                    }
                )
            except (sqlite3.Error, ValueError):
                raise StartupError("Management database is unavailable or invalid") from None

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except sqlite3.Error:
                    pass
                self._connection = None

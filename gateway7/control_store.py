"""Versioned, private operational documents and bounded history for both backends."""

import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from gateway7.errors import StartupError


def utc_timestamp(value: str | None = None) -> str:
    """Normalize an aware RFC3339 instant to lexically sortable UTC microseconds."""
    parsed = (
        datetime.now(timezone.utc)
        if value is None
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


class ControlConflict(ValueError):
    """The caller must refresh before changing a concurrently edited document."""


class ControlStoreMixin:
    """Backend SQL is fixed; document names and values are always parameters."""

    _backend_postgres = False

    def _control_query(self, sql: str, values: tuple[Any, ...] | list[Any] = ()) -> Any:
        prefix = "gateway7_admin." if self._backend_postgres else ""
        sql = sql.replace("{prefix}", prefix)
        if self._backend_postgres:
            sql = sql.replace("?", "%s")
        return self._db.execute(sql, values)  # type: ignore[attr-defined]

    @contextmanager
    def _control_transaction(self):
        database = self._db  # type: ignore[attr-defined]
        if self._backend_postgres:
            with database.transaction():
                yield
            return
        # Explicit BEGIN includes SQLite DDL in the schema-upgrade transaction.
        # Savepoints keep nested reserve/settle helpers from committing an outer
        # control transaction before its publication or rollback has completed.
        if database.in_transaction:
            savepoint = "control_" + uuid.uuid4().hex
            database.execute("SAVEPOINT " + savepoint)
            try:
                yield
            except BaseException:
                database.execute("ROLLBACK TO SAVEPOINT " + savepoint)
                database.execute("RELEASE SAVEPOINT " + savepoint)
                raise
            else:
                database.execute("RELEASE SAVEPOINT " + savepoint)
        else:
            database.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                database.rollback()
                raise
            else:
                database.commit()

    def _initialize_controls(self) -> None:
        with self._control_transaction():
            version = self._control_query(
                "SELECT value FROM {prefix}metadata WHERE name='schema_version'"
            ).fetchone()
            if version is not None and version[0] not in ("1", "2"):
                raise ValueError("Unsupported management schema version")
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}archived_usage "
                "(client_id TEXT NOT NULL, model TEXT NOT NULL, day TEXT NOT NULL, "
                "value TEXT NOT NULL, PRIMARY KEY (client_id, model, day))"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}legacy_usage "
                "(client_id TEXT NOT NULL, model TEXT NOT NULL, day TEXT NOT NULL, "
                "counts TEXT NOT NULL, PRIMARY KEY (client_id, model, day))"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}control_documents "
                "(name TEXT PRIMARY KEY, revision BIGINT NOT NULL, value TEXT NOT NULL)"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}control_audit "
                "(id TEXT PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, "
                "action TEXT NOT NULL, target TEXT NOT NULL, revision BIGINT NOT NULL, value TEXT NOT NULL)"
            )
            self._control_query(
                "CREATE INDEX IF NOT EXISTS control_audit_at ON {prefix}control_audit(at,id)"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}key_activity (id TEXT PRIMARY KEY, last_used_at TEXT NOT NULL)"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}operator_sessions "
                "(digest TEXT PRIMARY KEY, operator_id TEXT NOT NULL, expires_at TEXT NOT NULL, "
                "created_at TEXT NOT NULL, value TEXT NOT NULL)"
            )
            self._control_query(
                "CREATE TABLE IF NOT EXISTS {prefix}usage_events "
                "(id TEXT PRIMARY KEY, started_at TEXT NOT NULL, client_id TEXT NOT NULL, "
                "model TEXT NOT NULL, key_id TEXT, status TEXT NOT NULL, value TEXT NOT NULL)"
            )
            self._control_query(
                "CREATE INDEX IF NOT EXISTS usage_events_started ON {prefix}usage_events(started_at,id)"
            )
            self._control_query(
                "CREATE INDEX IF NOT EXISTS usage_events_client ON {prefix}usage_events(client_id,model,started_at)"
            )
            row = self._control_query(
                "SELECT value FROM {prefix}metadata WHERE name='control_revision'"
            ).fetchone()
            if row is None:
                self._control_query(
                    "INSERT INTO {prefix}legacy_usage(client_id,model,day,counts) "
                    "SELECT client_id,model,day,counts FROM {prefix}usage"
                )
                self._control_query(
                    "INSERT INTO {prefix}metadata(name,value) VALUES ('control_revision','0')"
                )
            else:
                if type(row[0]) is not str or not row[0].isdigit():
                    raise ValueError("Invalid management revision")
                if self.read_control()["revision"] != int(row[0]):
                    raise ValueError("Management revision metadata is inconsistent")
            from gateway7.accounting import _configuration, validate_event

            _validate_control_data(self.read_control()["data"])
            _configuration(self)
            known_clients = self.load_clients()[0].keys() | {  # type: ignore[attr-defined]
                row[0] for row in self._control_query("SELECT id FROM {prefix}tombstones")
            }
            for stored in self._control_query("SELECT value FROM {prefix}usage_events"):
                event = json.loads(stored[0])
                validate_event(event)
                if event["client_id"] not in known_clients:
                    raise ValueError("Unknown stored accounting identity")
            from gateway7.admin_store import _empty_counts, _validate_usage_row

            for table, column in (("legacy_usage", "counts"), ("archived_usage", "value")):
                for identity, model, day, value in self._control_query(
                    "SELECT client_id,model,day," + column + " FROM {prefix}" + table
                ):
                    decoded = json.loads(value)
                    _validate_usage_row(
                        identity,
                        model,
                        day,
                        json.dumps({key: decoded[key] for key in _empty_counts()}),
                    )
                    if identity not in known_clients:
                        raise ValueError("Unknown stored accounting identity")
                    if table == "archived_usage" and any(
                        type(decoded.get(key)) is not int or decoded[key] < 0
                        for key in ("cost_micro_usd", "unknown_cost_attempts")
                    ):
                        raise ValueError("Invalid archived accounting totals")
            boundary = self._control_query(
                "SELECT value FROM {prefix}metadata WHERE name='detail_retained_from'"
            ).fetchone()
            if boundary:
                utc_timestamp(boundary[0])
            for identity, at in self._control_query(
                "SELECT id,last_used_at FROM {prefix}key_activity"
            ):
                _identifier(identity)
                utc_timestamp(at)
            self._control_query(
                "INSERT INTO {prefix}metadata(name,value) VALUES ('schema_version','2') "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value"
            )

    def create_operator_session(self, digest: str, value: dict[str, Any]) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Invalid session")
        if set(value) != {"operator_id", "password_version", "created_at", "expires_at"}:
            raise ValueError("Invalid session")
        _identifier(value["operator_id"])
        created, expires = utc_timestamp(value["created_at"]), utc_timestamp(value["expires_at"])
        if (
            type(value["password_version"]) is not int
            or value["password_version"] < 1
            or expires <= created
        ):
            raise ValueError("Invalid session")
        normalized = {**value, "created_at": created, "expires_at": expires}
        with self._lock, self._control_transaction():  # type: ignore[attr-defined]
            try:
                self._control_query(
                    "DELETE FROM {prefix}operator_sessions WHERE expires_at<=?", (utc_timestamp(),)
                )
                # Evict the oldest sessions before insertion; no unbounded login history.
                for where, parameters, keep in (
                    (" WHERE operator_id=?", (value["operator_id"],), 15),
                    ("", (), 1023),
                ):
                    rows = list(
                        self._control_query(
                            "SELECT digest FROM {prefix}operator_sessions"
                            + where
                            + " ORDER BY created_at DESC,digest DESC",
                            parameters,
                        )
                    )
                    for row in rows[keep:]:
                        self._control_query(
                            "DELETE FROM {prefix}operator_sessions WHERE digest=?", (row[0],)
                        )
                self._control_query(
                    "INSERT INTO {prefix}operator_sessions(digest,operator_id,expires_at,created_at,value) VALUES (?,?,?,?,?)",
                    (digest, value["operator_id"], expires, created, json.dumps(normalized)),
                )
            except Exception:
                raise StartupError("Operator session storage is unavailable") from None

    def get_operator_session(self, digest: str) -> dict[str, Any] | None:
        with self._lock:  # type: ignore[attr-defined]
            try:
                row = self._control_query(
                    "SELECT value FROM {prefix}operator_sessions WHERE digest=? AND expires_at>?",
                    (digest, utc_timestamp()),
                ).fetchone()
                if row is None:
                    return None
                value = json.loads(row[0])
                if (
                    set(value) != {"operator_id", "password_version", "created_at", "expires_at"}
                    or type(value["password_version"]) is not int
                    or value["password_version"] < 1
                ):
                    raise ValueError
                _identifier(value["operator_id"])
                utc_timestamp(value["created_at"])
                utc_timestamp(value["expires_at"])
                return value
            except Exception:
                raise StartupError("Operator session storage is unavailable") from None

    def delete_operator_session(self, digest: str) -> None:
        with self._lock, self._control_transaction():  # type: ignore[attr-defined]
            try:
                self._control_query(
                    "DELETE FROM {prefix}operator_sessions WHERE digest=?", (digest,)
                )
            except Exception:
                raise StartupError("Operator session storage is unavailable") from None

    def read_control(self) -> dict[str, Any]:
        with self._lock:  # type: ignore[attr-defined]
            try:
                row = self._control_query(
                    "SELECT revision,value FROM {prefix}control_documents WHERE name='control'"
                ).fetchone()
                if row is None:
                    return {"revision": 0, "data": {}}
                data = json.loads(row[1])
                if type(row[0]) is not int or row[0] < 0 or type(data) is not dict:
                    raise ValueError
                return {"revision": row[0], "data": data}
            except Exception:
                raise StartupError("Management control state is unavailable or invalid") from None

    def write_control(
        self,
        expected_revision: int,
        data: dict[str, Any],
        audit: dict[str, Any],
        *,
        clients: Any = None,
        digests: Any = None,
    ) -> int:
        if type(expected_revision) is not int or expected_revision < 0 or type(data) is not dict:
            raise ValueError("Invalid management control update")
        _validate_control_data(data)
        payload = _bounded_json(data, 2 * 1024 * 1024)
        entry = _audit_entry(audit)
        with self._lock:  # type: ignore[attr-defined]
            try:
                with self._control_transaction():
                    current = self.read_control()
                    if current["revision"] != expected_revision:
                        raise ControlConflict("Management state changed; refresh before saving")
                    revision = expected_revision + 1
                    if (clients is None) != (digests is None):
                        raise ValueError("Client profiles and digests must be saved together")
                    if clients is not None:
                        self._write_clients(clients, digests)  # type: ignore[attr-defined]
                    self._control_query(
                        "INSERT INTO {prefix}control_documents(name,revision,value) VALUES ('control',?,?) "
                        "ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,value=excluded.value",
                        (revision, payload),
                    )
                    self._control_query(
                        "UPDATE {prefix}metadata SET value=? WHERE name='control_revision'",
                        (str(revision),),
                    )
                    entry["revision"] = revision
                    self._control_query(
                        "INSERT INTO {prefix}control_audit(id,at,actor,action,target,revision,value) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            entry["id"],
                            entry["timestamp"],
                            entry["actor"],
                            entry["action"],
                            entry["target"],
                            revision,
                            _bounded_json(entry, 32768),
                        ),
                    )
                    return revision
            except (ControlConflict, ValueError):
                raise
            except Exception:
                raise StartupError("Management control update could not be saved") from None

    def list_audit(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        target: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        _page(offset, limit)
        where, values = _history_filters(
            start=start, end=end, actor=actor, action=action, target=target
        )
        with self._lock:  # type: ignore[attr-defined]
            try:
                total = self._control_query(
                    "SELECT COUNT(*) FROM {prefix}control_audit" + where, values
                ).fetchone()[0]
                rows = self._control_query(
                    "SELECT value FROM {prefix}control_audit"
                    + where
                    + " ORDER BY at DESC,id DESC LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                )
                return {
                    "items": [json.loads(row[0]) for row in rows],
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            except Exception:
                raise StartupError("Management audit history is unavailable") from None

    def touch_key(self, key_id: str, timestamp: str) -> None:
        _identifier(key_id)
        timestamp = utc_timestamp(timestamp)
        with self._lock:  # type: ignore[attr-defined]
            try:
                with self._control_transaction():
                    self._control_query(
                        "INSERT INTO {prefix}key_activity(id,last_used_at) VALUES (?,?) "
                        "ON CONFLICT(id) DO UPDATE SET last_used_at=excluded.last_used_at "
                        "WHERE excluded.last_used_at > {prefix}key_activity.last_used_at",
                        (key_id, timestamp),
                    )
            except Exception:
                raise StartupError("Key activity could not be saved") from None

    def key_last_used(self) -> dict[str, str]:
        with self._lock:  # type: ignore[attr-defined]
            try:
                return dict(self._control_query("SELECT id,last_used_at FROM {prefix}key_activity"))
            except Exception:
                raise StartupError("Key activity is unavailable") from None

    def list_usage_events(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        client_id: str | None = None,
        model: str | None = None,
        status: str | None = None,
        key_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        _page(offset, limit)
        clauses, values = [], []
        for name, value in (
            ("started_at>=", utc_timestamp(start) if start else None),
            ("started_at<", utc_timestamp(end) if end else None),
            ("client_id=", client_id),
            ("model=", model),
            ("status=", status),
            ("key_id=", key_id),
        ):
            if value is not None:
                clauses.append(name + "?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:  # type: ignore[attr-defined]
            try:
                total = self._control_query(
                    "SELECT COUNT(*) FROM {prefix}usage_events" + where, values
                ).fetchone()[0]
                rows = self._control_query(
                    "SELECT value FROM {prefix}usage_events"
                    + where
                    + " ORDER BY started_at DESC,id DESC LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                )
                return {
                    "items": [json.loads(row[0]) for row in rows],
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            except ValueError:
                raise
            except Exception:
                raise StartupError("Usage history is unavailable") from None

    def usage_export_page(
        self,
        *,
        start: str,
        end: str,
        client_id: str | None,
        model: str | None,
        after: tuple[str, str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        _page(0, limit)
        predicate = (
            "(value::jsonb->>'kind')='provider'"
            if self._backend_postgres
            else "json_extract(value,'$.kind')='provider'"
        )
        sql = (
            "SELECT value FROM {prefix}usage_events WHERE started_at>=? AND started_at<? AND "
            + predicate
        )
        values: list[Any] = [start, end]
        for name, value in (("client_id", client_id), ("model", model)):
            if value is not None:
                sql += " AND " + name + "=?"
                values.append(value)
        if after is not None:
            sql += " AND (started_at>? OR (started_at=? AND id>?))"
            values.extend((after[0], after[0], after[1]))
        sql += " ORDER BY started_at,id LIMIT ?"
        values.append(limit)
        return [json.loads(row[0]) for row in self._control_query(sql, values)]

    def legacy_export_page(
        self,
        *,
        start: str,
        end: str,
        client_id: str | None,
        model: str | None,
        after: tuple[str, str, str, str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        _page(0, limit)
        first = datetime.fromisoformat(start)
        if first.time().isoformat() != "00:00:00":
            first += timedelta(days=1)
        last = datetime.fromisoformat(end) - timedelta(days=1)
        branches: list[str] = []
        values: list[Any] = []
        for table, column, source in (
            ("legacy_usage", "counts", "legacy"),
            ("archived_usage", "value", "archived"),
        ):
            sql = (
                "SELECT client_id,model,day,"
                + column
                + " AS value,'"
                + source
                + "' AS source FROM {prefix}"
                + table
                + " WHERE day>=? AND day<=?"
            )
            values.extend((first.date().isoformat(), last.date().isoformat()))
            for name, value in (("client_id", client_id), ("model", model)):
                if value is not None:
                    sql += " AND " + name + "=?"
                    values.append(value)
            branches.append(sql)
        query = (
            "SELECT client_id,model,day,value,source FROM ("
            + " UNION ALL ".join(branches)
            + ") AS combined"
        )
        if after is not None:
            query += " WHERE (day,client_id,model,source)>(?,?,?,?)"
            values.extend(after)
        query += " ORDER BY day,client_id,model,source LIMIT ?"
        values.append(limit)
        result = []
        for identity, name, day, encoded, source in self._control_query(query, values):
            row = json.loads(encoded)
            if source == "legacy":
                row.update(cost_micro_usd=0, unknown_cost_attempts=row["provider_attempts"])
            result.append(
                {"client_id": identity, "model": name, "day": day, "source": source, **row}
            )
        return result

    def usage_group_page(
        self,
        *,
        start: str,
        end: str,
        client_id: str | None,
        model: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        _page(offset, limit)
        predicate = (
            "(value::jsonb->>'kind')='provider'"
            if self._backend_postgres
            else "json_extract(value,'$.kind')='provider'"
        )
        event_sql = (
            "SELECT client_id,model,substr(started_at,1,10) AS day FROM {prefix}usage_events WHERE started_at>=? AND started_at<? AND "
            + predicate
        )
        values: list[Any] = [start, end]
        for name, value in (("client_id", client_id), ("model", model)):
            if value is not None:
                event_sql += " AND " + name + "=?"
                values.append(value)
        event_sql += " GROUP BY client_id,model,substr(started_at,1,10)"
        first = datetime.fromisoformat(start)
        if first.time().isoformat() != "00:00:00":
            first = first + timedelta(days=1)
        last = datetime.fromisoformat(end) - timedelta(days=1)
        legacy_sql = "SELECT client_id,model,day FROM {prefix}legacy_usage WHERE day>=? AND day<=?"
        values.extend([first.date().isoformat(), last.date().isoformat()])
        for name, value in (("client_id", client_id), ("model", model)):
            if value is not None:
                legacy_sql += " AND " + name + "=?"
                values.append(value)
        archived_sql = legacy_sql.replace("{prefix}legacy_usage", "{prefix}archived_usage")
        legacy_values = values[
            len(values) - (2 + int(client_id is not None) + int(model is not None)) :
        ]
        values.extend(legacy_values)
        grouped = (
            "(" + event_sql + " UNION " + legacy_sql + " UNION " + archived_sql + ") AS grouped"
        )
        total = self._control_query("SELECT COUNT(*) FROM " + grouped, values).fetchone()[0]
        keys = list(
            self._control_query(
                "SELECT client_id,model,day FROM "
                + grouped
                + " ORDER BY client_id,model,day LIMIT ? OFFSET ?",
                [*values, limit, offset],
            )
        )
        return {"keys": keys, "total": total}

    def _put_usage_event(self, event: dict[str, Any]) -> None:
        self._control_query(
            "INSERT INTO {prefix}usage_events(id,started_at,client_id,model,key_id,status,value) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status,value=excluded.value",
            (
                event["id"],
                event["started_at"],
                event["client_id"],
                event["model"],
                event.get("key_id"),
                event["status"],
                _bounded_json(event, 32768),
            ),
        )

    def _get_usage_event(self, attempt_id: str) -> dict[str, Any]:
        row = self._control_query(
            "SELECT value FROM {prefix}usage_events WHERE id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown accounting attempt")
        return json.loads(row[0])

    def reserve_usage(
        self,
        client_id: str,
        model: str,
        input_bound: int | None,
        output_bound: int | None,
        *,
        key_id: str | None = None,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        from gateway7.accounting import reserve_locked

        with self._lock:  # type: ignore[attr-defined]
            try:
                with self._control_transaction():
                    return reserve_locked(
                        self,
                        client_id,
                        model,
                        input_bound,
                        output_bound,
                        key_id=key_id,
                        started_at=started_at,
                    )
            except (ValueError, StartupError):
                raise
            except Exception:
                raise StartupError("Usage reservation could not be saved") from None

    def settle_usage(
        self,
        attempt_id: str,
        outcome: str,
        usage: dict[str, int] | None,
        *,
        duration_ms: int = 0,
        http_outcome: str | None = None,
    ) -> dict[str, Any]:
        from gateway7.accounting import settle_locked

        with self._lock:  # type: ignore[attr-defined]
            try:
                with self._control_transaction():
                    return settle_locked(
                        self,
                        attempt_id,
                        outcome,
                        usage,
                        duration_ms=duration_ms,
                        http_outcome=http_outcome,
                    )
            except (ValueError, StartupError):
                raise
            except Exception:
                raise StartupError("Usage settlement could not be saved") from None

    def backup_snapshot(self) -> dict[str, Any]:
        try:
            return _backup_snapshot(self)
        except Exception:
            raise StartupError("Management backup is unavailable") from None

    def restore_backup(self, snapshot: dict[str, Any]) -> None:
        _restore_backup(self, snapshot)


def _validate_control_data(data: dict[str, Any]) -> None:
    if type(data) is not dict:
        raise ValueError("Invalid management control document")
    if "identity" in data:
        from gateway7.identity_records import validate_identity

        validate_identity(data["identity"])
    if "policies" in data:
        from gateway7.policy_admin import validate_policy_document

        validate_policy_document(data["policies"])
    if "accounting" in data:
        from gateway7.accounting import validate_prices, validate_rules

        accounting = data["accounting"]
        if type(accounting) is not dict:
            raise ValueError("Invalid stored accounting configuration")
        pricing = accounting.get("pricing", {"revision": 0, "prices": []})
        if (
            type(pricing) is not dict
            or type(pricing.get("revision", 0)) is not int
            or pricing.get("revision", 0) < 0
        ):
            raise ValueError("Invalid pricing revision")
        validate_prices(pricing.get("prices", []))
        validate_rules(accounting.get("budgets", {}).get("rules", []))
        days = accounting.get("retention", {}).get("days", 90)
        if type(days) is not int or not 32 <= days <= 3650:
            raise ValueError("Invalid accounting retention")
    if "provider" in data:
        import base64
        from gateway7.provider_admin import ProviderUpdate

        provider = data["provider"]
        if type(provider) is not dict or "credential" in provider:
            raise ValueError("Invalid stored provider configuration")
        editable = {
            key: value
            for key, value in provider.items()
            if key not in ("credential_ciphertext", "credential_updated_at")
        }
        ProviderUpdate.model_validate(editable)
        if "credential_ciphertext" in provider:
            encrypted = provider["credential_ciphertext"]
            if type(encrypted) is not str or len(encrypted) > 16384:
                raise ValueError("Invalid stored provider credential")
            decoded = base64.b64decode(encrypted.encode("ascii"), altchars=b"-_", validate=True)
            if len(decoded) < 73 or decoded[0] != 128:
                raise ValueError("Invalid stored provider credential")
            utc_timestamp(provider["credential_updated_at"])
        elif "credential_updated_at" in provider:
            raise ValueError("Missing stored provider credential")


def _identifier(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,128}", value) is None:
        raise ValueError("Invalid management identifier")
    return value


def _bounded_json(value: Any, maximum: int) -> str:
    encoded = json.dumps(value, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > maximum:
        raise ValueError("Management document is too large")
    return encoded


def _audit_entry(value: dict[str, Any]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Invalid audit event")
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": utc_timestamp(value.get("timestamp")),
        "actor": _identifier(value.get("actor", "system")),
        "action": _identifier(value.get("action", "update")),
        "target": _identifier(value.get("target", "control")),
        "request_id": _identifier(value.get("request_id", "internal")),
        "diff": value.get("diff", []),
    }
    # A diff records field names or explicitly safe summaries, never secret material.
    forbidden = ("password", "ciphertext", "credential", "digest", "secret", "token", "dsn")

    def redact(current: Any) -> Any:
        if isinstance(current, dict):
            return {
                str(key): "[redacted]"
                if any(word in str(key).lower() for word in forbidden)
                else redact(child)
                for key, child in current.items()
            }
        if isinstance(current, list):
            return [redact(child) for child in current[:128]]
        if current is None or type(current) in (str, int, bool):
            return current
        raise ValueError("Invalid audit diff")

    entry["diff"] = redact(entry["diff"])
    _bounded_json(entry, 32768)
    return entry


def _page(offset: int, limit: int) -> None:
    if (
        type(offset) is not int
        or offset < 0
        or offset > 10_000_000
        or type(limit) is not int
        or not 1 <= limit <= 500
    ):
        raise ValueError("Invalid history page")


def _history_filters(**filters: str | None) -> tuple[str, list[Any]]:
    clauses, values = [], []
    for name, value in filters.items():
        if value is None:
            continue
        if name in ("start", "end"):
            clauses.append("at>=?" if name == "start" else "at<?")
            values.append(utc_timestamp(value))
        else:
            clauses.append(name + "=?")
            values.append(_identifier(value))
    return (" WHERE " + " AND ".join(clauses) if clauses else "", values)


def _backup_snapshot(self: ControlStoreMixin) -> dict[str, Any]:
    with self._lock, self._control_transaction():  # type: ignore[attr-defined]
        clients, digests = self.load_clients()  # type: ignore[attr-defined]
        return {
            "format": "gateway7-backup",
            "version": 2,
            "backend": "postgres" if self._backend_postgres else "sqlite",
            "metadata": dict(self._control_query("SELECT name,value FROM {prefix}metadata")),
            "clients": [
                {
                    "id": identity,
                    "specification": client.model_dump(),
                    "digest": digests[identity].hex() if identity in digests else None,
                }
                for identity, client in clients.items()
            ],
            "tombstones": [
                row[0] for row in self._control_query("SELECT id FROM {prefix}tombstones")
            ],
            "usage": [
                {"client_id": row[0], "model": row[1], "day": row[2], "counts": json.loads(row[3])}
                for row in self._control_query(
                    "SELECT client_id,model,day,counts FROM {prefix}usage"
                )
            ],
            "archived_usage": [
                {"client_id": row[0], "model": row[1], "day": row[2], "value": json.loads(row[3])}
                for row in self._control_query(
                    "SELECT client_id,model,day,value FROM {prefix}archived_usage"
                )
            ],
            "legacy_usage": [
                {"client_id": row[0], "model": row[1], "day": row[2], "counts": json.loads(row[3])}
                for row in self._control_query(
                    "SELECT client_id,model,day,counts FROM {prefix}legacy_usage"
                )
            ],
            "control": self.read_control(),
            "audit": [
                json.loads(row[0])
                for row in self._control_query(
                    "SELECT value FROM {prefix}control_audit ORDER BY at,id"
                )
            ],
            "events": [
                json.loads(row[0])
                for row in self._control_query(
                    "SELECT value FROM {prefix}usage_events ORDER BY started_at,id"
                )
            ],
            "key_activity": self.key_last_used(),
        }


def _restore_backup(self: ControlStoreMixin, snapshot: dict[str, Any]) -> None:
    from gateway7.admin_store import (
        AdminStore,
        _empty_counts,
        _validate_usage_row,
        _valid_client_ids,
    )
    from gateway7.config import ClientConfig

    try:
        if (
            type(snapshot) is not dict
            or set(snapshot)
            != {
                "format",
                "version",
                "backend",
                "metadata",
                "clients",
                "tombstones",
                "usage",
                "legacy_usage",
                "archived_usage",
                "control",
                "audit",
                "events",
                "key_activity",
            }
            or snapshot["format"] != "gateway7-backup"
            or type(snapshot["version"]) is not int
            or snapshot["version"] != 2
            or snapshot["backend"] != ("postgres" if self._backend_postgres else "sqlite")
        ):
            raise ValueError
        metadata = snapshot["metadata"]
        if (
            not {"schema_version", "initialized", "started_at", "control_revision"} <= set(metadata)
            or set(metadata)
            - {
                "schema_version",
                "initialized",
                "started_at",
                "control_revision",
                "detail_retained_from",
            }
            or metadata["schema_version"] != "2"
            or metadata["initialized"] != "1"
        ):
            raise ValueError
        utc_timestamp(metadata["started_at"])
        if "detail_retained_from" in metadata:
            utc_timestamp(metadata["detail_retained_from"])
        clients, digests = {}, {}
        for row in snapshot["clients"]:
            if row["id"] in clients:
                raise ValueError
            clients[row["id"]] = ClientConfig.model_validate(row["specification"])
            if row["digest"] is not None:
                digests[row["id"]] = bytes.fromhex(row["digest"])
        AdminStore._validate_clients(clients, digests)
        tombstones = snapshot["tombstones"]
        if len(set(tombstones)) != len(tombstones) or set(tombstones) & clients.keys():
            raise ValueError
        for identity in tombstones:
            _valid_client_ids([identity])
        identities = clients.keys() | set(tombstones)
        seen: set[tuple[str, str, str]] = set()
        for table in ("usage", "legacy_usage"):
            seen = set()
            for row in snapshot[table]:
                key = (row["client_id"], row["model"], row["day"])
                if key in seen or key[0] not in identities:
                    raise ValueError
                seen.add(key)
                _validate_usage_row(*key, json.dumps(row["counts"]))
        for row in snapshot["archived_usage"]:
            value = row["value"]
            _validate_usage_row(
                row["client_id"],
                row["model"],
                row["day"],
                json.dumps({key: value[key] for key in _empty_counts()}),
            )
            if row["client_id"] not in identities or any(
                type(value.get(key)) is not int or value[key] < 0
                for key in ("cost_micro_usd", "unknown_cost_attempts")
            ):
                raise ValueError
        control = snapshot["control"]
        if (
            type(control["revision"]) is not int
            or control["revision"] < 0
            or str(control["revision"]) != metadata["control_revision"]
            or type(control["data"]) is not dict
        ):
            raise ValueError
        _bounded_json(control["data"], 2 * 1024 * 1024)
        _validate_control_data(control["data"])
        from gateway7.accounting import validate_event

        seen_events: set[str] = set()
        for event in snapshot["events"]:
            validate_event(event)
            if event["id"] in seen_events:
                raise ValueError("Duplicate backup event")
            seen_events.add(event["id"])
            _identifier(event["id"])
            _valid_client_ids([event["client_id"]])
            if event["client_id"] not in identities or event.get("kind") not in (
                "http",
                "provider",
            ):
                raise ValueError
            utc_timestamp(event["started_at"])
            _bounded_json(event, 32768)
        for entry in snapshot["audit"]:
            _identifier(entry["id"])
            if _audit_entry(entry)["diff"] != entry.get("diff", []):
                raise ValueError("Unsafe audit diff in backup")
            if (
                type(entry["revision"]) is not int
                or not 1 <= entry["revision"] <= control["revision"]
            ):
                raise ValueError
        for identity, at in snapshot["key_activity"].items():
            _identifier(identity)
            utc_timestamp(at)
    except Exception:
        raise ValueError("Invalid or incompatible management backup") from None
    with self._lock:  # type: ignore[attr-defined]
        try:
            with self._control_transaction():
                if self.read_control() != {"revision": 0, "data": {}} or any(
                    self._control_query("SELECT 1 FROM {prefix}" + table + " LIMIT 1").fetchone()
                    for table in (
                        "clients",
                        "tombstones",
                        "usage",
                        "legacy_usage",
                        "archived_usage",
                        "control_audit",
                        "usage_events",
                        "key_activity",
                    )
                ):
                    raise ValueError("Restore requires an empty management database")
                self._write_clients(clients, digests)  # type: ignore[attr-defined]
                self._control_query("DELETE FROM {prefix}operator_sessions")
                for identity in tombstones:
                    self._control_query(
                        "INSERT INTO {prefix}tombstones(id) VALUES (?)", (identity,)
                    )
                for row in snapshot["usage"]:
                    self._control_query(
                        "INSERT INTO {prefix}usage(client_id,model,day,counts) VALUES (?,?,?,?)",
                        (row["client_id"], row["model"], row["day"], json.dumps(row["counts"])),
                    )
                for row in snapshot["legacy_usage"]:
                    self._control_query(
                        "INSERT INTO {prefix}legacy_usage(client_id,model,day,counts) VALUES (?,?,?,?)",
                        (row["client_id"], row["model"], row["day"], json.dumps(row["counts"])),
                    )
                for row in snapshot["archived_usage"]:
                    self._control_query(
                        "INSERT INTO {prefix}archived_usage(client_id,model,day,value) VALUES (?,?,?,?)",
                        (row["client_id"], row["model"], row["day"], json.dumps(row["value"])),
                    )
                self._control_query(
                    "INSERT INTO {prefix}control_documents(name,revision,value) VALUES ('control',?,?)",
                    (control["revision"], _bounded_json(control["data"], 2 * 1024 * 1024)),
                )
                for entry in snapshot["audit"]:
                    self._control_query(
                        "INSERT INTO {prefix}control_audit(id,at,actor,action,target,revision,value) VALUES (?,?,?,?,?,?,?)",
                        (
                            entry["id"],
                            entry["timestamp"],
                            entry["actor"],
                            entry["action"],
                            entry["target"],
                            entry["revision"],
                            json.dumps(entry),
                        ),
                    )
                for event in snapshot["events"]:
                    self._put_usage_event(event)
                for identity, at in snapshot["key_activity"].items():
                    self._control_query(
                        "INSERT INTO {prefix}key_activity(id,last_used_at) VALUES (?,?)",
                        (identity, at),
                    )
                self._control_query("DELETE FROM {prefix}metadata")
                for key, value in metadata.items():
                    self._control_query(
                        "INSERT INTO {prefix}metadata(name,value) VALUES (?,?)", (key, value)
                    )
            self.started_at = metadata["started_at"]  # type: ignore[attr-defined]
        except ValueError:
            raise
        except Exception:
            raise StartupError("Management restore could not be completed") from None

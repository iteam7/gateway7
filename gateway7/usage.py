"""Bounded process-lifetime client accounting and a separate read capability."""

import hashlib
import hmac
import os
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from threading import Lock, RLock
from typing import Any

from gateway7.admin_store import AdminStore, _add_counts, _empty_counts, _valid_client_ids
from gateway7.auth import _valid_token
from gateway7.config import GatewayConfig, validate_model_id
from gateway7.errors import GatewayError, StartupError, normalized_usage

ProviderObserver = Callable[[str, dict[str, int] | None], None]
_OUTCOMES = ("complete", "provider_error", "cancelled")


class OperatorAccess:
    """Only a distinct operator bearer credential can read client accounting."""

    def __init__(
        self, config: GatewayConfig, *, token_digests: dict[str, bytes] | None = None
    ) -> None:
        self.enabled = config.auth.operator_token_env is not None
        self._digest: bytes | None = None
        if not self.enabled:
            return
        assert config.auth.operator_token_env is not None
        token = os.environ.get(config.auth.operator_token_env, "")
        if not _valid_token(token):
            raise StartupError("Operator token environment variable is missing or invalid")
        digest = hashlib.sha256(token.encode("ascii")).digest()
        credentials = [os.environ.get(config.provider.key_env, "")]
        if token_digests is None:
            credentials.extend(
                os.environ.get(client.token_env, "")
                for client in config.auth.clients.values()
                if client.enabled
            )
        reserved_digests = [hashlib.sha256(value.encode()).digest() for value in credentials]
        if token_digests is not None:
            reserved_digests.extend(token_digests.values())
        conflict = False
        for other in reserved_digests:
            conflict = hmac.compare_digest(digest, other) or conflict
        if conflict:
            raise StartupError("Operator token must differ from provider and client credentials")
        self._digest = digest

    def authenticate(self, headers: list[tuple[bytes, bytes]]) -> None:
        if not self.enabled:
            raise GatewayError("not_found")
        values = [value for name, value in headers if name.lower() == b"authorization"]
        if len(values) != 1:
            raise GatewayError("unauthorized")
        try:
            scheme, token = values[0].decode("ascii").split(" ", 1)
        except (UnicodeError, ValueError):
            raise GatewayError("unauthorized") from None
        if scheme.lower() != "bearer" or not _valid_token(token):
            raise GatewayError("unauthorized")
        digest = hashlib.sha256(token.encode("ascii")).digest()
        if self._digest is None or not hmac.compare_digest(digest, self._digest):
            raise GatewayError("unauthorized")


class UsageLedger:
    """Count numeric provider observations for configured identities only.

    This stores neither requests nor individual events. Each application startup
    creates a new ledger; its known totals are not a complete billing ledger.
    """

    def __init__(self, client_ids: Iterable[str]) -> None:
        ids = tuple(client_ids)
        if (
            len(ids) > 128
            or any(
                type(client_id) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", client_id) is None
                for client_id in ids
            )
            or len(ids) != len(set(ids))
        ):
            raise ValueError("Invalid configured usage identities")
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._lock = Lock()
        self._clients: dict[str, dict[str, Any]] = {
            client_id: {
                "provider_attempts": 0,
                "outcomes": dict.fromkeys(_OUTCOMES, 0),
                "known_input_tokens": 0,
                "known_output_tokens": 0,
                "input_usage_unknown_attempts": 0,
                "output_usage_unknown_attempts": 0,
            }
            for client_id in ids
        }

    def observer(self, client_id: str) -> ProviderObserver:
        if client_id not in self._clients:
            raise ValueError("Unknown configured usage identity")

        def observe(outcome: str, usage: dict[str, int] | None) -> None:
            counts = normalized_usage(usage) or {}
            safe_outcome = outcome if outcome in _OUTCOMES else "provider_error"
            with self._lock:
                row = self._clients[client_id]
                row["provider_attempts"] += 1
                row["outcomes"][safe_outcome] += 1
                for direction in ("input", "output"):
                    count = counts.get(direction + "_tokens")
                    if count is None:
                        row[direction + "_usage_unknown_attempts"] += 1
                    else:
                        row["known_" + direction + "_tokens"] += count

        return observe

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            clients = {
                client_id: {**row, "outcomes": dict(row["outcomes"])}
                for client_id, row in self._clients.items()
            }
        return {
            "scope": "process_lifetime",
            "started_at": self._started_at,
            "reset_on_restart": True,
            "clients": clients,
        }


class PersistentUsageLedger:
    """Daily client/model aggregates retained across management-enabled restarts."""

    def __init__(self, store: AdminStore, client_ids: Iterable[str]) -> None:
        self.store = store
        self._lock = RLock()
        self._clients = store.usage_identities()
        self.ensure_clients(client_ids)

    def ensure_clients(self, client_ids: Iterable[str]) -> None:
        ids = _valid_client_ids(client_ids)
        with self._lock:
            self._clients.update(ids)

    def observer(self, client_id: str, model: str | None = None):
        with self._lock:
            if client_id not in self._clients:
                raise ValueError("Unknown managed usage identity")
        selected_model = "unknown" if model is None else validate_model_id(model)

        def observe(outcome: str, usage: dict[str, int] | None) -> None:
            self.store.record_usage(client_id, selected_model, outcome, usage)

        return observe

    def snapshot(
        self,
        *,
        client_id: str | None = None,
        model: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        if (
            client_id is not None
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", client_id) is None
        ):
            raise ValueError("Invalid usage client filter")
        if model is not None:
            validate_model_id(model)
        for value in (start, end):
            if value is not None:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
                    raise ValueError("Usage dates must be UTC YYYY-MM-DD days")
                date.fromisoformat(value)
        if start is not None and end is not None and start > end:
            raise ValueError("Usage start day must not follow end day")
        rows = self.store.usage_rows(client_id=client_id, model=model, start=start, end=end)
        with self._lock:
            clients = {
                identity: _empty_counts()
                for identity in sorted(self._clients)
                if client_id is None or identity == client_id
            }
        for row in rows:
            _add_counts(clients.setdefault(row["client_id"], _empty_counts()), row)
        return {
            "scope": "persistent",
            "started_at": self.store.started_at,
            "reset_on_restart": False,
            "clients": clients,
            "rows": rows,
            "filters": {"client_id": client_id, "model": model, "start": start, "end": end},
        }

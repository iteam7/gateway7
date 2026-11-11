"""Bounded process-lifetime client accounting and a separate read capability."""

import hashlib
import hmac
import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from gateway7.auth import _valid_token
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError, normalized_usage

ProviderObserver = Callable[[str, dict[str, int] | None], None]
_OUTCOMES = ("complete", "provider_error", "cancelled")


class OperatorAccess:
    """Only a distinct operator bearer credential can read client accounting."""

    def __init__(self, config: GatewayConfig) -> None:
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
        credentials.extend(
            os.environ.get(client.token_env, "")
            for client in config.auth.clients.values()
            if client.enabled
        )
        conflict = False
        for credential in credentials:
            other = hashlib.sha256(credential.encode()).digest()
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

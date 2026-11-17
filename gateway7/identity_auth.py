"""Named operator credentials and expiring bearer identities, without database I/O."""

import hashlib
import hmac
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from gateway7.auth import _valid_token, credential_expiry
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.usage import OperatorAccess as BootstrapAccess


@dataclass(frozen=True)
class OperatorPrincipal:
    id: str
    role: Literal["admin", "viewer"]
    expires_at: datetime | None = None
    is_bootstrap: bool = False
    credential_digest: bytes | None = field(default=None, repr=False)

    def require_admin(self) -> None:
        if self.role != "admin" or (
            self.expires_at is not None and datetime.now(timezone.utc) >= self.expires_at
        ):
            raise GatewayError("operator_forbidden")


class NamedOperatorAccess:
    """The environment administrator remains an explicit recovery credential."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        identity: dict[str, Any],
        token_digests: dict[str, bytes] | None = None,
        clock: Callable[[], datetime] | None = None,
        provider_digest: bytes | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.enabled = config.auth.operator_token_env is not None
        self._operators: list[tuple[bytes, OperatorPrincipal]] = []
        try:
            reserved = {**(token_digests or {})}
            for key_id, record in identity.get("keys", {}).items():
                reserved["key:" + key_id] = bytes.fromhex(record["digest"])
            for operator_id, record in identity.get("operators", {}).items():
                reserved["operator:" + operator_id] = bytes.fromhex(record["digest"])
            self._bootstrap = BootstrapAccess(config, token_digests=reserved)
            provider = (
                provider_digest
                or hashlib.sha256(os.environ.get(config.provider.key_env, "").encode()).digest()
            )
            bootstrap = hashlib.sha256(
                os.environ.get(config.auth.operator_token_env or "", "").encode()
            ).digest()
            if hmac.compare_digest(provider, bootstrap):
                raise ValueError("Provider and operator credentials must be distinct")
            key_digests = [
                bytes.fromhex(record["digest"]) for record in identity.get("keys", {}).values()
            ]
            for operator_id, record in identity.get("operators", {}).items():
                if operator_id == "bootstrap" or record["role"] not in ("admin", "viewer"):
                    raise ValueError("Invalid operator profile")
                digest = bytes.fromhex(record["digest"])
                if (
                    len(digest) != 32
                    or hmac.compare_digest(digest, provider)
                    or any(hmac.compare_digest(digest, value) for value in key_digests)
                ):
                    raise ValueError("Operator credentials must be distinct")
                if any(hmac.compare_digest(digest, previous) for previous, _ in self._operators):
                    raise ValueError("Operator credentials must be distinct")
                expiry = credential_expiry(record["expires_at"])
                if expiry is None:
                    raise ValueError("Named operator credentials require an expiry")
                if not record["revoked"]:
                    self._operators.append(
                        (
                            digest,
                            OperatorPrincipal(
                                operator_id,
                                record["role"],
                                expiry,
                                credential_digest=digest,
                            ),
                        )
                    )
        except (ValueError, KeyError, TypeError):
            raise StartupError("Stored operator credentials are invalid") from None

    def authenticate(self, headers: list[tuple[bytes, bytes]]) -> OperatorPrincipal:
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
        matched = None
        for expected, principal in self._operators:
            if hmac.compare_digest(expected, digest) and (
                principal.expires_at is None or self._clock() < principal.expires_at
            ):
                matched = principal
        try:
            self._bootstrap.authenticate(headers)
            matched = OperatorPrincipal("bootstrap", "admin", is_bootstrap=True)
        except GatewayError:
            pass
        if matched is None:
            raise GatewayError("unauthorized")
        return matched

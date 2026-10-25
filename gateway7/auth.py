"""Startup-resolved gateway credentials and immutable per-request permissions."""

import hashlib
import hmac
import os
from dataclasses import dataclass

from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError


@dataclass(frozen=True)
class Principal:
    models: tuple[str, ...]

    def select_model(self, requested: str | None, default: str) -> str:
        selected = default if requested is None else requested
        if selected not in self.models:
            raise GatewayError("model_forbidden")
        return selected


def _valid_token(token: str) -> bool:
    return 16 <= len(token) <= 512 and token.isascii() and all(33 <= ord(c) <= 126 for c in token)


class AccessControl:
    """Keep token digests, never caller tokens, in the running gateway state."""

    def __init__(self, config: GatewayConfig) -> None:
        self.enabled = config.auth.enabled
        self.anonymous = Principal((config.provider.model,))
        provider_digest = hashlib.sha256(
            os.environ.get(config.provider.key_env, "").encode()
        ).digest()
        clients: list[tuple[bytes, Principal]] = []
        for specification in config.auth.clients.values():
            token = os.environ.get(specification.token_env, "")
            if not _valid_token(token):
                raise StartupError(
                    f"Gateway token in {specification.token_env} is missing or invalid"
                )
            digest = hashlib.sha256(token.encode("ascii")).digest()
            if hmac.compare_digest(digest, provider_digest):
                raise StartupError("Gateway client tokens must differ from the provider credential")
            if any(hmac.compare_digest(digest, existing) for existing, _ in clients):
                raise StartupError("Gateway clients must use distinct bearer tokens")
            clients.append((digest, Principal(tuple(specification.models))))
        self._clients = tuple(clients)

    def authenticate(self, headers: list[tuple[bytes, bytes]]) -> Principal:
        if not self.enabled:
            return self.anonymous
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
        # Compare every configured digest, including after a match.
        for expected, principal in self._clients:
            if hmac.compare_digest(expected, digest):
                matched = principal
        if matched is None:
            raise GatewayError("unauthorized")
        return matched

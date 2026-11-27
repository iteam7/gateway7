"""Opaque, durable operator sessions and bounded password verification."""

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import re
import secrets
import time
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.datastructures import URL

from gateway7.auth import credential_expiry
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_auth import OperatorPrincipal
from gateway7.loader import complete_cleanup

COOKIE_NAME = "gateway7_operator"
PASSWORD_HASH_PATTERN = r"^scrypt\$131072\$8\$1\$[0-9a-f]{32}\$[0-9a-f]{64}$"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_T = TypeVar("_T")


def password_text(value: str) -> str:
    if not 12 <= len(value) <= 128 or len(value.encode("utf-8")) > 512:
        raise ValueError("Password must contain 12 to 128 characters")
    return value


class PasswordRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    password: str = Field(repr=False, min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        return password_text(value)


class SessionLogin(PasswordRequest):
    username: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
    remember: bool = False


def _password_hash(password: str, salt: bytes) -> str:
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=131072, r=8, p=1, dklen=32, maxmem=256 * 1024**2
    )
    return "scrypt$131072$8$1$" + salt.hex() + "$" + derived.hex()


def _password_matches(password: str, encoded: str) -> bool:
    # Persisted data cannot select a different work factor or unbounded salt.
    if re.fullmatch(PASSWORD_HASH_PATTERN, encoded) is None:
        return False
    salt = bytes.fromhex(encoded.split("$")[4])
    return hmac.compare_digest(_password_hash(password, salt), encoded)


class PasswordWorker:
    """One memory-bounded KDF worker with a bounded queue and owned cleanup."""

    def __init__(self, capacity: int = 8) -> None:
        self.capacity = capacity
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gateway7-password")
        self._pending: set[asyncio.Future[Any]] = set()
        self._closed = False

    async def _call(self, operation: Callable[..., _T], *args: Any) -> _T:
        if self._closed or len(self._pending) >= self.capacity:
            raise GatewayError("overloaded")
        submitted = self._pool.submit(operation, *args)
        future = asyncio.wrap_future(submitted)
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)
        cancellation = None
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError as error:
                if submitted.cancel():
                    raise
                cancellation = cancellation or error
            except Exception:
                break
        try:
            return future.result()
        finally:
            if cancellation is not None:
                raise cancellation

    async def hash(self, password: str) -> str:
        password_text(password)
        return await self._call(_password_hash, password, secrets.token_bytes(16))

    async def verify(self, password: str, encoded: str) -> bool:
        return await self._call(_password_matches, password, encoded)

    async def close(self) -> None:
        self._closed = True
        while self._pending:
            await asyncio.shield(asyncio.gather(*self._pending, return_exceptions=True))
        await asyncio.to_thread(self._pool.shutdown, wait=True)


class LoginThrottle:
    """Fixed bounds on both attempts and attacker-selected map cardinality."""

    def __init__(self) -> None:
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def check(self, username: str, peer: str) -> None:
        now = time.monotonic()
        keys = [("global", 60), ("peer:" + peer[:128], 20), ("user:" + username, 5)]
        for key, limit in keys:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= limit:
                raise GatewayError("rate_limited", retry_after=60)
            self._buckets[key] = (start, count + 1)
            self._buckets.move_to_end(key)
        while len(self._buckets) > 2048:
            self._buckets.popitem(last=False)


def _authorization(headers: list[tuple[bytes, bytes]]) -> bool:
    return any(name.lower() == b"authorization" for name, _ in headers)


def _cookie_token(headers: list[tuple[bytes, bytes]]) -> str:
    values = []
    for name, raw in headers:
        if name.lower() != b"cookie":
            continue
        try:
            for piece in raw.decode("ascii").split(";"):
                key, separator, value = piece.strip().partition("=")
                if separator and key == COOKIE_NAME:
                    values.append(value)
        except UnicodeError:
            raise GatewayError("unauthorized") from None
    if len(values) != 1 or _TOKEN.fullmatch(values[0]) is None:
        raise GatewayError("unauthorized")
    return values[0]


def _csrf(token: str) -> str:
    return hmac.new(token.encode("ascii"), b"gateway7-operator-csrf-v1", hashlib.sha256).hexdigest()


def _expiry(value: Any) -> datetime:
    expires = credential_expiry(value)
    if expires is None:
        raise GatewayError("unauthorized")
    return expires


class OperatorSessions:
    def __init__(self, state: Any) -> None:
        self.state = state
        self.passwords = PasswordWorker()
        self.throttle = LoginThrottle()
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._generation = 0
        self._dummy_hash = "scrypt$131072$8$1$" + "00" * 16 + "$" + "00" * 32

    def check_transport(self, scope: dict[str, Any]) -> None:
        secure = self.state.config.auth.session_cookie_secure
        if secure:
            if scope.get("scheme") != "https":
                raise GatewayError("invalid_request")
            return
        peer = (scope.get("client") or ("",))[0]
        try:
            peer_loopback = ipaddress.ip_address(peer).is_loopback
            host_text = URL(scope=scope).hostname or ""
            host_loopback = host_text == "localhost" or ipaddress.ip_address(host_text).is_loopback
        except (ValueError, UnicodeError):
            host_loopback = False
            peer_loopback = False
        if not peer_loopback or not host_loopback:
            raise GatewayError("invalid_request")

    def _record(self, username: str) -> dict[str, Any] | None:
        return self.state.control["data"].get("identity", {}).get("operators", {}).get(username)

    def _principal(self, session: dict[str, Any]) -> OperatorPrincipal:
        now = datetime.now(timezone.utc)
        record = self._record(session["operator_id"])
        if (
            record is None
            or record["revoked"]
            or not record.get("password_hash")
            or record.get("password_version", 0) != session["password_version"]
            or now >= _expiry(session["expires_at"])
            or now >= _expiry(record["expires_at"])
        ):
            raise GatewayError("unauthorized")
        return OperatorPrincipal(
            record["id"],
            record["role"],
            credential_expiry(session["expires_at"]),
            credential_digest=bytes.fromhex(record["digest"]),
            session_version=session["password_version"],
        )

    def _remember(self, digest: str, session: dict[str, Any]) -> None:
        self._cache[digest] = session
        self._cache.move_to_end(digest)
        while len(self._cache) > 1024:
            self._cache.popitem(last=False)

    async def authenticate(
        self, headers: list[tuple[bytes, bytes]], *, scope: dict[str, Any] | None = None
    ) -> OperatorPrincipal:
        if _authorization(headers):
            return self.state.operator_access.authenticate(headers)
        token = _cookie_token(headers)
        if scope is not None:
            self.check_transport(scope)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        for _ in range(3):
            generation = self._generation
            try:
                session = await self.state.db.call(
                    self.state.admin_store.get_operator_session, digest
                )
            except StartupError:
                raise GatewayError("unavailable") from None
            if generation == self._generation:
                break
        else:
            # A concurrent unrelated login/logout does not revoke this actor.
            # Recheck authoritative storage; sustained churn remains bounded.
            raise GatewayError("unavailable")
        if session is None:
            self._cache.pop(digest, None)
            raise GatewayError("unauthorized")
        principal = self._principal(session)
        self._remember(digest, session)
        return principal

    def authenticate_cached(self, headers: list[tuple[bytes, bytes]]) -> OperatorPrincipal:
        if _authorization(headers):
            return self.state.operator_access.authenticate(headers)
        token = _cookie_token(headers)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        session = self._cache.get(digest)
        if session is None:
            raise GatewayError("unauthorized")
        return self._principal(session)

    def check_csrf(self, headers: list[tuple[bytes, bytes]]) -> None:
        if _authorization(headers):
            return
        values = [value for name, value in headers if name.lower() == b"x-gateway7-csrf"]
        expected = _csrf(_cookie_token(headers)).encode("ascii")
        if len(values) != 1 or not hmac.compare_digest(values[0], expected):
            raise GatewayError("operator_forbidden")

    def view(self, headers: list[tuple[bytes, bytes]], actor: OperatorPrincipal) -> dict[str, Any]:
        cookie = not _authorization(headers)
        return {
            "actor": {"id": actor.id, "role": actor.role, "is_bootstrap": actor.is_bootstrap},
            "csrf_token": _csrf(_cookie_token(headers)) if cookie else None,
            "expires_at": actor.expires_at.isoformat() if actor.expires_at is not None else None,
            "authentication": "session" if cookie else "bearer",
        }

    async def login(self, payload: SessionLogin, peer: str) -> tuple[str, dict[str, Any]]:
        self.throttle.check(payload.username, peer)
        record = self._record(payload.username)
        encoded = (record.get("password_hash") or self._dummy_hash) if record else self._dummy_hash
        matched = await self.passwords.verify(payload.password, encoded)
        async with self.state.management_mutation_lock:
            current = self._record(payload.username)
            now = datetime.now(timezone.utc)
            if (
                not matched
                or current is None
                or current["revoked"]
                or current.get("password_hash") != encoded
                or now >= _expiry(current["expires_at"])
            ):
                raise GatewayError("unauthorized")
            ttl = (
                self.state.config.auth.session_remember_ttl_seconds
                if payload.remember
                else self.state.config.auth.session_ttl_seconds
            )
            expires = min(now + timedelta(seconds=ttl), _expiry(current["expires_at"]))
            token = secrets.token_urlsafe(32)
            session = {
                "operator_id": current["id"],
                "password_version": current["password_version"],
                "created_at": now.isoformat(),
                "expires_at": expires.isoformat(),
            }
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()

            async def publish() -> None:
                removed = await self.state.db.call(
                    self.state.admin_store.create_operator_session, digest, session
                )
                # Publish actual eviction while still owning the mutation lock.
                # Cancellation cannot leave deleted sessions in the auth cache.
                if removed:
                    self._generation += 1
                    for removed_digest in removed:
                        self._cache.pop(removed_digest, None)
                self._remember(digest, session)

            await complete_cleanup(publish())
            return token, session

    async def logout(self, headers: list[tuple[bytes, bytes]]) -> None:
        if _authorization(headers):
            return
        digest = hashlib.sha256(_cookie_token(headers).encode("ascii")).hexdigest()

        async def revoke() -> None:
            async with self.state.management_mutation_lock:
                await self.state.db.call(self.state.admin_store.delete_operator_session, digest)
                self._generation += 1
                self._cache.pop(digest, None)

        await complete_cleanup(revoke())

"""Named credentials, attributable changes and revision-checked account management."""

import asyncio
import copy
import hashlib
import hmac
import os
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gateway7.admin_runtime import ClientPolicy, CreateClient
from gateway7.auth import AccessControl, _effective_models, credential_expiry
from gateway7.client_policies import build_client_pipelines
from gateway7.config import ClientConfig, GatewayConfig, validate_provider_model
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_auth import NamedOperatorAccess, OperatorPrincipal
from gateway7.identity_records import validate_identity
from gateway7.operator_console import operator_state


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now().isoformat()


def _key_active(record: dict[str, Any]) -> bool:
    expiry = credential_expiry(record.get("expires_at"))
    return not record["revoked"] and (expiry is None or _now() < expiry)


class KeyRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    label: str = Field(default="application", min_length=1, max_length=64)
    expires_at: str | None = None

    @field_validator("label")
    @classmethod
    def label_is_text(cls, value: str) -> str:
        if not value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("Invalid credential label")
        return value.strip()


class OperatorRequest(KeyRequest):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
    role: Literal["admin", "viewer"] = "viewer"


class OperatorUpdate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    role: Literal["admin", "viewer"]
    label: str = Field(default="operator", min_length=1, max_length=64)
    expires_at: str | None = None

    @field_validator("label")
    @classmethod
    def label_is_text(cls, value: str) -> str:
        return KeyRequest.label_is_text(value)


def _new_expiry(value: str | None) -> str:
    try:
        now = _now()
        expiry = credential_expiry(value) if value is not None else now + timedelta(days=90)
        if expiry is None or not now < expiry <= now + timedelta(days=365):
            raise ValueError
        return expiry.isoformat()
    except (ValueError, TypeError):
        raise GatewayError("invalid_request") from None


def _safe_key(record: dict[str, Any], activity: dict[str, str] | None = None) -> dict[str, Any]:
    result = {
        name: record.get(name)
        for name in ("id", "client_id", "label", "created_at", "expires_at", "revoked")
    }
    result["last_used_at"] = (activity or {}).get(record["id"], record.get("last_used_at"))
    expiry = credential_expiry(record.get("expires_at"))
    result["expired"] = expiry is not None and _now() >= expiry
    return result


def _safe_operator(record: dict[str, Any]) -> dict[str, Any]:
    result = {
        name: record.get(name)
        for name in ("id", "label", "role", "created_at", "expires_at", "revoked")
    }
    expiry = credential_expiry(record.get("expires_at"))
    result["expired"] = expiry is not None and _now() >= expiry
    result["is_bootstrap"] = False
    return result


def prepare_identity(
    state: Any,
    config: GatewayConfig,
    control_snapshot: dict[str, Any],
    provider_digest: bytes | None = None,
) -> tuple[AccessControl, NamedOperatorAccess]:
    """Validate and build authentication before any irreversible store commit."""
    identity = validate_identity(control_snapshot.get("data", {}).get("identity", {}))
    digest = provider_digest or getattr(state, "provider_credential_digest", None)
    access = AccessControl(config, identity=identity, provider_digest=digest)
    operators = NamedOperatorAccess(
        config,
        identity=identity,
        token_digests=getattr(state, "token_digests", {}),
        provider_digest=digest,
    )
    return access, operators


def refresh_identity(state: Any, config: GatewayConfig, control_snapshot: dict[str, Any]) -> None:
    """Publish on the event loop only; never perform database work here."""
    state.access, state.operator_access = prepare_identity(state, config, control_snapshot)
    state.control = copy.deepcopy(control_snapshot)


class IdentityAdmin:
    """Persist control, account rows and audit together before publishing changes."""

    def __init__(self, state: Any) -> None:
        self.state = state
        if not hasattr(state, "management_mutation_lock"):
            state.management_mutation_lock = asyncio.Lock()

    async def _read(self) -> dict[str, Any]:
        try:
            return await self.state.db.call(self.state.admin_store.read_control)
        except StartupError:
            raise GatewayError("unavailable") from None

    async def initialize(self) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._read()
            if "identity" not in document["data"]:
                created = _timestamp()
                identity: dict[str, Any] = {
                    "users": {
                        name: {
                            "owner": "",
                            "tags": [],
                            "created_at": created,
                            "default_model": None,
                        }
                        for name in self.state.config.auth.clients
                    },
                    "keys": {},
                    "operators": {},
                }
                for client_id, digest in self.state.token_digests.items():
                    key_id = "key_" + uuid4().hex
                    identity["keys"][key_id] = {
                        "id": key_id,
                        "client_id": client_id,
                        "label": "legacy",
                        "digest": digest.hex(),
                        "created_at": created,
                        "expires_at": None,
                        "revoked": False,
                    }
                data = copy.deepcopy(document["data"])
                data["identity"] = identity
                audit = {
                    "actor": "bootstrap",
                    "action": "identity.initialize",
                    "target": "identity",
                    "diff": {"users": len(identity["users"]), "keys": len(identity["keys"])},
                    "timestamp": created,
                    "request_id": "internal",
                }
                revision = await self.state.db.call(
                    self.state.admin_store.write_control, document["revision"], data, audit
                )
                document = {"revision": revision, "data": data}
            refresh_identity(self.state, self.state.config, document)
            self.state.refresh_management_access = lambda config, snapshot: refresh_identity(
                self.state, config, snapshot
            )
            self.state.prepare_management_access = lambda config, snapshot, digest=None: (
                prepare_identity(self.state, config, snapshot, digest)
            )
            return document

    def _check_actor(self, document: dict[str, Any], actor: OperatorPrincipal) -> None:
        actor.require_admin()
        if actor.is_bootstrap:
            if actor.id != "bootstrap":
                raise GatewayError("operator_forbidden")
            return
        record = document["data"].get("identity", {}).get("operators", {}).get(actor.id)
        expiry = credential_expiry(record.get("expires_at")) if record is not None else None
        if (
            record is None
            or record.get("revoked")
            or record.get("role") != "admin"
            or expiry is None
            or _now() >= expiry
            or actor.credential_digest is None
            or not hmac.compare_digest(bytes.fromhex(record["digest"]), actor.credential_digest)
        ):
            raise GatewayError("operator_forbidden")

    async def _document(self, expected_revision: int, actor: OperatorPrincipal) -> dict[str, Any]:
        document = await self._read()
        self._check_actor(document, actor)
        if type(expected_revision) is not int or expected_revision != document["revision"]:
            raise GatewayError("conflict")
        return document

    def _candidate(
        self, clients: dict[str, ClientConfig], data: dict[str, Any]
    ) -> tuple[GatewayConfig, Any, Any, dict[str, Any]]:
        try:
            specification = self.state.config.model_dump()
            specification["auth"]["clients"] = {
                name: value.model_dump() for name, value in clients.items()
            }
            config = GatewayConfig.model_validate(specification)
            aliases = data.get("provider", {}).get("aliases", {})
            for name, client in clients.items():
                additional = client.additional_middleware
                if len(additional) != len(set(additional)) or any(
                    entry not in self.state.pipeline.plugins.instances
                    or not config.plugins[entry].enabled
                    or entry in config.middleware
                    for entry in additional
                ):
                    raise ValueError("Invalid client middleware")
                if client.models is not None and any(model in aliases for model in client.models):
                    raise ValueError("Model permissions must use canonical IDs")
                default = (
                    data.get("identity", {}).get("users", {}).get(name, {}).get("default_model")
                )
                if default is not None:
                    validate_provider_model(config.provider.kind, default)
                    if default in aliases:
                        raise ValueError("Client default model must be canonical")
            access, operators = prepare_identity(self.state, config, {"data": data})
            pipelines = build_client_pipelines(
                config, self.state.pipeline.plugins, self.state.pipeline
            )
            return config, access, operators, pipelines
        except (ValueError, TypeError, KeyError, ValidationError):
            raise GatewayError("invalid_request") from None
        except StartupError:
            raise GatewayError("invalid_request") from None

    async def _commit(
        self,
        document: dict[str, Any],
        data: dict[str, Any],
        actor: OperatorPrincipal,
        action: str,
        target: str,
        diff: dict[str, Any],
        *,
        clients: dict[str, ClientConfig] | None = None,
        digests: dict[str, bytes] | None = None,
        request_id: str = "",
    ) -> int:
        selected_clients = dict(self.state.config.auth.clients) if clients is None else clients
        candidate, access, operators, pipelines = self._candidate(selected_clients, data)
        audit = {
            "actor": actor.id,
            "action": action,
            "target": target,
            "diff": diff,
            "timestamp": _timestamp(),
            "request_id": request_id or "internal",
        }
        if hasattr(self.state, "validate_operator"):
            self.state.validate_operator(actor)
        self._check_actor(document, actor)
        validate_identity(data["identity"])
        try:
            revision = await self.state.db.call(
                self.state.admin_store.write_control,
                document["revision"],
                data,
                audit,
                clients=clients,
                digests=digests,
            )
        except ValueError as error:
            if type(error).__name__ == "ControlConflict":
                raise GatewayError("conflict") from None
            raise GatewayError("invalid_request") from None
        except StartupError:
            raise GatewayError("unavailable") from None
        # Everything below is synchronous event-loop publication. The app owns
        # cancellation shielding so a committed write always reaches this block.
        self.state.usage_ledger.ensure_clients(selected_clients)
        self.state.admission.update(candidate)
        self.state.config = candidate
        self.state.access = access
        self.state.operator_access = operators
        self.state.client_pipelines = pipelines
        if digests is not None:
            self.state.token_digests = digests
        self.state.control = {"revision": revision, "data": copy.deepcopy(data)}
        return revision

    def _secret(self, data: dict[str, Any]) -> tuple[str, str]:
        identity = data.get("identity", {})
        reserved = [record["digest"] for record in identity.get("keys", {}).values()]
        reserved.extend(record["digest"] for record in identity.get("operators", {}).values())
        reserved.extend(
            hashlib.sha256(os.environ.get(name, "").encode()).hexdigest()
            for name in (
                self.state.config.provider.key_env,
                self.state.config.auth.operator_token_env or "",
            )
        )
        live_digest = getattr(self.state, "provider_credential_digest", None)
        if live_digest is not None:
            reserved.append(live_digest.hex())
        for _ in range(10):
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            if digest not in reserved:
                return token, digest
        raise GatewayError("internal_error")

    def _new_key(
        self, data: dict[str, Any], client_id: str, payload: KeyRequest
    ) -> tuple[dict[str, Any], str]:
        keys = data["identity"]["keys"]
        if (
            sum(
                record["client_id"] == client_id and _key_active(record) for record in keys.values()
            )
            >= 16
            or len(keys) >= 4096
        ):
            raise GatewayError("invalid_request")
        token, digest = self._secret(data)
        key_id = "key_" + uuid4().hex
        record = {
            "id": key_id,
            "client_id": client_id,
            "label": payload.label,
            "digest": digest,
            "created_at": _timestamp(),
            "expires_at": _new_expiry(payload.expires_at),
            "revoked": False,
        }
        keys[key_id] = record
        return record, token

    def _validate_default(self, payload: ClientPolicy) -> None:
        if payload.default_model is None:
            return
        try:
            validate_provider_model(self.state.config.provider.kind, payload.default_model)
            permitted = _effective_models(self.state.config.provider.allowed_models, payload.models)
            aliases = self.state.control["data"].get("provider", {}).get("aliases", {})
            if payload.default_model in aliases or (
                permitted is not None and payload.default_model not in permitted
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise GatewayError("invalid_request") from None

    async def snapshot(self, actor: OperatorPrincipal | None = None) -> dict[str, Any]:
        document = self.state.control
        config = self.state.config
        pipeline = self.state.pipeline
        client_pipelines = self.state.client_pipelines
        ready = self.state.ready
        identity = document["data"].get("identity", {})
        activity = await self.state.db.call(self.state.admin_store.key_last_used)
        base = operator_state(config, pipeline, client_pipelines, ready=ready)
        for row in base["clients"]:
            metadata = identity.get("users", {}).get(row["id"], {})
            row.update(
                {
                    "owner": metadata.get("owner", ""),
                    "tags": metadata.get("tags", []),
                    "created_at": metadata.get("created_at"),
                    "default_model": metadata.get("default_model"),
                    "revision": document["revision"],
                }
            )
            row["keys"] = [
                _safe_key(record, activity)
                for record in identity.get("keys", {}).values()
                if record["client_id"] == row["id"]
            ]
            row["credential_active"] = any(
                not key["revoked"] and not key["expired"] for key in row["keys"]
            )
            allowed = _effective_models(
                config.provider.allowed_models,
                config.auth.clients[row["id"]].models,
            )
            row["effective_models"] = None if allowed is None else list(allowed)
            default = row["default_model"] or config.provider.model
            row["default_denied"] = allowed is not None and default not in allowed
        result = {
            "revision": document["revision"],
            "clients": base["clients"],
            "operators": self._operator_rows(identity),
        }
        if actor is not None:
            result["actor"] = {
                "id": actor.id,
                "role": actor.role,
                "is_bootstrap": actor.is_bootstrap,
            }
        return result

    def _operator_rows(self, identity: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": "bootstrap",
                "label": "Environment recovery administrator",
                "role": "admin",
                "is_bootstrap": True,
                "revoked": False,
                "expired": False,
                "created_at": None,
                "expires_at": None,
            },
            *[_safe_operator(row) for row in identity.get("operators", {}).values()],
        ]

    async def list_users(
        self,
        *,
        q: str = "",
        owner: str = "",
        tag: str = "",
        status: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        if (
            not 0 <= offset <= 100000
            or not 1 <= limit <= 100
            or status not in ("", "enabled", "suspended", "revoked")
            or any(len(value) > 128 for value in (q, owner, tag))
        ):
            raise GatewayError("invalid_request")
        snapshot = await self.snapshot()
        rows = [
            row
            for row in snapshot["clients"]
            if (
                (
                    not q
                    or q.casefold() in " ".join([row["id"], row["owner"], *row["tags"]]).casefold()
                )
                and (not owner or owner.casefold() in row["owner"].casefold())
                and (not tag or tag in row["tags"])
                and (
                    not status
                    or status == "enabled"
                    and row["enabled"]
                    or status == "suspended"
                    and not row["enabled"]
                    or status == "revoked"
                    and not row["credential_active"]
                )
            )
        ]
        rows.sort(key=lambda row: row["id"].casefold())
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "revision": snapshot["revision"],
        }

    def _user(self, client_id: str) -> ClientConfig:
        client = self.state.config.auth.clients.get(client_id)
        if client is None:
            raise GatewayError("not_found")
        return client

    async def _result(
        self, client_id: str, token: str | None = None, key: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        snapshot = await self.snapshot()
        result = {
            "client": next(row for row in snapshot["clients"] if row["id"] == client_id),
            "revision": snapshot["revision"],
        }
        if token is not None:
            result["token"] = token
        if key is not None:
            result["key"] = _safe_key(key)
        return result

    async def create(
        self,
        payload: CreateClient,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._validate_default(payload)
            clients = dict(self.state.config.auth.clients)
            if payload.id in clients or len(clients) >= 128:
                raise GatewayError("conflict")
            clients[payload.id] = payload.client_config()
            data = copy.deepcopy(document["data"])
            data["identity"]["users"][payload.id] = {
                "owner": payload.owner,
                "tags": payload.tags,
                "created_at": _timestamp(),
                "default_model": payload.default_model,
            }
            key, token = self._new_key(data, payload.id, KeyRequest(label="initial"))
            digests = {**self.state.token_digests, payload.id: bytes.fromhex(key["digest"])}
            await self._commit(
                document,
                data,
                actor,
                "user.create",
                payload.id,
                {
                    "enabled": payload.enabled,
                    "models": payload.models,
                    "owner": payload.owner,
                    "tags": payload.tags,
                },
                clients=clients,
                digests=digests,
                request_id=request_id,
            )
            return await self._result(payload.id, token, key)

    async def update(
        self,
        client_id: str,
        payload: ClientPolicy,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._validate_default(payload)
            previous = self._user(client_id)
            client = payload.client_config().model_copy(update={"token_env": previous.token_env})
            data = copy.deepcopy(document["data"])
            metadata = data["identity"]["users"].setdefault(client_id, {"created_at": _timestamp()})
            before = {
                "enabled": previous.enabled,
                "models": previous.models,
                "limits": previous.limits.model_dump(),
                "additional_middleware": previous.additional_middleware,
                "owner": metadata.get("owner", ""),
                "tags": metadata.get("tags", []),
                "default_model": metadata.get("default_model"),
            }
            metadata.update(
                {
                    "owner": payload.owner,
                    "tags": payload.tags,
                    "default_model": payload.default_model,
                }
            )
            after = {
                "enabled": payload.enabled,
                "models": payload.models,
                "limits": payload.limits.model_dump(),
                "additional_middleware": payload.additional_middleware,
                "owner": payload.owner,
                "tags": payload.tags,
                "default_model": payload.default_model,
            }
            await self._commit(
                document,
                data,
                actor,
                "user.update",
                client_id,
                {"before": before, "after": after},
                clients={**self.state.config.auth.clients, client_id: client},
                digests=dict(self.state.token_digests),
                request_id=request_id,
            )
            return await self._result(client_id)

    async def delete(
        self,
        client_id: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, int]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            for row in data["identity"]["keys"].values():
                if row["client_id"] == client_id:
                    row["revoked"] = True
            clients, digests = dict(self.state.config.auth.clients), dict(self.state.token_digests)
            del clients[client_id]
            digests.pop(client_id, None)
            revision = await self._commit(
                document,
                data,
                actor,
                "user.delete",
                client_id,
                {"deleted": True},
                clients=clients,
                digests=digests,
                request_id=request_id,
            )
            return {"revision": revision}

    async def list_keys(self, client_id: str) -> dict[str, Any]:
        self._user(client_id)
        result = await self._result(client_id)
        return {"items": result["client"]["keys"], "revision": result["revision"]}

    async def create_key(
        self,
        client_id: str,
        payload: KeyRequest,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            key, token = self._new_key(data, client_id, payload)
            await self._commit(
                document,
                data,
                actor,
                "key.create",
                key["id"],
                {"client_id": client_id, "label": payload.label, "expires_at": key["expires_at"]},
                request_id=request_id,
            )
            return await self._result(client_id, token, key)

    async def rotate_key(
        self,
        client_id: str,
        key_id: str,
        payload: KeyRequest,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            previous = data["identity"]["keys"].get(key_id)
            if previous is None or previous["client_id"] != client_id:
                raise GatewayError("not_found")
            previous["revoked"] = True
            key, token = self._new_key(data, client_id, payload)
            await self._commit(
                document,
                data,
                actor,
                "key.rotate",
                key_id,
                {
                    "client_id": client_id,
                    "replacement_id": key["id"],
                    "expires_at": key["expires_at"],
                },
                request_id=request_id,
            )
            return await self._result(client_id, token, key)

    async def revoke_key(
        self,
        client_id: str,
        key_id: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            key = data["identity"]["keys"].get(key_id)
            if key is None or key["client_id"] != client_id:
                raise GatewayError("not_found")
            key["revoked"] = True
            await self._commit(
                document,
                data,
                actor,
                "key.revoke",
                key_id,
                {"client_id": client_id, "revoked": True},
                request_id=request_id,
            )
            return await self._result(client_id)

    async def rotate(
        self,
        client_id: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        """Compatibility action replaces every existing key; named issue does not."""
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            for key in data["identity"]["keys"].values():
                if key["client_id"] == client_id:
                    key["revoked"] = True
            key, token = self._new_key(data, client_id, KeyRequest(label="replacement"))
            digests = {**self.state.token_digests, client_id: bytes.fromhex(key["digest"])}
            await self._commit(
                document,
                data,
                actor,
                "key.replace_all",
                client_id,
                {"replacement_id": key["id"]},
                digests=digests,
                clients=dict(self.state.config.auth.clients),
                request_id=request_id,
            )
            return await self._result(client_id, token, key)

    async def revoke(
        self,
        client_id: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            self._user(client_id)
            data = copy.deepcopy(document["data"])
            for key in data["identity"]["keys"].values():
                if key["client_id"] == client_id:
                    key["revoked"] = True
            digests = dict(self.state.token_digests)
            digests.pop(client_id, None)
            await self._commit(
                document,
                data,
                actor,
                "key.revoke_all",
                client_id,
                {"revoked": True},
                clients=dict(self.state.config.auth.clients),
                digests=digests,
                request_id=request_id,
            )
            return await self._result(client_id)

    async def list_operators(self) -> dict[str, Any]:
        document = self.state.control
        return {
            "items": self._operator_rows(document["data"].get("identity", {})),
            "revision": document["revision"],
        }

    async def create_operator(
        self,
        payload: OperatorRequest,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            data = copy.deepcopy(document["data"])
            operators = data["identity"]["operators"]
            if payload.id == "bootstrap" or payload.id in operators or len(operators) >= 64:
                raise GatewayError("conflict")
            token, digest = self._secret(data)
            record = {
                "id": payload.id,
                "label": payload.label,
                "role": payload.role,
                "digest": digest,
                "created_at": _timestamp(),
                "expires_at": _new_expiry(payload.expires_at),
                "revoked": False,
            }
            operators[payload.id] = record
            revision = await self._commit(
                document,
                data,
                actor,
                "operator.create",
                payload.id,
                {"role": payload.role, "expires_at": record["expires_at"]},
                request_id=request_id,
            )
            return {"operator": _safe_operator(record), "token": token, "revision": revision}

    async def update_operator(
        self,
        operator_id: str,
        payload: OperatorUpdate,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            data = copy.deepcopy(document["data"])
            row = data["identity"]["operators"].get(operator_id)
            if operator_id == "bootstrap":
                raise GatewayError("operator_forbidden")
            if row is None:
                raise GatewayError("not_found")
            before = _safe_operator(row)
            row.update({"role": payload.role, "label": payload.label})
            if payload.expires_at is not None:
                row["expires_at"] = _new_expiry(payload.expires_at)
            revision = await self._commit(
                document,
                data,
                actor,
                "operator.update",
                operator_id,
                {"before": before, "after": _safe_operator(row)},
                request_id=request_id,
            )
            return {"operator": _safe_operator(row), "revision": revision}

    async def revoke_operator(
        self,
        operator_id: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            data = copy.deepcopy(document["data"])
            row = data["identity"]["operators"].get(operator_id)
            if operator_id == "bootstrap":
                raise GatewayError("operator_forbidden")
            if row is None:
                raise GatewayError("not_found")
            row["revoked"] = True
            revision = await self._commit(
                document,
                data,
                actor,
                "operator.revoke",
                operator_id,
                {"revoked": True},
                request_id=request_id,
            )
            return {"operator": _safe_operator(row), "revision": revision}

    async def rotate_operator(
        self,
        operator_id: str,
        payload: KeyRequest,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self._document(expected_revision, actor)
            data = copy.deepcopy(document["data"])
            row = data["identity"]["operators"].get(operator_id)
            if operator_id == "bootstrap":
                raise GatewayError("operator_forbidden")
            if row is None:
                raise GatewayError("not_found")
            token, digest = self._secret(data)
            row.update(
                {
                    "digest": digest,
                    "created_at": _timestamp(),
                    "expires_at": _new_expiry(payload.expires_at),
                    "label": payload.label,
                    "revoked": False,
                }
            )
            revision = await self._commit(
                document,
                data,
                actor,
                "operator.rotate",
                operator_id,
                {"role": row["role"], "expires_at": row["expires_at"], "revoked": False},
                request_id=request_id,
            )
            return {"operator": _safe_operator(row), "token": token, "revision": revision}

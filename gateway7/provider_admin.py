"""Live single-provider administration with encrypted, write-only credentials."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import os
import time
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gateway7.auth import AccessControl
from gateway7.client_policies import build_client_pipelines
from gateway7.config import (
    GatewayConfig,
    ClientConfig,
    ModelId,
    ProviderConfig,
    provider_key,
    validate_provider_model,
)
from gateway7.control_store import ControlConflict
from gateway7.errors import GatewayError, ProviderError, StartupError
from gateway7.models import ChatRequest, Message
from gateway7.identity_auth import NamedOperatorAccess
from gateway7.identity_records import validate_identity
from gateway7.pipeline import Pipeline
from gateway7.providers import build_provider, validate_provider_config
from gateway7.transport_loader import create_transport, validate_transport_config


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    kind: Literal["fake", "openai", "claude", "gemini"]
    base_url: str | None = Field(default=None, max_length=2048)
    model: ModelId
    allowed_models: list[ModelId] | None = Field(default=None, max_length=64)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300, allow_inf_nan=False)
    max_concurrent_requests: int = Field(default=64, ge=1, le=10000)
    aliases: dict[ModelId, ModelId] = Field(default_factory=dict, max_length=64)
    credential: str | None = Field(default=None, min_length=1, max_length=4096, repr=False)

    @model_validator(mode="after")
    def valid_registry(self) -> "ProviderUpdate":
        if self.model in self.aliases or any(
            target in self.aliases for target in self.aliases.values()
        ):
            raise ValueError("Aliases must point directly to canonical models")
        if self.allowed_models is not None and any(
            model in self.aliases for model in self.allowed_models
        ):
            raise ValueError("Provider permissions must use canonical model IDs")
        for target in self.aliases.values():
            validate_provider_model(self.kind, target)
        if self.credential is not None and (
            not self.credential.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in self.credential)
        ):
            raise ValueError("Invalid provider credential")
        return self


def _provider_doc(control: dict[str, Any]) -> dict[str, Any]:
    data = control.get("data", control)
    document = data.get("provider", {})
    if not isinstance(document, dict):
        raise StartupError("Invalid stored provider configuration")
    return document


def get_provider_aliases(control: dict[str, Any]) -> dict[str, str]:
    aliases = _provider_doc(control).get("aliases", {})
    if not isinstance(aliases, dict):
        raise StartupError("Invalid stored model aliases")
    if any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in aliases.items()
    ):
        raise StartupError("Invalid stored model aliases")
    return dict(aliases)


def resolve_model_alias(model: str, aliases: dict[str, str]) -> str:
    return aliases.get(model, model)


def _cipher() -> Fernet:
    try:
        value = os.environ.get("GATEWAY7_CONTROL_KEY", "")
        return Fernet(value.encode("ascii"))
    except (ValueError, UnicodeError):
        raise StartupError(
            "A valid GATEWAY7_CONTROL_KEY is required for provider credentials"
        ) from None


def _seed_key(config: GatewayConfig) -> str:
    return provider_key(config.provider)


def _configured(
    seed: GatewayConfig, document: dict[str, Any], *, clients: dict[str, ClientConfig] | None = None
) -> GatewayConfig:
    try:
        if not document:
            if clients is None:
                return seed
            data = seed.model_dump()
            data["auth"]["clients"] = {
                name: client.model_dump() for name, client in clients.items()
            }
            return GatewayConfig.model_validate(data)
        editable = {
            key: document[key]
            for key in (
                "kind",
                "base_url",
                "model",
                "allowed_models",
                "timeout_seconds",
                "max_concurrent_requests",
                "aliases",
            )
            if key in document
        }
        values = ProviderUpdate.model_validate(editable)
        data = seed.model_dump()
        if clients is not None:
            data["auth"]["clients"] = {
                name: client.model_dump() for name, client in clients.items()
            }
        provider: dict[str, Any] = {
            "kind": values.kind,
            "model": values.model,
            "timeout_seconds": values.timeout_seconds,
            "transport": seed.provider.transport,
        }
        if values.base_url is not None:
            provider["base_url"] = values.base_url
        if values.allowed_models is not None:
            provider["allowed_models"] = values.allowed_models
        # The original environment reference remains available for config-only
        # edits; a changed provider kind obtains its own conventional reference.
        if values.kind == seed.provider.kind:
            provider["key_env"] = seed.provider.key_env
        data["provider"] = ProviderConfig.model_validate(provider).model_dump()
        data["limits"]["max_concurrent_requests"] = values.max_concurrent_requests
        configured = GatewayConfig.model_validate(data)
        validate_provider_config(configured.provider)
        return configured
    except (ValidationError, ValueError, TypeError):
        raise StartupError("Invalid stored provider configuration") from None


def restore_provider_config(
    seed: GatewayConfig, control: dict[str, Any], *, clients: dict[str, ClientConfig] | None = None
) -> tuple[GatewayConfig, str]:
    """Restore durable settings without falling back around an unreadable secret."""
    document = _provider_doc(control)
    config = _configured(seed, document, clients=clients)
    ciphertext = document.get("credential_ciphertext")
    if ciphertext is None:
        return config, _seed_key(config)
    try:
        if not isinstance(ciphertext, str):
            raise ValueError
        key = _cipher().decrypt(ciphertext.encode("ascii")).decode("ascii")
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError
        validate_provider_credential(config, key, control)
        return config, key
    except (InvalidToken, ValueError, UnicodeError):
        raise StartupError("Cannot decrypt stored provider credential") from None


def validate_provider_credential(
    config: GatewayConfig,
    key: str,
    control: dict[str, Any],
    token_digests: dict[str, bytes] | None = None,
) -> None:
    digest = hashlib.sha256(key.encode("ascii")).digest()
    reserved: list[bytes] = list((token_digests or {}).values())
    bootstrap_env = config.auth.operator_token_env
    if bootstrap_env is not None:
        reserved.append(hashlib.sha256(os.environ.get(bootstrap_env, "").encode()).digest())
    identity = control.get("data", control).get("identity", {})
    for collection in ("keys", "operators"):
        for specification in identity.get(collection, {}).values():
            try:
                reserved.append(bytes.fromhex(specification.get("digest", "")))
            except (ValueError, TypeError):
                raise StartupError("Invalid stored credential registry") from None
    if any(hmac.compare_digest(digest, other) for other in reserved):
        raise StartupError("Provider credential must differ from client and operator credentials")


def _actor_id(actor: Any) -> str:
    if isinstance(actor, str):
        return actor
    if isinstance(actor, dict):
        return str(actor.get("id", "bootstrap"))
    return str(getattr(actor, "id", "bootstrap"))


class ProviderAdmin:
    """Construct candidates before atomically publishing a durable provider view."""

    def __init__(self, state: Any) -> None:
        self.state = state

    async def _read(self) -> dict[str, Any]:
        return await self.state.db.call(self.state.admin_store.read_control)

    def _safe_provider(self, document: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.state.config
        return {
            "kind": config.provider.kind,
            "base_url": config.provider.base_url,
            "model": config.provider.model,
            "allowed_models": config.provider.allowed_models,
            "timeout_seconds": config.provider.timeout_seconds,
            "max_concurrent_requests": config.limits.max_concurrent_requests,
            "aliases": dict(getattr(self.state, "provider_aliases", {})),
            "credential_configured": True,
            "credential_updated_at": (document or {}).get("credential_updated_at"),
            "credential_writes_available": bool(os.environ.get("GATEWAY7_CONTROL_KEY")),
        }

    async def snapshot(self) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            return await self._snapshot()

    async def _snapshot(self) -> dict[str, Any]:
        control = await self._read()
        return {
            "revision": control["revision"],
            "provider": self._safe_provider(_provider_doc(control)),
            "health": dict(
                getattr(
                    self.state, "provider_health", {"status": "not_checked", "checked_at": None}
                )
            ),
        }

    def _candidate_config(self, payload: ProviderUpdate) -> GatewayConfig:
        document = payload.model_dump(exclude={"credential"})
        try:
            return _configured(self.state.config, document)
        except StartupError:
            raise GatewayError("invalid_request") from None

    def _key(self, payload: ProviderUpdate, control: dict[str, Any]) -> str:
        if payload.credential is not None:
            return payload.credential
        if payload.kind != self.state.config.provider.kind:
            raise GatewayError("invalid_request")
        return restore_provider_config(self.state.config, control)[1]

    def _validate_separation(self, key: str, control: dict[str, Any]) -> None:
        try:
            validate_provider_credential(
                self.state.config, key, control, getattr(self.state, "token_digests", {})
            )
        except StartupError:
            raise GatewayError("invalid_request") from None

    async def _build(self, config: GatewayConfig, key: str) -> Any:
        transport = create_transport(validate_transport_config(config.provider.transport))
        factory = getattr(self.state, "provider_factory", build_provider)
        try:
            return factory(
                config.provider, key, **({"transport": transport} if transport is not None else {})
            )
        except BaseException as error:
            if transport is not None:
                await transport.aclose()
            if not isinstance(error, Exception):
                raise
            raise GatewayError("invalid_request") from None

    def _authorize(self, actor: Any) -> None:
        validate = getattr(self.state, "validate_operator", None)
        if validate is not None:
            validate(actor)
        elif hasattr(actor, "require_admin"):
            actor.require_admin()
        elif isinstance(actor, dict) and actor.get("role") != "admin":
            raise GatewayError("unauthorized")

    async def _probe(self, provider: Any, config: GatewayConfig) -> dict[str, Any]:
        started = time.monotonic()
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            async with asyncio.timeout(min(10.0, config.provider.timeout_seconds)):
                if config.provider.kind == "openai":
                    models = await provider.get_models()
                    count: int | None = len(models)
                else:
                    await provider.complete(
                        ChatRequest(
                            messages=[
                                Message(role="user", content="Gateway connection check: reply OK.")
                            ],
                            max_tokens=1,
                        )
                    )
                    count = None
            return {
                "status": "reachable",
                "checked_at": checked_at,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "catalog_count": count,
            }
        except (ProviderError, TimeoutError, ValueError):
            return {
                "status": "unavailable",
                "checked_at": checked_at,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "reason": "connection_check_failed",
            }

    async def test(
        self, payload: ProviderUpdate | None = None, actor: Any = None
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            self._authorize(actor)
            control = await self._read()
            if payload is None:
                # An explicit health check must contact the provider rather than
                # treating a warm discovery cache as evidence of reachability.
                config = self.state.config
                key = restore_provider_config(config, control)[1]
                provider = await self._build(config, key)
                try:
                    result = await self._probe(provider, config)
                    self.state.provider_health = result
                    return result
                finally:
                    await provider.aclose()
            config = self._candidate_config(payload)
            key = self._key(payload, control)
            self._validate_separation(key, control)
            provider = await self._build(config, key)
            try:
                return await self._probe(provider, config)
            finally:
                await provider.aclose()

    async def update(
        self,
        payload: ProviderUpdate,
        expected_revision: int,
        actor: Any,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            self._authorize(actor)
            control = await self._read()
            if control["revision"] != expected_revision:
                raise ControlConflict("Control state changed; refresh and retry")
            config = self._candidate_config(payload)
            key = self._key(payload, control)
            self._validate_separation(key, control)
            document = payload.model_dump(exclude={"credential"})
            old_document = _provider_doc(control)
            if payload.credential is not None:
                document["credential_ciphertext"] = (
                    _cipher().encrypt(key.encode("ascii")).decode("ascii")
                )
                document["credential_updated_at"] = datetime.now(timezone.utc).isoformat()
            else:
                for field in ("credential_ciphertext", "credential_updated_at"):
                    if field in old_document:
                        document[field] = old_document[field]
            provider = await self._build(config, key)
            published = False
            try:
                health = await self._probe(provider, config)
                if health["status"] != "reachable":
                    raise GatewayError("unavailable")
                pipeline = Pipeline(
                    self.state.pipeline.plugins,
                    provider,
                    config.limits,
                    metrics=self.state.metrics,
                    provider_name=config.provider.kind,
                )
                pipelines = build_client_pipelines(config, pipeline.plugins, pipeline)
                control["data"]["provider"] = document
                provider_digest = hashlib.sha256(key.encode("ascii")).digest()
                prepare = getattr(self.state, "prepare_management_access", None)
                if prepare is not None:
                    access, operator_access = prepare(config, control, provider_digest)
                else:
                    identity = validate_identity(control["data"].get("identity", {}))
                    access = (
                        AccessControl(config, identity=identity, provider_digest=provider_digest)
                        if identity
                        else AccessControl(config, token_digests=self.state.token_digests)
                    )
                    operator_access = NamedOperatorAccess(
                        config,
                        identity=identity,
                        token_digests=self.state.token_digests,
                        provider_digest=provider_digest,
                    )
                audit = {
                    "actor": _actor_id(actor),
                    "action": "provider.update",
                    "request_id": request_id,
                    "target": "provider",
                    "diff": {
                        "fields": [
                            "kind",
                            "base_url",
                            "model",
                            "allowed_models",
                            "aliases",
                            "timeout_seconds",
                            "max_concurrent_requests",
                        ],
                        "credential_changed": payload.credential is not None,
                    },
                }
                self._authorize(actor)
                revision = await self.state.db.call(
                    self.state.admin_store.write_control, expected_revision, control["data"], audit
                )
                old_provider = self.state.pipeline.provider
                self.state.config = config
                self.state.pipeline = pipeline
                self.state.client_pipelines = pipelines
                self.state.provider_aliases = dict(payload.aliases)
                self.state.provider_health = health
                self.state.control = {"revision": revision, "data": control["data"]}
                self.state.access = access
                self.state.operator_access = operator_access
                self.state.provider_credential_digest = hashlib.sha256(key.encode("ascii")).digest()
                self.state.admission.update(config)
                published = True
                self.state.retire_provider(old_provider)
                return {
                    "revision": revision,
                    "provider": self._safe_provider(document),
                    "health": health,
                }
            finally:
                if not published:
                    await provider.aclose()

    async def models(self, refresh: bool = False) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            return await self._models(refresh)

    async def _models(self, refresh: bool = False) -> dict[str, Any]:
        control = await self._read()
        config = self.state.config
        known = {
            config.provider.model,
            *(config.provider.allowed_models or []),
            *getattr(self.state, "provider_aliases", {}).values(),
        }
        source = "configuration"
        error = None
        fetched_at = None
        discovered: set[str] = set()
        if config.provider.kind == "openai":
            try:
                provider = self.state.pipeline.provider
                if refresh and hasattr(provider, "_catalog_until"):
                    provider._catalog_until = 0.0
                models = await provider.get_models()
                discovered = {model.id for model in models}
                known.update(discovered)
                source = "provider_catalog"
                fetched_at = datetime.now(timezone.utc).isoformat()
            except (ProviderError, TimeoutError):
                source, error = "configuration", "catalog_unavailable"
        aliases = getattr(self.state, "provider_aliases", {})
        return {
            "revision": control["revision"],
            "source": source,
            "refreshed_at": fetched_at,
            "error": error,
            "items": [
                {
                    "id": model,
                    "aliases": sorted(
                        alias for alias, target in aliases.items() if target == model
                    ),
                    "globally_allowed": config.provider.allowed_models is None
                    or model in config.provider.allowed_models,
                    "is_default": model == config.provider.model,
                    "availability": "catalogued" if model in discovered else "unverified",
                    "pricing_model": model,
                }
                for model in sorted(known)
            ],
            "health": dict(
                getattr(
                    self.state, "provider_health", {"status": "not_checked", "checked_at": None}
                )
            ),
        }

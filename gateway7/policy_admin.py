"""Revisioned data-only policies built from the gateway's known pure middleware."""

import asyncio
import copy
import unicodedata
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from gateway7.client_policies import build_client_pipelines
from gateway7.config import GatewayConfig, InstanceName
from gateway7.control_store import ControlConflict
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_admin import IdentityAdmin, prepare_identity
from gateway7.identity_auth import OperatorPrincipal
from gateway7.loader import LoadedPlugin, LoadedPlugins
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import PluginDescriptor
from gateway7.plugins import content_policy, email_mask, phone_mask

PolicyId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,55}$")]
Term = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Template = Literal["literal_guard", "literal_redact", "email_mask", "phone_mask"]
Phase = Literal["request", "response", "both"]
PREFIX = "policy_"
MODULE = "gateway7.policy_admin"


def _text(value: str) -> str:
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("Policy text must not contain control characters")
    return value


class PolicySpec(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: PolicyId
    label: str = Field(min_length=1, max_length=64)
    template: Template
    phase: Phase
    terms: list[Term] = Field(default_factory=list, max_length=32)
    replacement: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("label")
    @classmethod
    def label_text(cls, value: str) -> str:
        if not _text(value).strip():
            raise ValueError("Policy label must not be blank")
        return value.strip()

    @field_validator("terms")
    @classmethod
    def literal_terms(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not _text(term).strip() for term in values):
            raise ValueError("Literal terms must be distinct and nonblank")
        return values

    @field_validator("replacement")
    @classmethod
    def replacement_text(cls, value: str | None) -> str | None:
        return _text(value) if value is not None else None

    @model_validator(mode="after")
    def template_settings(self) -> "PolicySpec":
        if self.template in ("literal_guard", "literal_redact"):
            if not self.terms:
                raise ValueError("Literal policies require bounded terms")
        elif self.terms:
            raise ValueError("Mask policies do not accept literal terms")
        if self.template == "literal_guard" and self.replacement is not None:
            raise ValueError("Guard policies do not accept a replacement")
        return self


class PolicyDefinition(PolicySpec):
    action: Literal["deny", "redact"]

    @model_validator(mode="after")
    def fixed_action(self) -> "PolicyDefinition":
        if self.action != ("deny" if self.template == "literal_guard" else "redact"):
            raise ValueError("Policy action is fixed by its template")
        return self


class PolicyAssignments(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    global_: list[PolicyId] = Field(alias="global", max_length=64)
    clients: dict[InstanceName, list[PolicyId]] = Field(max_length=128)

    @model_validator(mode="after")
    def unique_bindings(self) -> "PolicyAssignments":
        if len(set(self.global_)) != len(self.global_):
            raise ValueError("Duplicate global policy")
        for bindings in self.clients.values():
            if len(bindings) > 64 or len(set(bindings)) != len(bindings):
                raise ValueError("Invalid client policy selections")
            if set(bindings) & set(self.global_):
                raise ValueError("A global policy cannot be appended to a client twice")
        return self


class PolicyPreview(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    spec: PolicySpec
    text: str = Field(max_length=8192)

    @field_validator("text")
    @classmethod
    def valid_unicode(cls, value: str) -> str:
        value.encode("utf-8", errors="strict")
        return value


class _Document(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    version: Literal[1]
    definitions: dict[PolicyId, PolicyDefinition] = Field(max_length=64)
    global_: list[PolicyId] = Field(alias="global", max_length=64)

    @field_validator("version", mode="before")
    @classmethod
    def exact_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Invalid policy version")
        return value

    @model_validator(mode="after")
    def references(self) -> "_Document":
        if any(name != spec.id for name, spec in self.definitions.items()):
            raise ValueError("Policy identity mismatch")
        if len(set(self.global_)) != len(self.global_) or any(
            name not in self.definitions for name in self.global_
        ):
            raise ValueError("Invalid global policy selections")
        return self


def _definition(spec: PolicySpec) -> dict[str, Any]:
    value = spec.model_dump()
    value["action"] = "deny" if spec.template == "literal_guard" else "redact"
    if value["replacement"] is None:
        value["replacement"] = {
            "literal_guard": None,
            "literal_redact": "[REDACTED]",
            "email_mask": "[EMAIL]",
            "phone_mask": "[PHONE]",
        }[spec.template]
    return value


def validate_policy_document(value: Any) -> dict[str, Any]:
    """Shared startup/write/backup validator; never includes input in diagnostics."""
    try:
        document = _Document.model_validate(value)
        return {
            "version": 1,
            "definitions": {name: _definition(spec) for name, spec in document.definitions.items()},
            "global": list(document.global_),
        }
    except (ValueError, TypeError):
        raise ValueError("Invalid managed policy configuration") from None


def _policies(control: dict[str, Any]) -> dict[str, Any]:
    return validate_policy_document(
        control.get("data", control).get(
            "policies", {"version": 1, "definitions": {}, "global": []}
        )
    )


def create(settings: PolicyDefinition) -> Any:
    """Only these fixed, immutable factories are reachable from operator data."""
    if settings.template in ("literal_guard", "literal_redact"):
        return content_policy.create(
            content_policy.Settings(
                terms=tuple(settings.terms),
                phase=settings.phase,
                action="block" if settings.action == "deny" else "redact",
                replacement=settings.replacement or "[REDACTED]",
            )
        )
    if settings.template == "email_mask":
        return email_mask.create(
            email_mask.Settings(phase=settings.phase, replacement=settings.replacement or "[EMAIL]")
        )
    return phone_mask.create(
        phone_mask.Settings(phase=settings.phase, replacement=settings.replacement or "[PHONE]")
    )


PLUGIN = PluginDescriptor(
    id="managed-policy",
    api_version=2,
    settings_model=PolicyDefinition,
    create=create,
    supports_tools=True,
)


def restore_policy_config(config: GatewayConfig, control: dict[str, Any]) -> GatewayConfig:
    """Append durable managed definitions to the original configured plugin chain."""
    try:
        policies = _policies(control)
        data = config.model_dump()
        for identity, specification in policies["definitions"].items():
            name = PREFIX + identity
            if name in config.plugins:
                raise ValueError("Managed policy collides with a configured plugin")
            data["plugins"][name] = {"module": MODULE, "settings": specification}
        data["middleware"] += [PREFIX + name for name in policies["global"]]
        if (active := control.get("data", control).get("plugin_active")) is not None:
            from gateway7.plugin_draft import ChainDraft, apply_active

            apply_active(data, config, ChainDraft.model_validate(active))
        restored = GatewayConfig.model_validate(data)
        for client in restored.auth.clients.values():
            selected = client.additional_middleware
            if len(selected) != len(set(selected)) or any(
                name not in restored.plugins
                or not restored.plugins[name].enabled
                or name in restored.middleware
                for name in selected
            ):
                raise ValueError("Invalid client policy selections")
        return restored
    except (ValueError, TypeError, KeyError):
        raise StartupError("Invalid stored managed policy configuration") from None


def _loaded(name: str, specification: dict[str, Any]) -> LoadedPlugin:
    instance = create(PolicyDefinition.model_validate(specification))
    return LoadedPlugin(
        name,
        PLUGIN,
        instance,
        instance.handle,
        None,
        None,
        instance.prepare_early_stream,
        instance.prepare_responses,
        instance.check_responses,
        instance.prepare_early_responses,
    )


def _pipeline(previous: Pipeline, plugins: LoadedPlugins, config: GatewayConfig) -> Pipeline:
    return Pipeline(
        plugins,
        previous.provider,
        config.limits,
        metrics=previous.metrics,
        provider_name=previous.provider_name,
        provider_observer=previous.provider_observer,
        provider_before=previous.provider_before,
    )


def _templates() -> list[dict[str, Any]]:
    return [
        {
            "id": template,
            "label": label,
            "phases": ["request", "response", "both"],
            "early_phases": ["request"],
            "action": "deny" if template == "literal_guard" else "redact",
        }
        for template, label in (
            ("literal_guard", "Block literal terms"),
            ("literal_redact", "Redact literal terms"),
            ("email_mask", "Mask email addresses"),
            ("phone_mask", "Mask supported Russian phone formats"),
        )
    ]


class PolicyAdmin:
    def __init__(self, state: Any) -> None:
        self.state = state
        self.identity = IdentityAdmin(state)
        if not hasattr(state, "management_mutation_lock"):
            state.management_mutation_lock = asyncio.Lock()

    def _view(self, document: dict[str, Any]) -> dict[str, Any]:
        policies = _policies(document)
        return {
            "revision": document["revision"],
            "templates": _templates(),
            "items": [
                {**spec, "instance_id": PREFIX + name}
                for name, spec in policies["definitions"].items()
            ],
            "global": policies["global"],
            "clients": {
                name: [
                    entry[len(PREFIX) :]
                    for entry in client.additional_middleware
                    if entry in {PREFIX + key for key in policies["definitions"]}
                ]
                for name, client in self.state.config.auth.clients.items()
            },
        }

    async def snapshot(self) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            return self._view(await self.identity._read())

    @staticmethod
    def preview(payload: PolicyPreview) -> dict[str, Any]:
        instance = create(PolicyDefinition.model_validate(_definition(payload.spec)))
        transform = (
            instance._apply
            if isinstance(instance, content_policy.ContentPolicyPlugin)
            else instance._transform
        )
        text, matches = transform(payload.text)
        denied = matches > 0 and payload.spec.template == "literal_guard"
        return {
            "text": None if denied else text,
            "matched": matches,
            "denied": denied,
            "provider_calls": 0,
            "scope": "plain_text_only",
        }

    async def _save(
        self,
        document: dict[str, Any],
        policies: dict[str, Any],
        actor: OperatorPrincipal,
        action: str,
        target: str,
        request_id: str,
        assignments: PolicyAssignments | None = None,
    ) -> dict[str, Any]:
        policies = validate_policy_document(policies)
        old = _policies(document)
        managed = {PREFIX + name for name in old["definitions"]}
        data = copy.deepcopy(document["data"])
        data["policies"] = policies
        base = self.state.config.model_dump()
        base["plugins"] = {
            name: spec for name, spec in base["plugins"].items() if name not in managed
        }
        base["middleware"] = [name for name in base["middleware"] if name not in managed]
        studio_instances: set[str] = set()
        if "plugin_active" in data:
            from gateway7.plugin_draft import (
                PREFIX as DRAFT_PREFIX,
                ChainDraft,
                load_enabled_builtin,
            )

            original = self.state.plugin_base_config
            old_active = self.state.control["data"].get("plugin_active")
            if old_active is not None:
                studio_instances = {
                    DRAFT_PREFIX + row.spec.id
                    for row in ChainDraft.model_validate(old_active).items
                    if row.enabled
                }
            for name in studio_instances:
                base["plugins"].pop(name, None)
            base["middleware"] = list(original.middleware)
            for name in original.middleware:
                base["plugins"][name]["enabled"] = original.plugins[name].enabled
        for name, client in base["auth"]["clients"].items():
            if assignments is not None:
                client["additional_middleware"] = [
                    entry for entry in client["additional_middleware"] if entry not in managed
                ]
                client["additional_middleware"] += [
                    PREFIX + entry for entry in assignments.clients.get(name, [])
                ]
        try:
            candidate = restore_policy_config(GatewayConfig.model_validate(base), {"data": data})
        except (StartupError, ValueError):
            raise GatewayError("invalid_request") from None
        instances = {
            name: plugin
            for name, plugin in self.state.pipeline.plugins.instances.items()
            if name not in managed and name not in studio_instances
        }
        instances.update(
            {
                PREFIX + name: _loaded(PREFIX + name, spec)
                for name, spec in policies["definitions"].items()
            }
        )
        if "plugin_active" in data:
            active = ChainDraft.model_validate(data["plugin_active"])
            for configured in active.configured:
                if configured.enabled and configured.id not in instances:
                    instances[configured.id] = load_enabled_builtin(candidate, configured.id)
            for row in active.items:
                if row.enabled:
                    name = DRAFT_PREFIX + row.spec.id
                    instances[name] = _loaded(name, _definition(row.spec))
        plugins = LoadedPlugins(
            instances,
            tuple(
                instances[name] for name in candidate.middleware if candidate.plugins[name].enabled
            ),
        )
        pipeline = _pipeline(self.state.pipeline, plugins, candidate)
        clients = build_client_pipelines(candidate, plugins, pipeline, self.state.usage_ledger)
        access, operators = prepare_identity(self.state, candidate, {"data": data})
        self.identity._check_actor(document, actor)
        if hasattr(self.state, "validate_operator"):
            self.state.validate_operator(actor)
        try:
            revision = await self.state.db.call(
                self.state.admin_store.write_control,
                document["revision"],
                data,
                {
                    "actor": actor.id,
                    "action": action,
                    "target": target,
                    "request_id": request_id or "internal",
                    "diff": {
                        "fields": ["definitions", "global", "client_assignments"]
                        if assignments is not None
                        else ["plugin_active"]
                        if action == "plugin.activate"
                        else ["definitions"]
                    },
                },
                clients=candidate.auth.clients,
                digests=self.state.token_digests,
            )
        except ControlConflict:
            raise GatewayError("conflict") from None
        except StartupError:
            raise GatewayError("unavailable") from None
        self.state.config = candidate
        self.state.pipeline = pipeline
        self.state.client_pipelines = clients
        self.state.access, self.state.operator_access = access, operators
        self.state.control = {"revision": revision, "data": data}
        self.state.admission.update(candidate)
        return self._view(self.state.control)

    async def create(
        self,
        spec: PolicySpec,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            policies = _policies(document)
            if spec.id in policies["definitions"] or PREFIX + spec.id in self.state.config.plugins:
                raise GatewayError("conflict")
            policies["definitions"][spec.id] = _definition(spec)
            return await self._save(document, policies, actor, "policy.create", spec.id, request_id)

    async def update(
        self,
        identity: str,
        spec: PolicySpec,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            policies = _policies(document)
            if identity != spec.id or identity not in policies["definitions"]:
                raise GatewayError("invalid_request")
            policies["definitions"][identity] = _definition(spec)
            return await self._save(
                document, policies, actor, "policy.update", identity, request_id
            )

    async def delete(
        self,
        identity: str,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            policies = _policies(document)
            if identity not in policies["definitions"]:
                raise GatewayError("invalid_request")
            if identity in policies["global"] or any(
                PREFIX + identity in client.additional_middleware
                for client in self.state.config.auth.clients.values()
            ):
                raise GatewayError("conflict")
            del policies["definitions"][identity]
            return await self._save(
                document, policies, actor, "policy.delete", identity, request_id
            )

    async def assignments(
        self,
        spec: PolicyAssignments,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            policies = _policies(document)
            if any(
                name not in policies["definitions"]
                for selected in [spec.global_, *spec.clients.values()]
                for name in selected
            ) or any(name not in self.state.config.auth.clients for name in spec.clients):
                raise GatewayError("invalid_request")
            policies["global"] = list(spec.global_)
            return await self._save(
                document, policies, actor, "policy.assign", "policies", request_id, spec
            )

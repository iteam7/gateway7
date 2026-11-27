"""Durable, data-only operator draft. Preview never calls arbitrary plugins or providers."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gateway7.config import GatewayConfig, InstanceName
from gateway7.control_store import ControlConflict
from gateway7.errors import GatewayError, StartupError
from gateway7.identity_auth import OperatorPrincipal
from gateway7.loader import LoadedPlugin, LoadedPlugins, load_plugins
from gateway7.policy_admin import (
    MODULE,
    PREFIX as POLICY_PREFIX,
    PolicyAdmin,
    PolicyDefinition,
    PolicySpec,
    _definition,
    _policies,
    _templates,
    create,
)
from gateway7.plugins import content_policy, email_mask, phone_mask

PREFIX = "draft_"
PURE_MODULES = {module.__name__: module for module in (content_policy, email_mask, phone_mask)}


class DraftItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    spec: PolicySpec
    enabled: bool


class ConfiguredItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: InstanceName
    enabled: bool
    required: bool


class ChainDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    items: list[DraftItem] = Field(max_length=64)
    configured: list[ConfiguredItem] = Field(default_factory=list, max_length=256)

    managed_chain: list[ConfiguredItem] | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def unique(self) -> ChainDraft:
        if len({item.spec.id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate plugin")
        if self.managed_chain is not None and (
            any(row.required for row in self.managed_chain)
            or len({row.id for row in self.managed_chain}) != len(self.managed_chain)
        ):
            raise ValueError("Invalid managed order")
        return self


class ChainPreview(ChainDraft):
    text: str = Field(max_length=8192)
    phase: Literal["request", "response"]

    @field_validator("text")
    @classmethod
    def valid_unicode(cls, value: str) -> str:
        value.encode("utf-8", errors="strict")
        return value


def defaults(base: GatewayConfig) -> list[ConfiguredItem]:
    return [
        ConfiguredItem(
            id=name, enabled=base.plugins[name].enabled, required=base.plugins[name].required
        )
        for name in base.middleware
    ]


def validate_chain(draft: ChainDraft, base: GatewayConfig) -> None:
    expected = defaults(base)
    if sorted(row.id for row in draft.configured) != sorted(row.id for row in expected):
        raise ValueError("Configured plugin inventory changed")
    # Required entries partition the order. No optional plugin can cross a protection.
    segment: dict[str, int] = {}
    for rows in (expected, draft.configured):
        boundary = 0
        for row in rows:
            configured = base.plugins[row.id]
            if row.required != configured.required or row.required and not row.enabled:
                raise ValueError("Required plugin is fixed")
            if row.enabled and not configured.enabled and configured.module not in PURE_MODULES:
                raise ValueError("Plugin is disabled in deployment configuration")
            if row.id in segment and segment[row.id] != boundary:
                raise ValueError("Cannot cross a required plugin")
            segment[row.id] = boundary
            boundary += int(row.required)
    if any(PREFIX + item.spec.id in base.plugins for item in draft.items):
        raise ValueError("Plugin identity collides with configured plugin")


def managed_rows(draft: ChainDraft, current: list[str]) -> list[ConfiguredItem]:
    """Keep legacy assignments authoritative for membership, even after a draft was saved."""
    existing = [row for row in draft.managed_chain or [] if row.id in current]
    ordered = {row.id for row in existing}
    return existing + [
        ConfiguredItem(id=name, enabled=True, required=False)
        for name in current
        if name not in ordered
    ]


def apply_active(data: dict[str, Any], base: GatewayConfig, active: ChainDraft) -> None:
    validate_chain(active, base)
    managed = data["middleware"][len(base.middleware) :]
    selected = managed_rows(active, [name.removeprefix(POLICY_PREFIX) for name in managed])
    data["middleware"] = [row.id for row in active.configured]
    for row in selected:
        name = POLICY_PREFIX + row.id
        data["middleware"].append(name)
        data["plugins"][name]["enabled"] = row.enabled
    for row in active.configured:
        data["plugins"][row.id]["enabled"] = row.enabled
    for item in active.items:
        if item.enabled:
            name = PREFIX + item.spec.id
            data["plugins"][name] = {"module": MODULE, "settings": _definition(item.spec)}
            data["middleware"].append(name)


def load_enabled_builtin(config: GatewayConfig, name: str) -> LoadedPlugin:
    """A deployment-disabled pure built-in has no resource lifecycle to start."""
    if config.plugins[name].module not in PURE_MODULES:
        raise GatewayError("invalid_request")
    single = config.model_copy(
        update={
            "plugins": {name: config.plugins[name]},
            "middleware": [name],
            "auth": config.auth.model_copy(update={"clients": {}}),
        }
    )
    return load_plugins(single).instances[name]


def load_active_plugins(config: GatewayConfig, base: GatewayConfig) -> LoadedPlugins:
    """Keep deployment-enabled instances lifecycle-owned and available for later activation."""
    specifications = dict(config.plugins)
    for name in base.middleware:
        if base.plugins[name].enabled:
            specifications[name] = specifications[name].model_copy(update={"enabled": True})
    loaded = load_plugins(config.model_copy(update={"plugins": specifications}))
    return LoadedPlugins(
        loaded.instances,
        tuple(loaded.instances[name] for name in config.middleware if config.plugins[name].enabled),
    )


class DraftAdmin(PolicyAdmin):
    def _base(self) -> GatewayConfig:
        return self.state.plugin_base_config

    def view(self, document: dict[str, Any]) -> dict[str, Any]:
        base = self._base()
        data = document["data"]
        fallback = ChainDraft(items=[], configured=defaults(base)).model_dump()
        draft = data.get("plugin_draft", data.get("plugin_active", fallback))
        return {
            **draft,
            "managed_chain": [
                row.model_dump()
                for row in managed_rows(
                    ChainDraft.model_validate(draft), _policies(document)["global"]
                )
            ],
            "revision": document["revision"],
            "templates": _templates(),
            "has_saved": "plugin_draft" in data,
            "is_active": "plugin_active" in data and draft == data["plugin_active"],
            "mandatory": [row.id for row in defaults(base) if row.required],
            "managed": _policies(document)["global"],
            "deployment_disabled": [
                row.id
                for row in defaults(base)
                if not row.enabled and base.plugins[row.id].module not in PURE_MODULES
            ],
        }

    async def draft(self) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            return self.view(await self.identity._read())

    def check(self, draft: ChainDraft, *, reconcile_managed: bool = False) -> None:
        try:
            validate_chain(draft, self._base())
            if not reconcile_managed and draft.managed_chain is not None:
                current = _policies(self.state.control)["global"]
                if {row.id for row in draft.managed_chain} != set(current):
                    raise ValueError("Managed policy inventory changed")
        except ValueError:
            raise GatewayError("invalid_request") from None

    async def save_draft(
        self,
        draft: ChainDraft,
        *,
        actor: OperatorPrincipal,
        expected_revision: int,
        request_id: str = "internal",
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            self.check(draft)
            data = {**document["data"], "plugin_draft": draft.model_dump()}
            if hasattr(self.state, "validate_operator"):
                self.state.validate_operator(actor)
            audit = {
                "actor": actor.id,
                "action": "plugin.draft",
                "target": "plugins",
                "request_id": request_id,
                "diff": {"fields": ["plugin_draft"]},
            }
            try:
                revision = await self.state.db.call(
                    self.state.admin_store.write_control, expected_revision, data, audit
                )
            except ControlConflict:
                raise GatewayError("conflict") from None
            except StartupError:
                raise GatewayError("unavailable") from None
            self.state.control = {"revision": revision, "data": data}
            return self.view(self.state.control)

    async def activate(
        self, *, actor: OperatorPrincipal, expected_revision: int, request_id: str = "internal"
    ) -> dict[str, Any]:
        async with self.state.management_mutation_lock:
            document = await self.identity._document(expected_revision, actor)
            if "plugin_draft" not in document["data"]:
                raise GatewayError("invalid_request")
            active = ChainDraft.model_validate(document["data"]["plugin_draft"])
            self.check(active, reconcile_managed=True)
            pending = copy.deepcopy(document)
            pending["data"]["plugin_active"] = active.model_dump()
            await self._save(
                pending, _policies(document), actor, "plugin.activate", "plugins", request_id
            )
            return self.view(self.state.control)

    def simulate(self, payload: ChainPreview) -> dict[str, Any]:
        self.check(payload)
        base = self._base()
        # Only trusted, built-in pure transforms have a text preview.
        rows: list[tuple[str, bool, Any]] = []
        for configured in payload.configured:
            spec = base.plugins[configured.id]
            module = PURE_MODULES.get(spec.module)
            instance = (
                module.create(module.Settings.model_validate(spec.settings))
                if module and configured.enabled
                else None
            )
            rows.append((configured.id, configured.enabled, instance))
        policies = _policies(self.state.control)
        for row in managed_rows(payload, policies["global"]):
            name = row.id
            rows.append(
                (
                    POLICY_PREFIX + name,
                    row.enabled,
                    create(PolicyDefinition.model_validate(policies["definitions"][name])),
                )
            )
        for item in payload.items:
            rows.append(
                (
                    item.spec.id,
                    item.enabled,
                    create(PolicyDefinition.model_validate(_definition(item.spec))),
                )
            )
        if payload.phase == "response":
            rows.reverse()
        steps = []
        output: str | None = payload.text
        failure = None
        for name, enabled, plugin in rows:
            before = output
            error = None
            if before is None:
                status = "not_run"
            elif not enabled:
                status = "disabled"
            elif plugin is None:
                status, error, output = "unsupported", "preview_unavailable", None
            else:
                settings = (
                    plugin.settings
                    if isinstance(plugin, content_policy.ContentPolicyPlugin)
                    else plugin
                )
                if settings.phase not in (payload.phase, "both"):
                    status = "skipped_phase"
                else:
                    transform = (
                        plugin._apply
                        if isinstance(plugin, content_policy.ContentPolicyPlugin)
                        else plugin._transform
                    )
                    output, matches = transform(before)
                    status = "applied"
                    if matches and settings.action == "block":
                        status, error, output = "denied", "policy_denied", None
                    elif output is not None and len(output) > 8192:
                        status, error, output = "error", "preview_size_limit", None
            failure = failure or error
            steps.append(
                {"id": name, "input": before, "output": output, "error": error, "status": status}
            )
        return {
            "input": payload.text,
            "output": output,
            "steps": steps,
            "error": failure,
            "provider_calls": 0,
        }

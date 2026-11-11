"""Strict, safe YAML configuration; credentials are resolved from the environment."""

import os
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from gateway7.errors import StartupError

MAX_CONFIG_BYTES = 1_048_576
MAX_CONFIG_NODES = 10_000
MAX_CONFIG_DEPTH = 64

InstanceName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")]
ModelId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
ModuleName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$",
        max_length=200,
    ),
]


class StrictConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class TransportConfig(StrictConfig):
    module: ModuleName
    settings: dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(StrictConfig):
    kind: Literal["fake", "claude", "openai", "gemini"] = "fake"
    base_url: str = Field(default="http://127.0.0.1:8001", min_length=1)
    key_env: str = Field(
        default="FAKE_LLM_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128
    )
    # Real adapters require an explicit model. Restrict IDs to a path-safe
    # alphabet because Gemini puts this server-controlled value in its URL.
    model: str = Field(default="fake", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    timeout_seconds: float = Field(default=30.0, gt=0, le=300, allow_inf_nan=False)
    transport: TransportConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def provider_defaults(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        defaults = {
            "claude": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
            "openai": ("https://api.openai.com", "OPENAI_API_KEY"),
            "gemini": ("https://generativelanguage.googleapis.com", "GEMINI_API_KEY"),
        }
        kind = value.get("kind", "fake")
        if isinstance(kind, str) and kind in defaults:
            value = dict(value)
            origin, environment = defaults[kind]
            value.setdefault("base_url", origin)
            value.setdefault("key_env", environment)
        return value


class LimitsConfig(StrictConfig):
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=300, allow_inf_nan=False)
    hook_timeout_seconds: float = Field(default=2.0, gt=0, le=300, allow_inf_nan=False)
    max_body_bytes: int = Field(default=65536, ge=1, le=10 * 1024 * 1024)
    max_concurrent_requests: int = Field(default=64, ge=1, le=10000)


class PluginConfig(StrictConfig):
    module: ModuleName
    enabled: bool = True
    required: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class ClientLimitsConfig(StrictConfig):
    max_concurrent_requests: int | None = Field(default=None, ge=1, le=10000)
    requests_per_minute: int | None = Field(default=None, ge=1, le=1_000_000)


class ClientConfig(StrictConfig):
    token_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    enabled: bool = True
    limits: ClientLimitsConfig = Field(default_factory=ClientLimitsConfig)
    models: list[ModelId] = Field(min_length=1, max_length=64)
    additional_middleware: list[InstanceName] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique_models(self) -> "ClientConfig":
        if len(self.models) != len(set(self.models)):
            raise ValueError("Client models must be unique")
        return self


class AuthConfig(StrictConfig):
    enabled: bool = False
    clients: dict[InstanceName, ClientConfig] = Field(default_factory=dict, max_length=128)
    operator_token_env: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128
    )

    @model_validator(mode="after")
    def consistent_clients(self) -> "AuthConfig":
        if self.enabled != bool(self.clients):
            raise ValueError(
                "Enabled authentication requires clients; disabled authentication requires none"
            )
        if self.operator_token_env is not None and not self.enabled:
            raise ValueError("Operator usage access requires client authentication")
        return self


class GatewayConfig(StrictConfig):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    plugins: dict[InstanceName, PluginConfig] = Field(default_factory=dict)
    middleware: list[InstanceName] = Field(default_factory=list)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @model_validator(mode="after")
    def real_providers_require_authentication(self) -> "GatewayConfig":
        if self.provider.kind != "fake" and not self.auth.enabled:
            raise ValueError("Real providers require gateway client authentication")
        return self


def _reject_duplicate_keys(node: yaml.Node | None) -> None:
    """Validate the bounded YAML graph before constructing configuration values."""
    if node is None:
        return
    heights: dict[int, int] = {}
    nodes = 0

    def visit(current: yaml.Node, ancestors: frozenset[int], depth: int) -> int:
        nonlocal nodes
        identity = id(current)
        if identity in ancestors:
            raise StartupError("Recursive YAML configuration is not supported")
        if depth > MAX_CONFIG_DEPTH:
            raise StartupError("Gateway configuration exceeds the YAML depth limit")
        if identity in heights:
            height = heights[identity]
            if depth + height - 1 > MAX_CONFIG_DEPTH:
                raise StartupError("Gateway configuration exceeds the YAML depth limit")
            return height
        nodes += 1
        if nodes > MAX_CONFIG_NODES:
            raise StartupError("Gateway configuration exceeds the YAML node limit")
        ancestors = ancestors | {identity}
        height = 1
        if isinstance(current, yaml.MappingNode):
            keys: set[str] = set()
            for key, value in current.value:
                if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                    raise StartupError("Configuration keys must be strings")
                if key.value in keys:
                    raise StartupError("Duplicate configuration key")
                keys.add(key.value)
                height = max(
                    height,
                    1 + visit(key, ancestors, depth + 1),
                    1 + visit(value, ancestors, depth + 1),
                )
        elif isinstance(current, yaml.SequenceNode):
            for item in current.value:
                height = max(height, 1 + visit(item, ancestors, depth + 1))
        heights[identity] = height
        return height

    visit(node, frozenset(), 1)


def load_config(path: str | Path) -> GatewayConfig:
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise StartupError("Gateway configuration exceeds the file size limit")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise StartupError("Cannot read gateway configuration") from None
    try:
        # Compose once, check graph structure and work limits, then construct only
        # safe YAML values. Memoized subtree heights keep alias checks linear.
        loader = yaml.SafeLoader(text)
        try:
            node = loader.get_single_node()
            _reject_duplicate_keys(node)
            data = None if node is None else loader.construct_document(node)
        finally:
            loader.dispose()
        if isinstance(data, dict) and "chains" in data:
            raise StartupError(
                "Legacy chains configuration: replace chains.request/response "
                "with middleware: [instance names]"
            )
        return GatewayConfig.model_validate(data, strict=True)
    except StartupError:
        raise
    except (yaml.YAMLError, ValidationError, TypeError, ValueError, RecursionError):
        raise StartupError("Invalid gateway configuration") from None


def provider_key(config: ProviderConfig) -> str:
    key = os.environ.get(config.key_env)
    if key is None or not key.strip():
        raise StartupError(f"Required environment variable {config.key_env} is missing or empty")
    return key

"""Strict, safe YAML configuration; credentials are resolved from the environment."""

import os
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from gateway7.errors import StartupError

InstanceName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")]


def validate_model_id(value: str) -> str:
    """Keep model IDs literal while bounding their UTF-8 wire representation."""
    if (
        not isinstance(value, str)
        or not value
        or any(c.isspace() or unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in value)
        or len(value.encode("utf-8")) > 1024
    ):
        raise ValueError("Invalid model ID")
    return value


def validate_provider_model(kind: str, value: str) -> str:
    """OpenAI IDs are opaque; other adapters retain their path-safe contract."""
    value = validate_model_id(value)
    if kind != "openai" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is None:
        raise ValueError("Invalid provider model ID")
    return value


ModelId = Annotated[str, BeforeValidator(validate_model_id)]
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
    model: ModelId = "fake"
    allowed_models: list[ModelId] | None = Field(default=None, max_length=64)
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

    @field_validator("allowed_models", mode="before")
    @classmethod
    def explicit_model_policy(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Omit allowed_models for unrestricted access")
        return value

    @model_validator(mode="after")
    def valid_models(self) -> "ProviderConfig":
        validate_provider_model(self.kind, self.model)
        if self.allowed_models is not None:
            if len(self.allowed_models) != len(set(self.allowed_models)):
                raise ValueError("Provider allowed_models must be unique")
            for model in self.allowed_models:
                validate_provider_model(self.kind, model)
        return self

    @model_serializer(mode="wrap")
    def serialize_model_policy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.allowed_models is None:
            data.pop("allowed_models", None)
        return data


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


class ClientConfig(StrictConfig):
    token_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    models: list[ModelId] | None = Field(default=None, max_length=64)

    @field_validator("models", mode="before")
    @classmethod
    def explicit_model_policy(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Omit models for unrestricted access")
        return value

    @model_validator(mode="after")
    def unique_models(self) -> "ClientConfig":
        if self.models is not None and len(self.models) != len(set(self.models)):
            raise ValueError("Client models must be unique")
        return self

    @model_serializer(mode="wrap")
    def serialize_model_policy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.models is None:
            data.pop("models", None)
        return data


class AuthConfig(StrictConfig):
    enabled: bool = False
    clients: dict[InstanceName, ClientConfig] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def consistent_clients(self) -> "AuthConfig":
        if self.enabled != bool(self.clients):
            raise ValueError(
                "Enabled authentication requires clients; disabled authentication requires none"
            )
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
        for client in self.auth.clients.values():
            if client.models is not None:
                for model in client.models:
                    validate_provider_model(self.provider.kind, model)
        return self


def _reject_duplicate_keys(node: yaml.Node | None, ancestors: frozenset[int] = frozenset()) -> None:
    """safe_load otherwise silently overwrites repeated plugin/config map keys."""
    if node is None:
        return
    if id(node) in ancestors:
        raise StartupError("Recursive YAML configuration is not supported")
    ancestors = ancestors | {id(node)}
    if isinstance(node, yaml.MappingNode):
        keys: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise StartupError("Configuration keys must be strings")
            if key.value in keys:
                raise StartupError("Duplicate configuration key")
            keys.add(key.value)
            _reject_duplicate_keys(value, ancestors)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _reject_duplicate_keys(item, ancestors)


def load_config(path: str | Path) -> GatewayConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise StartupError("Cannot read gateway configuration") from None
    try:
        # SafeLoader does not instantiate Python objects. The second pass rejects
        # duplicate map keys, aliases that recurse, and non-string keys.
        data = yaml.safe_load(text)
        _reject_duplicate_keys(yaml.compose(text, Loader=yaml.SafeLoader))
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

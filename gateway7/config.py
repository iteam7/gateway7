"""Strict, safe YAML configuration; credentials are resolved from the environment."""

import os
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from gateway7.errors import StartupError

InstanceName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
]
ModuleName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$",
        max_length=200,
    ),
]


class StrictConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class ProviderConfig(StrictConfig):
    kind: Literal["fake", "claude"] = "fake"
    base_url: str = Field(default="http://127.0.0.1:8001", min_length=1)
    key_env: str = Field(
        default="FAKE_LLM_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128
    )
    model: str = Field(default="fake", min_length=1)


class LimitsConfig(StrictConfig):
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=300, allow_inf_nan=False)
    hook_timeout_seconds: float = Field(default=2.0, gt=0, le=300, allow_inf_nan=False)
    max_body_bytes: int = Field(default=65536, ge=1, le=10 * 1024 * 1024)


class PluginConfig(StrictConfig):
    module: ModuleName
    enabled: bool = True
    required: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class GatewayConfig(StrictConfig):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    plugins: dict[InstanceName, PluginConfig] = Field(default_factory=dict)
    middleware: list[InstanceName] = Field(default_factory=list)


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

"""Version 1 plugin contract. Plugins are trusted in-process Python code."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from gateway7.models import ChatRequest, ChatResponse

API_VERSION = 1


@dataclass(frozen=True)
class PluginDescriptor:
    """A module's PLUGIN export describes its type, settings, and factory."""

    id: str
    api_version: int
    settings_model: type[BaseModel]
    create: Callable[[BaseModel], object]


@dataclass(frozen=True)
class Continue:
    payload: ChatRequest | ChatResponse


@dataclass(frozen=True)
class Deny:
    # The core returns only its own allowlisted denial code, never free text.
    code: str = "policy_denied"


@dataclass(frozen=True)
class PluginContext:
    request_id: str
    deadline: float
    # One fresh dict for each request and plugin instance, shared by its hooks.
    state: dict[str, Any]

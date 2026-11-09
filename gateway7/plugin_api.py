"""Version 2 middleware contract. Plugins are trusted in-process Python code.

An instance may opt in to early text with async prepare_early_stream(request,
context) -> ChatRequest | Deny. It must perform all request checks there and
raise EarlyStreamUnsupported if the configuration needs response processing.
The core never infers compatibility from third-party plugin settings.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from gateway7.models import ChatRequest, ChatResponse

API_VERSION = 2
SettingsT = TypeVar("SettingsT", bound=BaseModel)
NextHandler = Callable[[ChatRequest], Awaitable[ChatResponse]]


class EarlyStreamUnsupported(Exception):
    """The request cannot safely bypass response middleware for early text."""

    def __init__(self) -> None:
        super().__init__("Early streaming is not supported for this request")


class ResponsesUnsupported(Exception):
    """The configured provider or middleware cannot safely process native data."""

    def __init__(self) -> None:
        super().__init__("Native Responses is not supported for this request")


@dataclass(frozen=True)
class PluginDescriptor(Generic[SettingsT]):
    """A module's PLUGIN export describes its type, settings, and factory."""

    id: str
    api_version: int
    settings_model: type[SettingsT]
    create: Callable[[SettingsT], object]
    # Opt in only after inspecting structured arguments, definitions, and results.
    supports_tools: bool = False


@dataclass(frozen=True)
class Deny:
    # The core returns only its own allowlisted denial code, never free text.
    code: str = "policy_denied"


@dataclass(frozen=True)
class PluginContext:
    request_id: str
    deadline: float
    # One fresh dict per request and configured instance, across next().
    state: dict[str, Any]
    # Configured instance name, supplied by the core for safe policy diagnostics.
    instance_name: str = ""


@dataclass(frozen=True)
class ResponsesContext:
    """Native hook state; no Chat payload, routing authority, or consent grants.

    Optional API v2 hooks are prepare_responses(ResponsesRequest, context),
    check_responses(ResponsesResponse, context), and
    prepare_early_responses(ResponsesRequest, context). Each is async and returns
    its native payload type or Deny. Incompatible configurations raise
    ResponsesUnsupported; early hooks must not require response processing.
    """

    request_id: str
    deadline: float
    state: dict[str, Any]
    instance_name: str = ""

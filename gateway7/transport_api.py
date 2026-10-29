"""Version 1 provider transport contract for trusted in-process Python modules."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel

API_VERSION = 1
SettingsT = TypeVar("SettingsT", bound=BaseModel)


@dataclass(frozen=True)
class TransportDescriptor(Generic[SettingsT]):
    """A module exports TRANSPORT; its synchronous factory transfers ownership."""

    id: str
    api_version: int
    settings_model: type[SettingsT]
    create: Callable[[SettingsT], httpx.AsyncBaseTransport]

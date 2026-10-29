"""Validate trusted transport modules separately from constructing resources."""

import importlib
import inspect
import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from gateway7.config import TransportConfig
from gateway7.errors import StartupError
from gateway7.transport_api import API_VERSION, TransportDescriptor


@dataclass(frozen=True, repr=False)
class ValidatedTransport:
    descriptor: TransportDescriptor
    settings: BaseModel


def validate_transport_config(config: TransportConfig | None) -> ValidatedTransport | None:
    """Import and validate only: never invoke the factory or resolve credentials."""
    if config is None:
        return None
    try:
        module = importlib.import_module(config.module)
        descriptor = getattr(module, "TRANSPORT", None)
        if (
            type(descriptor) is not TransportDescriptor
            or not isinstance(descriptor.id, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", descriptor.id) is None
            or type(descriptor.api_version) is not int
            or descriptor.api_version != API_VERSION
            or not inspect.isclass(descriptor.settings_model)
            or not issubclass(descriptor.settings_model, BaseModel)
            or descriptor.settings_model.model_config.get("strict") is not True
            or descriptor.settings_model.model_config.get("extra") != "forbid"
            or descriptor.settings_model.model_config.get("frozen") is not True
            or not callable(descriptor.create)
            or inspect.iscoroutinefunction(descriptor.create)
        ):
            raise ValueError
        inspect.signature(descriptor.create).bind(None)
    except Exception:
        raise StartupError("Invalid provider transport module or descriptor") from None
    try:
        settings = descriptor.settings_model.model_validate(config.settings, strict=True)
    except Exception:
        raise StartupError("Invalid provider transport settings") from None
    return ValidatedTransport(descriptor, settings)


def create_transport(validated: ValidatedTransport | None) -> httpx.AsyncBaseTransport | None:
    """Construct once; the caller must close the returned transport or transfer it."""
    if validated is None:
        return None
    try:
        transport = validated.descriptor.create(validated.settings)
    except Exception:
        raise StartupError("Provider transport initialization failed") from None
    if inspect.isawaitable(transport):
        if inspect.iscoroutine(transport):
            transport.close()
        raise StartupError("Provider transport requires a synchronous factory")
    if not isinstance(transport, httpx.AsyncBaseTransport):
        raise StartupError("Provider transport factory returned an invalid transport")
    return transport

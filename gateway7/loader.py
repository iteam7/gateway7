"""Validate every configured module and assemble one ordered middleware chain."""

import asyncio
import importlib
import inspect
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.plugin_api import API_VERSION, PluginDescriptor

logger = logging.getLogger("gateway7")
AsyncHook = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class LoadedPlugin:
    name: str
    descriptor: PluginDescriptor
    instance: object
    handle: AsyncHook
    startup: AsyncHook | None
    shutdown: AsyncHook | None


@dataclass(frozen=True)
class LoadedPlugins:
    instances: dict[str, LoadedPlugin]
    middleware_chain: tuple[LoadedPlugin, ...]


def _hook(instance: object, name: str, instance_name: str) -> AsyncHook | None:
    try:
        value = getattr(instance, name, None)
        if value is None:
            return None
        if not callable(value) or not inspect.iscoroutinefunction(value):
            raise ValueError
        arguments = (None, None, None) if name == "handle" else ()
        inspect.signature(value).bind(*arguments)
    except Exception:
        raise StartupError(
            f"Plugin instance {instance_name} has invalid async hook {name}"
        ) from None
    return value


def load_plugins(config: GatewayConfig) -> LoadedPlugins:
    chain = config.middleware
    if len(chain) != len(set(chain)):
        raise StartupError("Duplicate plugin instance in middleware chain")
    for name in chain:
        if name not in config.plugins:
            raise StartupError(f"Unknown plugin instance {name} in middleware chain")

    # Validate all descriptors/settings first, including disabled modules. No
    # factory runs until all configuration-level checks have passed.
    descriptors: dict[str, tuple[PluginDescriptor, BaseModel]] = {}
    for name, specification in config.plugins.items():
        if specification.required and not specification.enabled:
            raise StartupError(f"Required plugin instance {name} must be enabled")
        try:
            module = importlib.import_module(specification.module)
        except Exception:
            raise StartupError(
                f"Cannot load module {specification.module} for plugin instance {name}; "
                "check module imports and migrate API v1 hooks/Continue to API v2 handle"
            ) from None
        try:
            descriptor = getattr(module, "PLUGIN", None)
        except Exception:
            raise StartupError(f"Invalid PLUGIN descriptor for plugin instance {name}") from None
        if (
            type(descriptor) is PluginDescriptor
            and type(descriptor.api_version) is int
            and descriptor.api_version == 1
        ):
            raise StartupError(
                f"Plugin instance {name} uses legacy API v1; "
                "migrate to API v2 handle(request, context, call_next)"
            )
        try:
            if (
                type(descriptor) is not PluginDescriptor
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
        except Exception:
            raise StartupError(f"Invalid PLUGIN descriptor for plugin instance {name}") from None
        try:
            settings = descriptor.settings_model.model_validate(specification.settings, strict=True)
        except Exception:
            raise StartupError(f"Invalid settings for plugin instance {name}") from None
        descriptors[name] = (descriptor, settings)

    instances: dict[str, LoadedPlugin] = {}
    for name, specification in config.plugins.items():
        if not specification.enabled:
            continue
        descriptor, settings = descriptors[name]
        try:
            instance = descriptor.create(settings)
        except Exception:
            raise StartupError(f"Cannot construct plugin instance {name}") from None
        if inspect.isawaitable(instance):
            if inspect.iscoroutine(instance):
                instance.close()
            raise StartupError(f"Plugin instance {name} requires a synchronous factory")
        handle = _hook(instance, "handle", name)
        if handle is None:
            raise StartupError(
                f"Plugin instance {name} requires API v2 async handle(request, context, call_next); "
                "migrate legacy on_request/on_response hooks"
            )
        plugin = LoadedPlugin(
            name=name,
            descriptor=descriptor,
            instance=instance,
            handle=handle,
            startup=_hook(instance, "startup", name),
            shutdown=_hook(instance, "shutdown", name),
        )
        instances[name] = plugin

    for name, specification in config.plugins.items():
        if specification.required and name not in chain:
            raise StartupError(f"Required plugin instance {name} is missing from middleware chain")
    active = tuple(instances[name] for name in chain if config.plugins[name].enabled)
    return LoadedPlugins(instances, active)


async def start_plugins(plugins: LoadedPlugins, timeout_seconds: float) -> None:
    started: list[LoadedPlugin] = []
    try:
        for plugin in plugins.instances.values():
            # Include a failing startup in cleanup: it may have acquired a resource.
            started.append(plugin)
            if plugin.startup is not None:
                deadline = time.monotonic() + timeout_seconds
                timer = asyncio.timeout(timeout_seconds)
                async with timer:
                    await plugin.startup()
                if timer.expired() or time.monotonic() >= deadline:
                    raise TimeoutError
    except BaseException as error:
        await _stop_instances(reversed(started), timeout_seconds)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise StartupError(f"Startup failed for plugin instance {plugin.name}") from None


async def _stop_instances(plugins: Any, timeout_seconds: float) -> None:
    for plugin in plugins:
        if plugin.shutdown is None:
            continue
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout_seconds):
                await plugin.shutdown()
        except Exception:
            logger.warning(
                "request_id=- outcome=shutdown_error component=%s duration_ms=%.3f",
                plugin.name,
                (time.monotonic() - started) * 1000,
            )


async def stop_plugins(plugins: LoadedPlugins, timeout_seconds: float) -> None:
    await _stop_instances(reversed(tuple(plugins.instances.values())), timeout_seconds)

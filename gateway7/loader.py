"""Validate every configured module and assemble one ordered middleware chain."""

import asyncio
import importlib
import inspect
import logging
import re
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.plugin_diagnostics import PluginDiagnosticError, diagnostic, validation_issues
from gateway7.plugin_api import API_VERSION, PLUGIN_COUNTERS, PluginDescriptor

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
    prepare_early_stream: AsyncHook | None = None
    prepare_responses: AsyncHook | None = None
    check_responses: AsyncHook | None = None
    prepare_early_responses: AsyncHook | None = None


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
        arguments = {
            "handle": (None, None, None),
            "prepare_early_stream": (None, None),
            "prepare_responses": (None, None),
            "check_responses": (None, None),
            "prepare_early_responses": (None, None),
        }.get(name, ())
        inspect.signature(value).bind(*arguments)
    except Exception:
        raise diagnostic(
            f"Plugin instance {instance_name} has invalid async hook {name}",
            "plugin_hook_invalid",
            f"plugins.{instance_name}.hooks.{name}",
            "Declare the documented async hook with the required positional arguments",
        ) from None
    return value


def load_plugins(config: GatewayConfig) -> LoadedPlugins:
    chain = config.middleware
    if len(chain) != len(set(chain)):
        raise StartupError("Duplicate plugin instance in middleware chain")
    for name in chain:
        if name not in config.plugins:
            raise StartupError(f"Unknown plugin instance {name} in middleware chain")
    for name, specification in config.plugins.items():
        if specification.required and not specification.enabled:
            raise StartupError(f"Required plugin instance {name} must be enabled")
        if specification.required and name not in chain:
            raise StartupError(f"Required plugin instance {name} is missing from middleware chain")
    for client in config.auth.clients.values():
        additional = client.additional_middleware
        if len(additional) != len(set(additional)):
            raise StartupError("Duplicate additional middleware in client policy")
        for name in additional:
            if name not in config.plugins:
                raise StartupError(f"Unknown additional middleware {name} in client policy")
            if not config.plugins[name].enabled:
                raise StartupError(f"Disabled additional middleware {name} in client policy")
            if name in chain:
                raise StartupError(f"Additional middleware {name} is already global")

    # Validate all descriptors/settings first, including disabled modules. No
    # factory runs until all configuration-level checks have passed.
    descriptors: dict[str, tuple[PluginDescriptor, BaseModel]] = {}
    for name, specification in config.plugins.items():
        try:
            module = importlib.import_module(specification.module)
        except Exception:
            raise diagnostic(
                f"Cannot load module {specification.module} for plugin instance {name}; check module imports and dependencies",
                "plugin_import_failed",
                f"plugins.{name}.module",
                "Check the declared project module and installed dependencies; imports and factories execute trusted code",
            ) from None
        try:
            descriptor = getattr(module, "PLUGIN", None)
        except Exception:
            raise diagnostic(
                f"Invalid PLUGIN descriptor for plugin instance {name}",
                "plugin_descriptor_invalid",
                f"plugins.{name}.PLUGIN",
                "Export PluginDescriptor with API 2, strict frozen extra-forbid settings and a synchronous factory",
            ) from None
        if (
            type(descriptor) is PluginDescriptor
            and type(descriptor.api_version) is int
            and descriptor.api_version != API_VERSION
        ):
            raise diagnostic(
                f"Invalid PLUGIN descriptor for plugin instance {name}",
                "plugin_api_unsupported",
                f"plugins.{name}.api_version",
                f"Use API {API_VERSION}; this descriptor declares API {descriptor.api_version}",
            )
        try:
            if (
                type(descriptor) is not PluginDescriptor
                or not isinstance(descriptor.id, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", descriptor.id) is None
                or type(descriptor.api_version) is not int
                or descriptor.api_version != API_VERSION
                or type(descriptor.supports_tools) is not bool
                or type(descriptor.counters) is not tuple
                or len(descriptor.counters) > len(PLUGIN_COUNTERS)
                or any(
                    type(item) is not str or item not in PLUGIN_COUNTERS
                    for item in descriptor.counters
                )
                or len(set(descriptor.counters)) != len(descriptor.counters)
                or not inspect.isclass(descriptor.settings_model)
                or not issubclass(descriptor.settings_model, BaseModel)
                or descriptor.settings_model.model_config.get("strict") is not True
                or descriptor.settings_model.model_config.get("extra") != "forbid"
                or descriptor.settings_model.model_config.get("frozen") is not True
                or not callable(descriptor.create)
                or inspect.iscoroutinefunction(descriptor.create)
                or inspect.iscoroutinefunction(getattr(descriptor.create, "__call__", None))
            ):
                raise ValueError
            inspect.signature(descriptor.create).bind(None)
        except Exception:
            raise diagnostic(
                f"Invalid PLUGIN descriptor for plugin instance {name}",
                "plugin_descriptor_invalid",
                f"plugins.{name}.PLUGIN",
                "Export PluginDescriptor with API 2, strict frozen extra-forbid settings and a synchronous factory",
            ) from None
        try:
            settings = descriptor.settings_model.model_validate(specification.settings, strict=True)
        except Exception as error:
            action = specification.settings.get("action")
            if (
                specification.module == "gateway7.plugins.content_policy"
                and descriptor.id == "content-policy"
                and type(action) is str
                and action not in ("block", "log", "redact")
                and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", action)
            ):
                raise StartupError(
                    f"Unsupported content policy action {action} for plugin instance {name}"
                ) from None
            message = f"Invalid settings for plugin instance {name}"
            if isinstance(error, ValidationError):
                try:
                    issues = validation_issues(
                        error, model=descriptor.settings_model, prefix=f"plugins.{name}.settings"
                    )
                except Exception:
                    issues = []
                if issues:
                    raise PluginDiagnosticError(message, issues) from None
            raise diagnostic(
                message,
                "plugin_settings_invalid",
                f"plugins.{name}.settings",
                "Inspect the settings schema and use only declared strict field types",
            ) from None
        descriptors[name] = (descriptor, settings)

    instances: dict[str, LoadedPlugin] = {}
    for name, specification in config.plugins.items():
        if not specification.enabled:
            continue
        descriptor, settings = descriptors[name]
        try:
            instance = descriptor.create(settings)
        except Exception:
            raise diagnostic(
                f"Cannot construct plugin instance {name}",
                "plugin_factory_failed",
                f"plugins.{name}.create",
                "Keep constructors cheap; acquire and release resources in startup/shutdown",
            ) from None
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
            prepare_early_stream=_hook(instance, "prepare_early_stream", name),
            prepare_responses=_hook(instance, "prepare_responses", name),
            check_responses=_hook(instance, "check_responses", name),
            prepare_early_responses=_hook(instance, "prepare_early_responses", name),
        )
        instances[name] = plugin

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
        try:
            await complete_cleanup(_stop_instances(reversed(started), timeout_seconds))
        except (Exception, asyncio.CancelledError):
            # Rollback must not replace the original startup failure/cancellation.
            pass
        if isinstance(error, asyncio.CancelledError):
            raise
        raise StartupError(f"Startup failed for plugin instance {plugin.name}") from None


async def complete_cleanup(operation: Coroutine[Any, Any, None]) -> None:
    """Finish owned cooperative cleanup, then re-raise the caller's cancellation."""
    cleanup = asyncio.create_task(operation)
    cancelled: asyncio.CancelledError | None = None
    try:
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as error:
                if cancelled is None:
                    cancelled = error
        cleanup.result()
    finally:
        if cancelled is not None:
            raise cancelled


async def _stop_instances(plugins: Any, timeout_seconds: float) -> None:
    for plugin in plugins:
        if plugin.shutdown is None:
            continue
        started = time.monotonic()
        timer = asyncio.timeout(timeout_seconds)
        try:
            async with timer:
                await plugin.shutdown()
            if timer.expired() or time.monotonic() - started >= timeout_seconds:
                raise TimeoutError
        except (Exception, asyncio.CancelledError):
            logger.warning(
                "request_id=- outcome=shutdown_error component=%s duration_ms=%.3f",
                plugin.name,
                (time.monotonic() - started) * 1000,
            )


async def stop_plugins(plugins: LoadedPlugins, timeout_seconds: float) -> None:
    await complete_cleanup(
        _stop_instances(reversed(tuple(plugins.instances.values())), timeout_seconds)
    )

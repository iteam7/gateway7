"""Ordered, fail-closed request/provider/response execution."""

import asyncio
import logging
import time
from typing import Any, TypeVar

from gateway7.config import LimitsConfig
from gateway7.errors import GatewayError
from gateway7.loader import LoadedPlugin, LoadedPlugins
from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import Continue, Deny, PluginContext

logger = logging.getLogger("gateway7")
Payload = TypeVar("Payload", ChatRequest, ChatResponse)


def _checkpoint(deadline: float) -> None:
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError
    if time.monotonic() >= deadline:
        raise GatewayError("timeout")


def _validated(payload: object, expected: type[Payload]) -> Payload:
    if not isinstance(payload, expected):
        raise ValueError("Invalid payload type")
    # model_copy/model_construct can bypass Pydantic validation. Dumping and
    # validating again also validates nested mutable collections in frozen models.
    return expected.model_validate(payload.model_dump(mode="python", warnings=False), strict=True)


def _log(request_id: str, outcome: str, component: str, started: float) -> None:
    logger.info(
        "request_id=%s outcome=%s component=%s duration_ms=%.3f",
        request_id,
        outcome,
        component,
        (time.monotonic() - started) * 1000,
    )


class Pipeline:
    def __init__(self, plugins: LoadedPlugins, provider: Any, limits: LimitsConfig) -> None:
        self.plugins = plugins
        self.provider = provider
        self.limits = limits

    async def _hook(
        self,
        plugin: LoadedPlugin,
        stage: str,
        payload: Payload,
        context: PluginContext,
        expected: type[Payload],
    ) -> Payload:
        _checkpoint(context.deadline)
        hook = getattr(plugin, f"on_{stage}")
        started = time.monotonic()
        hook_deadline = min(context.deadline, started + self.limits.hook_timeout_seconds)
        try:
            timer = asyncio.timeout_at(hook_deadline)
            try:
                async with timer:
                    result = await hook(payload, context)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                raise GatewayError("timeout" if timer.expired() else "plugin_error") from None
            except Exception:
                # Even a plugin-raised GatewayError cannot select the HTTP code.
                raise GatewayError("plugin_error") from None
            # A plugin may suppress cancellation; its late output is still refused.
            _checkpoint(hook_deadline)
            if type(result) is Deny:
                raise GatewayError("policy_denied")
            if type(result) is not Continue:
                raise GatewayError("plugin_error")
            output = _validated(result.payload, expected)
            _checkpoint(hook_deadline)
        except asyncio.CancelledError:
            _log(context.request_id, "cancelled", plugin.name, started)
            raise
        except TimeoutError:
            _log(context.request_id, "timeout", plugin.name, started)
            raise GatewayError("timeout") from None
        except GatewayError as error:
            _log(context.request_id, error.code, plugin.name, started)
            raise
        except Exception:
            _log(context.request_id, "plugin_error", plugin.name, started)
            raise GatewayError("plugin_error") from None
        _log(context.request_id, "continue", plugin.name, started)
        return output

    async def run(
        self, request: ChatRequest, request_id: str, *, deadline: float | None = None
    ) -> ChatResponse:
        deadline = deadline or time.monotonic() + self.limits.request_timeout_seconds
        contexts = {
            name: PluginContext(request_id, deadline, {}) for name in self.plugins.instances
        }
        try:
            async with asyncio.timeout_at(deadline):
                _checkpoint(deadline)
                for plugin in self.plugins.request_chain:
                    request = await self._hook(
                        plugin, "request", request, contexts[plugin.name], ChatRequest
                    )
                _checkpoint(deadline)
                started = time.monotonic()
                try:
                    response = _validated(await self.provider.complete(request), ChatResponse)
                except asyncio.CancelledError:
                    _log(request_id, "cancelled", "provider", started)
                    raise
                except Exception:
                    _log(request_id, "provider_error", "provider", started)
                    raise GatewayError("provider_error") from None
                _checkpoint(deadline)
                _log(request_id, "complete", "provider", started)
                # Preserve provider-reported usage; response plugins can transform
                # text but cannot rewrite the usage associated with that call.
                provider_usage = None if response.usage is None else dict(response.usage)
                for plugin in self.plugins.response_chain:
                    response = await self._hook(
                        plugin, "response", response, contexts[plugin.name], ChatResponse
                    )
                _checkpoint(deadline)
                result = ChatResponse(text=response.text, usage=provider_usage)
            _checkpoint(deadline)
            return result
        except TimeoutError:
            raise GatewayError("timeout") from None
        finally:
            # Request-owned state is intentionally never retained by the core.
            for context in contexts.values():
                context.state.clear()

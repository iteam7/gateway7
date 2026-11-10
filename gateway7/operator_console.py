"""Read-only operator assets and an explicit, credential-free state projection."""

from importlib.resources import files
from typing import Any, Literal

from starlette.responses import Response

from gateway7.config import GatewayConfig
from gateway7.pipeline import Pipeline

CONSOLE_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}
OPERATOR_PATHS = frozenset(
    {
        "/operator/console",
        "/operator/assets/console.css",
        "/operator/assets/console.js",
        "/operator/state",
        "/operator/usage",
    }
)


def console_asset(name: Literal["index.html", "console.css", "console.js"]) -> Response:
    media_type = {
        "index.html": "text/html",
        "console.css": "text/css",
        "console.js": "text/javascript",
    }[name]
    body = files("gateway7").joinpath("static", "operator_console", name).read_bytes()
    return Response(body, media_type=media_type, headers=CONSOLE_HEADERS)


def operator_state(
    config: GatewayConfig,
    pipeline: Pipeline,
    client_pipelines: dict[str, Pipeline],
    *,
    ready: bool,
) -> dict[str, Any]:
    """Project named fields only; plugin settings and credential references stay private."""
    configured_chains = {plugin.name for plugin in pipeline.plugins.middleware_chain}
    for pipeline_view in client_pipelines.values():
        configured_chains.update(plugin.name for plugin in pipeline_view.plugins.middleware_chain)
    clients = []
    for client_id, client_specification in config.auth.clients.items():
        client_pipeline = client_pipelines.get(client_id)
        clients.append(
            {
                "id": client_id,
                "enabled": client_specification.enabled,
                "models": list(client_specification.models),
                "limits": {
                    "max_concurrent_requests": client_specification.limits.max_concurrent_requests,
                    "requests_per_minute": client_specification.limits.requests_per_minute,
                },
                "additional_middleware": list(client_specification.additional_middleware),
                "effective_middleware": (
                    [plugin.name for plugin in client_pipeline.plugins.middleware_chain]
                    if client_pipeline is not None
                    else []
                ),
            }
        )
    plugins = []
    for name, plugin_specification in config.plugins.items():
        loaded = pipeline.plugins.instances.get(name)
        plugins.append(
            {
                "instance": name,
                "enabled": plugin_specification.enabled,
                "required": plugin_specification.required,
                "in_chain": name in configured_chains,
                "validation": "configuration_validated_at_startup",
                "capabilities": (
                    {
                        "plugin_id": loaded.descriptor.id,
                        "tool_inspection": loaded.descriptor.supports_tools,
                        "chat_early_hook": loaded.prepare_early_stream is not None,
                        "responses_request_hook": loaded.prepare_responses is not None,
                        "responses_response_hook": loaded.check_responses is not None,
                        "responses_early_hook": loaded.prepare_early_responses is not None,
                    }
                    if loaded is not None
                    else None
                ),
            }
        )
    return {
        "configuration": {
            "validation": "validated_at_startup",
            "changes_require_restart": True,
        },
        "gateway": {
            "ready": ready,
            "provider_kind": config.provider.kind,
            "max_concurrent_requests": config.limits.max_concurrent_requests,
        },
        "clients": clients,
        "middleware": {
            "global": list(config.middleware),
            "active_global": [plugin.name for plugin in pipeline.plugins.middleware_chain],
            "plugins": plugins,
        },
    }

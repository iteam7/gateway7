"""Read-only operator assets and an explicit, credential-free state projection."""

from importlib.resources import files
from typing import Any

from starlette.responses import Response

from gateway7.auth import _effective_models
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError
from gateway7.opencode import opencode_config
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


STATIC_ASSETS = frozenset(
    {
        "index.html",
        "console.css",
        "console.js",
        "admin_console.js",
        "admin_forms.js",
        "provider_panel.js",
        "identity_panel.js",
        "reporting_panel.js",
        "navigation.js",
        "policy_panel.js",
        "plugin_panel.js",
    }
)


def console_asset(name: str) -> Response:
    if name not in STATIC_ASSETS:
        raise GatewayError("not_found")
    media_type = (
        "text/html"
        if name == "index.html"
        else "text/css"
        if name == "console.css"
        else "text/javascript"
    )
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
    clients: list[dict[str, Any]] = []
    for client_id, client_specification in config.auth.clients.items():
        client_pipeline = client_pipelines.get(client_id)
        clients.append(
            {
                "id": client_id,
                "enabled": client_specification.enabled,
                "models": (
                    None
                    if client_specification.models is None
                    else list(client_specification.models)
                ),
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
    if config.auth.management_enabled:
        for row in clients:
            effective = _effective_models(config.provider.allowed_models, row["models"])
            row["effective_models"] = None if effective is None else list(effective)
            row["default_denied"] = effective is not None and config.provider.model not in effective
    plugins = []
    for name, plugin_specification in config.plugins.items():
        loaded = pipeline.plugins.instances.get(name)
        plugins.append(
            {
                "instance": name,
                "enabled": plugin_specification.enabled,
                "required": plugin_specification.required,
                "in_chain": name in configured_chains,
                "validation": (
                    "validated_before_activation"
                    if plugin_specification.module == "gateway7.policy_admin"
                    else "configuration_validated_at_startup"
                ),
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
    configuration: dict[str, Any] = {
        "validation": "validated_at_startup",
        "changes_require_restart": True,
    }
    if config.auth.management_enabled:
        configuration.update(
            {
                "management_enabled": True,
                "client_changes_require_restart": False,
            }
        )
    gateway: dict[str, Any] = {
        "ready": ready,
        "provider_kind": config.provider.kind,
        "max_concurrent_requests": config.limits.max_concurrent_requests,
    }
    if config.auth.management_enabled:
        gateway.update(
            {
                "default_model": config.provider.model,
                "allowed_models": config.provider.allowed_models,
            }
        )
    if config.grafana_url:
        gateway["grafana_url"] = config.grafana_url
    if (
        config.auth.management_enabled
        and "{" not in config.provider.model
        and "}" not in config.provider.model
    ):
        # The browser fills the base URL from its own origin, including a proxy prefix.
        gateway["opencode_profile"] = opencode_config("", config.provider.model)
    return {
        "configuration": configuration,
        "gateway": gateway,
        "clients": clients,
        "middleware": {
            "global": list(config.middleware),
            "active_global": [plugin.name for plugin in pipeline.plugins.middleware_chain],
            "plugins": plugins,
        },
    }

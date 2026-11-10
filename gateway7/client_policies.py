"""Startup-built client policy views share instances without changing global middleware."""

from gateway7.config import GatewayConfig
from gateway7.loader import LoadedPlugins
from gateway7.pipeline import Pipeline


def build_client_pipelines(
    config: GatewayConfig, plugins: LoadedPlugins, pipeline: Pipeline
) -> dict[str, Pipeline]:
    """Append operator-selected policies to the immutable global chain per client."""
    return {
        client_id: Pipeline(
            LoadedPlugins(
                plugins.instances,
                plugins.middleware_chain
                + tuple(plugins.instances[name] for name in client.additional_middleware),
            ),
            pipeline.provider,
            pipeline.limits,
            metrics=pipeline.metrics,
            provider_name=pipeline.provider_name,
        )
        for client_id, client in config.auth.clients.items()
        if client.enabled
    }

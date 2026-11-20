"""Operator-selected client policies extend the global chain on every API shape."""

import asyncio
import importlib
import logging
import sys
from types import ModuleType

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

from gateway7.app import create_app
from gateway7.cli import main
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.loader import load_plugins
from gateway7.models import ChatResponse
from gateway7.plugin_api import PluginDescriptor
from gateway7.responses_models import ResponsesResponse

MODEL = "model-a"
PRIVATE = "SYNTHETIC-CLIENT-POLICY-TEXT"
GLOBAL = "SYNTHETIC-GLOBAL-POLICY-TEXT"
TOKENS = {
    "restricted": "synthetic-restricted-client-token",
    "ordinary": "synthetic-ordinary-client-token",
}
CHAT = "/v1/chat/completions"
RESPONSES = "/v1/responses"


def policy(term, *, phase="request"):
    return {
        "module": "gateway7.plugins.content_policy",
        "settings": {
            "terms": [term],
            "phase": phase,
            "action": "block",
        },
    }


def configuration(*, additional=None, extra=None):
    return GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": MODEL},
            "plugins": {"global_guard": policy(GLOBAL), "client_guard": extra or policy(PRIVATE)},
            "middleware": ["global_guard"],
            "auth": {
                "enabled": True,
                "clients": {
                    name: {
                        "token_env": "POLICY_" + name.upper(),
                        "models": [MODEL],
                        "additional_middleware": (
                            additional if additional is not None else ["client_guard"]
                        )
                        if name == "restricted"
                        else [],
                    }
                    for name in TOKENS
                },
            },
        }
    )


def body(path, text, *, stream=False):
    if path == RESPONSES:
        return {"model": MODEL, "input": text, "store": False, "stream": stream}
    data = {"model": MODEL, "messages": [{"role": "user", "content": text}]}
    if path != "/chat":
        data["stream"] = stream
    return data


def headers(name, *, early=False):
    result = {"Authorization": "Bearer " + TOKENS[name]}
    if early:
        result["X-Gateway7-Stream-Mode"] = "early"
    return result


class Provider:
    def __init__(self):
        self.calls = []
        self.closed = 0

    async def complete(self, request, **options):
        self.calls.append("chat")
        await asyncio.sleep(0)
        return ChatResponse(text="Synthetic answer", usage={"input_tokens": 3, "output_tokens": 2})

    async def complete_early(self, request, *, on_text, **options):
        self.calls.append("early_chat")
        await on_text("Synthetic answer")
        return ChatResponse(text="Synthetic answer", usage={"input_tokens": 3, "output_tokens": 2})

    async def complete_responses(self, request, **options):
        self.calls.append("responses")
        await asyncio.sleep(0)
        return ResponsesResponse.model_validate(
            {
                "id": "resp_synthetic",
                "object": "response",
                "created_at": 1.0,
                "model": MODEL,
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_synthetic",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Synthetic answer",
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            }
        )

    async def complete_responses_early(self, request, **options):
        # The native profile may hold all text until final checked delivery.
        return await self.complete_responses(request, **options)

    async def aclose(self):
        self.closed += 1


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-policy-provider-secret")
    for name, token in TOKENS.items():
        monkeypatch.setenv("POLICY_" + name.upper(), token)

    def create(config=None):
        provider = Provider()
        monkeypatch.setattr(
            importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
        )
        return create_app(config=config or configuration()), provider

    return create


@pytest.mark.parametrize(
    "path,stream",
    [("/chat", False), (CHAT, False), (CHAT, True), (RESPONSES, False), (RESPONSES, True)],
)
def test_client_policy_extends_global_checks_for_all_buffered_shapes(gateway, path, stream, caplog):
    caplog.set_level(logging.INFO, logger="gateway7")
    app, provider = gateway()
    with TestClient(app) as client:
        allowed = client.post(
            path, headers=headers("ordinary"), json=body(path, PRIVATE, stream=stream)
        )
        denied = client.post(
            path, headers=headers("restricted"), json=body(path, PRIVATE, stream=stream)
        )
        assert allowed.status_code == 200, allowed.text
        assert denied.status_code == 403, denied.text
        for name in TOKENS:
            global_denial = client.post(
                path, headers=headers(name), json=body(path, GLOBAL, stream=stream)
            )
            assert global_denial.status_code == 403
        assert len(provider.calls) == 1
        assert tuple(p.name for p in app.state.pipeline.plugins.middleware_chain) == (
            "global_guard",
        )
        assert tuple(
            p.name for p in app.state.client_pipelines["restricted"].plugins.middleware_chain
        ) == (
            "global_guard",
            "client_guard",
        )
    assert "outcome=policy_match" in caplog.text
    assert PRIVATE not in caplog.text and GLOBAL not in caplog.text
    assert all(token not in caplog.text for token in TOKENS.values())


@pytest.mark.parametrize("path", [CHAT, RESPONSES])
def test_early_paths_use_the_authenticated_clients_additional_policy(gateway, path):
    app, provider = gateway()
    with TestClient(app) as client:
        denied = client.post(
            path, headers=headers("restricted", early=True), json=body(path, PRIVATE, stream=True)
        )
        assert denied.status_code == 403, denied.text
        assert provider.calls == []
        allowed = client.post(
            path, headers=headers("ordinary", early=True), json=body(path, PRIVATE, stream=True)
        )
        assert allowed.status_code == 200, allowed.text
        assert len(provider.calls) == 1


@pytest.mark.parametrize("path", [CHAT, RESPONSES])
def test_response_policy_cannot_be_silently_skipped_by_early_delivery(gateway, path):
    app, provider = gateway(configuration(extra=policy(PRIVATE, phase="response")))
    with TestClient(app) as client:
        denied = client.post(
            path,
            headers=headers("restricted", early=True),
            json=body(path, "ordinary", stream=True),
        )
        assert denied.status_code == 400, denied.text
        assert provider.calls == []


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    "additional,disabled,expected",
    [
        (["missing"], False, "Unknown additional middleware"),
        (["client_guard"], True, "Disabled additional middleware"),
        (["client_guard", "client_guard"], False, "Duplicate additional middleware"),
        (["global_guard"], False, "already global"),
    ],
)
def test_bad_client_policy_references_fail_before_any_factory(
    monkeypatch, additional, disabled, expected, enabled
):
    created = []
    module = ModuleType("synthetic_policy_factory")
    module.PLUGIN = PluginDescriptor(
        "synthetic", 2, Settings, lambda settings: created.append(settings)
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = configuration(additional=additional).model_dump(mode="python")
    config["auth"]["clients"]["restricted"]["enabled"] = enabled
    config["plugins"] = {
        "global_guard": {"module": module.__name__},
        "client_guard": {"module": module.__name__, "enabled": not disabled},
    }
    with pytest.raises(StartupError, match=expected):
        load_plugins(GatewayConfig.model_validate(config))
    assert created == []


def test_client_additions_are_bounded_by_configuration():
    with pytest.raises(ValidationError):
        configuration(additional=["client_guard"] * 65)


def test_invalid_policy_cli_diagnostics_do_not_expose_the_client_identity(tmp_path, capsys, caplog):
    private_name = "SYNTHETIC-PRIVATE-ACCOUNT"
    config = configuration(additional=["missing"]).model_dump(mode="python")
    config["auth"]["clients"][private_name] = config["auth"]["clients"].pop("restricted")
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(StartupError) as caught:
        load_plugins(GatewayConfig.model_validate(config))
    assert private_name not in str(caught.value)
    assert main(["validate", "--config", str(path)]) == 1
    output = capsys.readouterr()
    assert private_name not in output.out + output.err + caplog.text


def test_missing_authenticated_policy_view_never_falls_back_to_global(gateway):
    app, provider = gateway()
    with TestClient(app) as client:
        app.state.client_pipelines.pop("restricted")
        response = client.post(CHAT, headers=headers("restricted"), json=body(CHAT, PRIVATE))
        assert response.status_code == 503
        assert provider.calls == []


@pytest.mark.parametrize(
    "path,stream,early",
    [
        ("/chat", False, False),
        (CHAT, False, False),
        (CHAT, True, False),
        (RESPONSES, False, False),
        (RESPONSES, True, False),
        (CHAT, True, True),
        (RESPONSES, True, True),
    ],
)
@pytest.mark.asyncio
async def test_concurrent_clients_keep_distinct_immutable_effective_chains(
    gateway, path, stream, early
):
    app, provider = gateway()
    async with app.router.lifespan_context(app):
        views = dict(app.state.client_pipelines)
        chains = {name: view.plugins.middleware_chain for name, view in views.items()}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client:
            names = ["restricted", "ordinary"] * 10
            responses = await asyncio.gather(
                *[
                    client.post(
                        path,
                        headers=headers(name, early=early),
                        json=body(path, PRIVATE, stream=stream),
                    )
                    for name in names
                ]
            )
        assert [response.status_code for response in responses] == [403, 200] * 10
        assert len(provider.calls) == 10
        assert all(view.plugins.middleware_chain is chains[name] for name, view in views.items())
        assert all(
            view.plugins.instances is app.state.pipeline.plugins.instances
            for view in views.values()
        )


@pytest.mark.parametrize(
    "path,stream",
    [("/chat", False), (CHAT, False), (CHAT, True), (RESPONSES, False), (RESPONSES, True)],
)
def test_additional_response_policy_checks_output_for_its_client(gateway, path, stream):
    app, provider = gateway(configuration(extra=policy("Synthetic answer", phase="response")))
    with TestClient(app) as client:
        ordinary = client.post(
            path, headers=headers("ordinary"), json=body(path, "ordinary", stream=stream)
        )
        restricted = client.post(
            path, headers=headers("restricted"), json=body(path, "ordinary", stream=stream)
        )
        assert ordinary.status_code == 200, ordinary.text
        assert restricted.status_code == 403, restricted.text
        assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "path,stream,early",
    [
        ("/chat", False, False),
        (CHAT, False, False),
        (CHAT, True, False),
        (RESPONSES, False, False),
        (RESPONSES, True, False),
        (CHAT, True, True),
        (RESPONSES, True, True),
    ],
)
def test_admitted_policy_denial_consumes_only_that_clients_rate_budget(
    gateway, path, stream, early
):
    config = configuration().model_dump(mode="python")
    config["auth"]["clients"]["restricted"]["limits"] = {"requests_per_minute": 1}
    app, provider = gateway(GatewayConfig.model_validate(config))
    with TestClient(app) as client:
        denied = client.post(
            path,
            headers=headers("restricted", early=early),
            json=body(path, PRIVATE, stream=stream),
        )
        assert denied.status_code == 403, denied.text
        assert provider.calls == []
        limited = client.post(
            path,
            headers=headers("restricted", early=early),
            json=body(path, "ordinary", stream=stream),
        )
        assert limited.status_code == 429, limited.text
        assert limited.json()["error"]["code"] == "rate_limited"
        assert provider.calls == []
        ordinary = client.post(
            path, headers=headers("ordinary", early=early), json=body(path, PRIVATE, stream=stream)
        )
        assert ordinary.status_code == 200, ordinary.text
        assert len(provider.calls) == 1


@pytest.mark.parametrize("phase", ["request", "response"])
def test_client_policy_denial_releases_its_concurrency_lease(gateway, phase):
    term = PRIVATE if phase == "request" else "Synthetic answer"
    config = configuration(extra=policy(term, phase=phase)).model_dump(mode="python")
    config["auth"]["clients"]["restricted"]["limits"] = {"max_concurrent_requests": 1}
    app, provider = gateway(GatewayConfig.model_validate(config))
    with TestClient(app) as client:
        denied = client.post(CHAT, headers=headers("restricted"), json=body(CHAT, PRIVATE))
        assert denied.status_code == 403, denied.text
        again = client.post(CHAT, headers=headers("restricted"), json=body(CHAT, "ordinary"))
        assert again.status_code == (200 if phase == "request" else 403), again.text
        assert len(provider.calls) == (1 if phase == "request" else 2)
        assert app.state.admission.active == 0


def test_shared_additional_instances_have_one_owned_lifecycle(gateway, monkeypatch):
    events = []

    class Plugin:
        async def startup(self):
            events.append("startup")

        async def shutdown(self):
            events.append("shutdown")

        async def handle(self, request, context, call_next):
            assert not hasattr(context, "client_id")
            return await call_next(request)

    def create(settings):
        events.append("factory")
        return Plugin()

    module = ModuleType("synthetic_shared_policy")
    module.PLUGIN = PluginDescriptor("synthetic-shared", 2, Settings, create)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = configuration(extra={"module": module.__name__}).model_dump(mode="python")
    config["auth"]["clients"]["ordinary"]["additional_middleware"] = ["client_guard"]
    app, provider = gateway(GatewayConfig.model_validate(config))
    with TestClient(app) as client:
        for name in TOKENS:
            assert (
                client.post(CHAT, headers=headers(name), json=body(CHAT, "ordinary")).status_code
                == 200
            )
        assert events == ["factory", "startup"]
        assert (
            app.state.client_pipelines["restricted"].plugins.middleware_chain[-1]
            is (app.state.client_pipelines["ordinary"].plugins.middleware_chain[-1])
        )
    assert events == ["factory", "startup", "shutdown"]
    assert provider.closed == 1


@pytest.mark.parametrize("path,early", [(RESPONSES, False), (CHAT, True), (RESPONSES, True)])
def test_extra_chat_only_middleware_cannot_be_skipped_for_unsupported_paths(
    gateway, monkeypatch, path, early
):
    class ChatOnly:
        async def handle(self, request, context, call_next):
            return await call_next(request)

    module = ModuleType("synthetic_chat_only_policy")
    module.PLUGIN = PluginDescriptor(
        "synthetic-chat-only", 2, Settings, lambda settings: ChatOnly()
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    app, provider = gateway(configuration(extra={"module": module.__name__}))
    with TestClient(app) as client:
        response = client.post(
            path,
            headers=headers("restricted", early=early),
            json=body(path, "ordinary", stream=early),
        )
        assert response.status_code == 400
        assert provider.calls == []
        assert (
            client.post(
                path,
                headers=headers("ordinary", early=early),
                json=body(path, "ordinary", stream=early),
            ).status_code
            == 200
        )


def test_client_addition_order_and_response_unwinding_preserve_the_global_chain(
    gateway, monkeypatch
):
    class TaggedSettings(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
        marker: str

    class Tagged:
        def __init__(self, marker):
            self.marker = marker

        async def handle(self, request, context, call_next):
            processed = request.model_copy(
                update={
                    "messages": [
                        message.model_copy(update={"content": message.content + self.marker})
                        for message in request.messages
                    ]
                }
            )
            response = await call_next(processed)
            return response.model_copy(update={"text": response.text + self.marker})

    module = ModuleType("synthetic_ordered_policies")
    module.PLUGIN = PluginDescriptor(
        "synthetic-ordered", 2, TaggedSettings, lambda settings: Tagged(settings.marker)
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = configuration().model_dump(mode="python")
    config["plugins"] = {
        name: {"module": module.__name__, "settings": {"marker": marker}}
        for name, marker in (("global_guard", "[G]"), ("first", "[A]"), ("second", "[B]"))
    }
    config["plugins"]["global_guard"]["required"] = True
    config["auth"]["clients"]["restricted"]["additional_middleware"] = ["first", "second"]
    app, provider = gateway(GatewayConfig.model_validate(config))

    async def echo(request, **options):
        text = request.messages[-1].content
        provider.calls.append(text)
        return ChatResponse(text=text)

    monkeypatch.setattr(provider, "complete", echo)
    with TestClient(app) as client:
        restricted = client.post("/chat", headers=headers("restricted"), json=body("/chat", "ping"))
        ordinary = client.post("/chat", headers=headers("ordinary"), json=body("/chat", "ping"))
    assert provider.calls == ["ping[G][A][B]", "ping[G]"]
    assert restricted.json()["text"] == "ping[G][A][B][B][A][G]"
    assert ordinary.json()["text"] == "ping[G][G]"

"""Caller tokens and model permissions are enforced before any middleware work."""

import asyncio
import importlib

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway7.app import create_app
from gateway7.auth import AccessControl
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.models import ChatResponse

TOKEN_A = "gateway7-synthetic-client-alpha"
TOKEN_B = "gateway7-synthetic-client-beta"
PROVIDER_KEY = "gateway7-synthetic-provider-secret"


def access_config(**updates):
    data = {
        "provider": {"kind": "fake", "model": "model-a"},
        "auth": {"enabled": True, "clients": {
            "alpha": {"token_env": "CLIENT_ALPHA", "models": ["model-a"]},
            "beta": {"token_env": "CLIENT_BETA", "models": ["model-b"]},
        }},
    }
    data.update(updates)
    return GatewayConfig.model_validate(data)


class Provider:
    def __init__(self):
        self.calls = []

    async def complete(self, request, *, model=None):
        await asyncio.sleep(0)
        self.calls.append((request, model or "model-a"))
        return ChatResponse(text="answer", usage={"input_tokens": 3, "output_tokens": 2})

    async def aclose(self):
        pass


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", PROVIDER_KEY)
    monkeypatch.setenv("CLIENT_ALPHA", TOKEN_A)
    monkeypatch.setenv("CLIENT_BETA", TOKEN_B)


@pytest.fixture
def provider(monkeypatch):
    provider = Provider()
    app_module = importlib.import_module("gateway7.app")
    monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
    return provider


@pytest.mark.parametrize("auth", [None, {}, {"enabled": False}])
@pytest.mark.parametrize("kind", ["openai", "claude", "gemini"])
def test_real_providers_cannot_run_without_client_authentication(kind, auth):
    value = {"provider": {"kind": kind, "model": "configured-model"}}
    if auth is not None:
        value["auth"] = auth
    with pytest.raises(ValidationError):
        GatewayConfig.model_validate(value)


@pytest.mark.parametrize("auth", [
    {"enabled": True},
    {"enabled": False, "clients": {"ignored": {"token_env": "TOKEN", "models": ["fake"]}}},
    {"enabled": True, "clients": {"bad": {"token_env": "TOKEN", "models": []}}},
    {"enabled": True, "clients": {"bad": {"token_env": "TOKEN", "models": ["fake", "fake"]}}},
    {"enabled": True, "clients": {"bad": {"token_env": "TOKEN", "models": ["../escape"]}}},
])
def test_auth_configuration_is_strict(auth):
    with pytest.raises(ValidationError):
        GatewayConfig.model_validate({"auth": auth})


@pytest.mark.parametrize("value", [None, "", "too-short", "contains whitespace", "x" * 513, "non-ascii-ключ-private"])
def test_startup_rejects_invalid_client_tokens_safely(credentials, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CLIENT_ALPHA")
    else:
        monkeypatch.setenv("CLIENT_ALPHA", value)
    with pytest.raises(StartupError) as error:
        AccessControl(access_config())
    assert "CLIENT_ALPHA" in str(error.value)
    if value:
        assert value not in str(error.value)


def test_duplicate_tokens_and_provider_credential_reuse_are_rejected(credentials, monkeypatch):
    monkeypatch.setenv("CLIENT_BETA", TOKEN_A)
    with pytest.raises(StartupError, match="distinct bearer tokens"):
        AccessControl(access_config())
    monkeypatch.setenv("CLIENT_ALPHA", PROVIDER_KEY)
    with pytest.raises(StartupError, match="differ from the provider"):
        AccessControl(access_config())


def test_runtime_keeps_digests_and_requires_restart_for_rotation(credentials, monkeypatch):
    access = AccessControl(access_config())
    assert TOKEN_A not in repr(vars(access)) and TOKEN_B not in repr(vars(access))
    monkeypatch.setenv("CLIENT_ALPHA", "gateway7-synthetic-rotated-token")
    assert access.authenticate([(b"authorization", ("Bearer " + TOKEN_A).encode())]).models == ("model-a",)
    with pytest.raises(GatewayError):
        access.authenticate([(b"authorization", b"Bearer gateway7-synthetic-rotated-token")])


@pytest.mark.parametrize("headers", [
    [], [("authorization", "Bearer gateway7-synthetic-unknown")],
    [("authorization", "Basic " + TOKEN_A)], [("authorization", "Bearer")],
    [("authorization", "Bearer " + TOKEN_A + " ")], [("authorization", "Bearer " + "x" * 513)],
    [("authorization", "Bearer " + TOKEN_A), ("authorization", "Bearer " + TOKEN_A)],
    [("x-api-key", TOKEN_A)],
])
@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions", "/v1/responses", "/v1/models"])
def test_missing_invalid_duplicate_tokens_never_run_middleware(credentials, provider, monkeypatch, headers, path):
    from gateway7.plugins.phone_mask import PhoneMaskPlugin

    calls = []
    original = PhoneMaskPlugin.handle

    async def watched(self, *args):
        calls.append(1)
        return await original(self, *args)

    monkeypatch.setattr(PhoneMaskPlugin, "handle", watched)
    config = access_config(plugins={"mask": {"module": "gateway7.plugins.phone_mask"}}, middleware=["mask"])
    app = create_app(config=config)
    with TestClient(app) as client:
        if path.endswith("models"):
            response = client.get(path + "?api_key=" + TOKEN_A, headers=headers)
        else:
            response = client.post(path, headers=headers, content="not even valid JSON")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "unauthorized"
        assert TOKEN_A not in response.text and TOKEN_B not in response.text
        assert not calls and not provider.calls
        metrics = client.get("/metrics").text
        assert TOKEN_A not in metrics and TOKEN_B not in metrics and PROVIDER_KEY not in metrics


def test_allowed_default_model_forbidden_override_and_filtered_model_list(credentials, provider):
    app = create_app(config=access_config())
    with TestClient(app) as client:
        alpha = {"Authorization": "Bearer " + TOKEN_A}
        beta = {"Authorization": "Bearer " + TOKEN_B}
        message = {"messages": [{"role": "user", "content": "hello"}]}
        result = client.post("/chat", headers=alpha, json=message)
        assert result.status_code == 200
        assert set(result.json()) == {"text", "usage", "request_id"}
        assert provider.calls[-1][1] == "model-a"
        assert not hasattr(provider.calls[-1][0], "model")
        assert client.post("/chat", headers=alpha, json={**message, "model": "model-b"}).status_code == 403
        assert client.post("/chat", headers=beta, json=message).status_code == 403
        assert len(provider.calls) == 1
        assert client.post("/chat", headers=beta, json={**message, "model": "model-b"}).status_code == 200
        assert provider.calls[-1][1] == "model-b"
        assert [item["id"] for item in client.get("/v1/models", headers=alpha).json()["data"]] == ["model-a"]
        assert [item["id"] for item in client.get("/v1/models", headers=beta).json()["data"]] == ["model-b"]
        for path in ("/health", "/ready", "/metrics"):
            assert client.get(path).status_code == 200


def test_fake_anonymous_mode_cannot_select_another_model(credentials, provider):
    app = create_app(config=GatewayConfig())
    with TestClient(app) as client:
        response = client.post("/chat", json={"model": "another", "messages": [{"role": "user", "content": "hello"}]})
        assert response.status_code == 403
        assert not provider.calls
        assert [item["id"] for item in client.get("/v1/models").json()["data"]] == ["fake"]


async def test_concurrent_clients_cannot_change_each_others_model_permissions(credentials, provider):
    app = create_app(config=access_config())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://gateway") as client:
            async def call(token, model):
                return await client.post("/chat", headers={"Authorization": "Bearer " + token},
                                         json={"model": model, "messages": [{"role": "user", "content": model}]})
            results = await asyncio.gather(*(call(token, model) for token, model in [
                (TOKEN_A, "model-a"), (TOKEN_B, "model-b"), (TOKEN_A, "model-b"), (TOKEN_B, "model-a"),
            ] * 8))
            assert [result.status_code for result in results] == [200, 200, 403, 403] * 8
    assert len(provider.calls) == 16
    assert all(request.messages[0].content == selected for request, selected in provider.calls)


@pytest.mark.parametrize("path", ["/chat/", "/v1/chat/completions/", "/v1/responses/", "/v1/models/"])
@pytest.mark.parametrize("authenticated", [False, True])
def test_trailing_slashes_never_redirect_or_forward(credentials, provider, path, authenticated):
    app = create_app(config=access_config())
    headers = {"Authorization": "Bearer " + TOKEN_A} if authenticated else {}
    with TestClient(app, follow_redirects=False) as client:
        response = client.request(
            "GET" if "models" in path else "POST", path, headers=headers,
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert response.status_code == 404
        assert "location" not in response.headers
        assert response.json()["error"]["code"] == "not_found"
        if path.startswith("/v1/"):
            assert response.json()["error"]["type"] == "invalid_request_error"
        assert not provider.calls


def test_configured_client_identity_is_immutable_and_distinguishes_shared_models(credentials):
    from dataclasses import FrozenInstanceError

    config = access_config()
    data = config.model_dump()
    data["auth"]["clients"]["beta"]["models"] = ["model-a"]
    access = AccessControl(GatewayConfig.model_validate(data))
    alpha = access.authenticate([(b"authorization", ("Bearer " + TOKEN_A).encode())])
    beta = access.authenticate([(b"authorization", ("Bearer " + TOKEN_B).encode())])
    assert alpha.models == beta.models == ("model-a",)
    assert alpha.client_id == "alpha" and beta.client_id == "beta"
    with pytest.raises(FrozenInstanceError):
        alpha.client_id = "beta"
    assert AccessControl(GatewayConfig()).anonymous.client_id is None


def test_token_rotation_retains_configured_client_identity(credentials, monkeypatch):
    config = access_config()
    previous = AccessControl(config)
    rotated = "gateway7-synthetic-rotated-account-token"
    monkeypatch.setenv("CLIENT_ALPHA", rotated)
    current = AccessControl(config)
    old_principal = previous.authenticate([(b"authorization", ("Bearer " + TOKEN_A).encode())])
    new_principal = current.authenticate([(b"authorization", ("Bearer " + rotated).encode())])
    assert old_principal.client_id == new_principal.client_id == "alpha"
    assert old_principal.models == new_principal.models
    with pytest.raises(GatewayError, match="Missing or invalid"):
        current.authenticate([(b"authorization", ("Bearer " + TOKEN_A).encode())])


@pytest.mark.parametrize("unused_token", [None, "", "short", TOKEN_B, PROVIDER_KEY])
def test_suspended_clients_need_no_valid_or_distinct_credential(credentials, monkeypatch, unused_token):
    data = access_config().model_dump()
    data["auth"]["clients"]["alpha"]["enabled"] = False
    if unused_token is None:
        monkeypatch.delenv("CLIENT_ALPHA")
    else:
        monkeypatch.setenv("CLIENT_ALPHA", unused_token)
    access = AccessControl(GatewayConfig.model_validate(data))
    assert access.authenticate([(b"authorization", ("Bearer " + TOKEN_B).encode())]).client_id == "beta"
    with pytest.raises(GatewayError):
        access.authenticate([(b"authorization", ("Bearer " + TOKEN_A).encode())])


@pytest.mark.parametrize("enabled", [None, "true", "false", 0, 1])
def test_client_suspension_configuration_requires_a_boolean(enabled):
    data = access_config().model_dump()
    data["auth"]["clients"]["alpha"]["enabled"] = enabled
    with pytest.raises(ValidationError):
        GatewayConfig.model_validate(data)


@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions", "/v1/responses", "/v1/models"])
async def test_suspended_clients_are_rejected_before_body_or_middleware(
    credentials, provider, monkeypatch, caplog, path
):
    import json

    from gateway7.plugins.phone_mask import PhoneMaskPlugin

    data = access_config().model_dump()
    data["auth"]["clients"]["alpha"]["enabled"] = False
    middleware_calls = []
    original = PhoneMaskPlugin.handle

    async def watched(self, *args):
        middleware_calls.append(1)
        return await original(self, *args)

    monkeypatch.setattr(PhoneMaskPlugin, "handle", watched)
    data["plugins"] = {"mask": {"module": "gateway7.plugins.phone_mask"}}
    data["middleware"] = ["mask"]
    app = create_app(config=GatewayConfig.model_validate(data))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET" if path.endswith("models") else "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "",
        "headers": [(b"authorization", ("Bearer " + TOKEN_A).encode()),
                    (b"content-type", b"application/json")],
        "server": ("synthetic.test", 80), "client": ("synthetic", 1000),
    }
    sent = []

    async def receive():
        pytest.fail("Suspended account body was read")

    async def send(message):
        sent.append(message)

    with caplog.at_level("INFO", logger="gateway7"):
        async with app.router.lifespan_context(app):
            await app(scope, receive, send)
    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [401]
    body = b"".join(message.get("body", b"") for message in sent)
    assert json.loads(body)["error"]["code"] == "unauthorized"
    assert provider.calls == [] and middleware_calls == []
    assert TOKEN_A not in body.decode() + caplog.text


def test_active_client_identity_does_not_enter_prompt_response_or_diagnostics(
    credentials, provider, caplog
):
    from prometheus_client import generate_latest

    account_id = "SYNTHETIC_PRIVATE_ACCOUNT"
    data = access_config().model_dump()
    data["auth"]["clients"][account_id] = data["auth"]["clients"].pop("alpha")
    app = create_app(config=GatewayConfig.model_validate(data))
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        response = client.post(
            "/chat", headers={"Authorization": "Bearer " + TOKEN_A},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        metrics = generate_latest(app.state.metrics.registry).decode()
    assert response.status_code == 200
    assert app.state.config.auth.clients[account_id].enabled is True
    assert account_id not in response.text + caplog.text + metrics
    assert account_id not in str(provider.calls[0][0].model_dump())
    assert TOKEN_A not in response.text + caplog.text + metrics


def test_suspended_account_without_secret_preserves_other_clients_model_access(
    credentials, provider, monkeypatch
):
    data = access_config().model_dump()
    data["auth"]["clients"]["alpha"]["enabled"] = False
    monkeypatch.delenv("CLIENT_ALPHA")
    with TestClient(create_app(config=GatewayConfig.model_validate(data))) as client:
        headers = {"Authorization": "Bearer " + TOKEN_B}
        allowed = client.post(
            "/chat", headers=headers,
            json={"model": "model-b", "messages": [{"role": "user", "content": "hello"}]},
        )
        forbidden = client.post(
            "/chat", headers=headers,
            json={"model": "model-a", "messages": [{"role": "user", "content": "hello"}]},
        )
    assert allowed.status_code == 200 and forbidden.status_code == 403
    assert len(provider.calls) == 1 and provider.calls[0][1] == "model-b"

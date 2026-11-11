"""Read-only operator UI boundaries use the actual gateway with synthetic credentials."""

import importlib
import json
from html.parser import HTMLParser

from fastapi.testclient import TestClient
from prometheus_client import generate_latest
import pytest

from gateway7.app import create_app
from gateway7.analytics import Analytics
from gateway7.config import GatewayConfig
from gateway7.models import ChatResponse
from gateway7.operator_console import console_asset
from gateway7.telemetry import Telemetry

OPERATOR = "synthetic-console-operator-credential"
CLIENT = "synthetic-console-client-credential"
PROVIDER_KEY = "synthetic-console-provider-credential"
PRIVATE = "SYNTHETIC_PRIVATE_POLICY_TERM"
ACCOUNT = "SYNTHETIC_PRIVATE_ACCOUNT"
SHARED = "synthetic_shared_email"
EXTRA = "synthetic_extra_phone"
DISABLED = "synthetic_disabled_policy"
OPERATOR_HEADERS = {"Authorization": "Bearer " + OPERATOR}
PATHS = (
    "/operator/console",
    "/operator/assets/console.css",
    "/operator/assets/console.js",
    "/operator/state",
)


class Provider:
    def __init__(self):
        self.calls = []
        self.usage = {"input_tokens": 7, "output_tokens": 3}

    async def complete(self, request, **options):
        self.calls.append(request)
        return ChatResponse(text="synthetic answer", usage=self.usage)

    async def aclose(self):
        pass


@pytest.fixture
def console_app(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", PROVIDER_KEY)
    monkeypatch.setenv("CONSOLE_TEST_OPERATOR", OPERATOR)
    monkeypatch.setenv("CONSOLE_TEST_CLIENT", CLIENT)
    monkeypatch.delenv("CONSOLE_TEST_SUSPENDED", raising=False)

    def build(*, enabled=True):
        provider = Provider()
        monkeypatch.setattr(
            importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
        )
        config = GatewayConfig.model_validate(
            {
                "auth": {
                    "enabled": True,
                    **({"operator_token_env": "CONSOLE_TEST_OPERATOR"} if enabled else {}),
                    "clients": {
                        ACCOUNT: {
                            "token_env": "CONSOLE_TEST_CLIENT",
                            "models": ["fake"],
                            "limits": {"max_concurrent_requests": 2, "requests_per_minute": 30},
                            "additional_middleware": [EXTRA],
                        },
                        "synthetic_suspended": {
                            "token_env": "CONSOLE_TEST_SUSPENDED",
                            "enabled": False,
                            "models": ["fake"],
                        },
                    },
                },
                "plugins": {
                    SHARED: {"module": "gateway7.plugins.email_mask", "required": True},
                    EXTRA: {"module": "gateway7.plugins.phone_mask"},
                    DISABLED: {
                        "module": "gateway7.plugins.content_policy",
                        "enabled": False,
                        "settings": {"terms": [PRIVATE]},
                    },
                },
                "middleware": [SHARED],
            }
        )
        return create_app(
            config=config, telemetry=Telemetry.disabled(), analytics=Analytics.disabled()
        ), provider

    return build


@pytest.mark.parametrize("path", PATHS)
def test_disabled_console_is_not_exposed(console_app, path):
    app, provider = console_app(enabled=False)
    with TestClient(app) as client:
        response = client.get(path, headers=OPERATOR_HEADERS)
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert ACCOUNT not in response.text and PRIVATE not in response.text
    assert provider.calls == []


@pytest.mark.parametrize("path", PATHS[:3])
def test_public_assets_contain_no_operator_state_and_use_restrictive_headers(console_app, path):
    app, provider = console_app()
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    policy = response.headers["content-security-policy"]
    for directive in (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "form-action 'none'",
        "base-uri 'none'",
    ):
        assert directive in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert "set-cookie" not in response.headers
    for value in (ACCOUNT, SHARED, EXTRA, PRIVATE, OPERATOR, CLIENT, PROVIDER_KEY):
        assert value not in response.text
    assert provider.calls == []


class ConsoleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_packaged_static_shell_uses_external_same_origin_assets_and_safe_form():
    parser = ConsoleHTML()
    parser.feed(bytes(console_asset("index.html").body).decode())
    scripts = [attrs for tag, attrs in parser.elements if tag == "script"]
    styles = [attrs for tag, attrs in parser.elements if tag == "link"]
    assert scripts == [{"src": "./assets/console.js", "defer": None}]
    assert styles == [{"rel": "stylesheet", "href": "./assets/console.css"}]
    assert not [tag for tag, _ in parser.elements if tag in ("iframe", "style", "img")]
    token_input = next(attrs for tag, attrs in parser.elements if tag == "input")
    assert token_input["type"] == "password" and token_input["autocomplete"] == "off"
    assert "name" not in token_input and "value" not in token_input
    for name, media_type in (("console.js", "text/javascript"), ("console.css", "text/css")):
        response = console_asset(name)
        assert response.headers["content-type"].startswith(media_type)
        assert len(response.body) > 100


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Authorization", "Bearer " + CLIENT)],
        [("Authorization", "Bearer " + PROVIDER_KEY)],
        [("Authorization", "Bearer synthetic-console-wrong-credential")],
        [*OPERATOR_HEADERS.items(), *OPERATOR_HEADERS.items()],
    ],
)
def test_console_state_requires_the_separate_operator_capability(console_app, headers):
    app, provider = console_app()
    with TestClient(app) as client:
        response = client.get("/operator/state", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "unauthorized"
    assert ACCOUNT not in response.text and OPERATOR not in response.text
    assert provider.calls == []


@pytest.mark.parametrize("enabled", [False, True])
async def test_console_state_checks_access_before_body_and_ignores_query_or_cookie(
    console_app, enabled
):
    app, provider = console_app(enabled=enabled)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/operator/state",
        "raw_path": b"/operator/state",
        "query_string": ("token=" + OPERATOR).encode(),
        "root_path": "",
        "headers": [(b"cookie", ("token=" + OPERATOR).encode())],
        "server": ("synthetic.test", 80),
        "client": ("synthetic", 1000),
    }
    sent = []

    async def receive():
        pytest.fail("Operator access was checked after reading the request body")

    async def send(message):
        sent.append(message)

    async with app.router.lifespan_context(app):
        await app(scope, receive, send)
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert [message["status"] for message in starts] == [401 if enabled else 404]
    assert ACCOUNT not in str(sent) and OPERATOR not in str(sent)
    assert provider.calls == []


def test_operator_state_projects_only_safe_configuration_and_truthful_startup_metadata(console_app):
    app, provider = console_app()
    with TestClient(app) as client:
        response = client.get("/operator/state", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    snapshot = response.json()
    assert set(snapshot) == {"configuration", "gateway", "clients", "middleware", "usage"}
    assert snapshot["configuration"] == {
        "validation": "validated_at_startup", "changes_require_restart": True,
    }
    assert snapshot["gateway"]["ready"] is True
    account = next(client for client in snapshot["clients"] if client["id"] == ACCOUNT)
    assert account["limits"] == {"max_concurrent_requests": 2, "requests_per_minute": 30}
    assert account["models"] == ["fake"]
    assert account["additional_middleware"] == [EXTRA]
    assert account["effective_middleware"] == [SHARED, EXTRA]
    suspended = next(client for client in snapshot["clients"] if not client["enabled"])
    assert suspended["effective_middleware"] == []
    assert snapshot["middleware"]["global"] == [SHARED]
    plugins = {plugin["instance"]: plugin for plugin in snapshot["middleware"]["plugins"]}
    assert plugins[SHARED]["required"] is True and plugins[SHARED]["in_chain"] is True
    assert plugins[EXTRA]["in_chain"] is True
    assert plugins[SHARED]["capabilities"]["plugin_id"] == "email-mask"
    assert plugins[SHARED]["capabilities"]["responses_request_hook"] is True
    assert plugins[DISABLED]["enabled"] is False
    assert plugins[DISABLED]["capabilities"] is None
    assert plugins[DISABLED]["validation"] == "configuration_validated_at_startup"
    for value in (
        PRIVATE, OPERATOR, CLIENT, PROVIDER_KEY, "CONSOLE_TEST_OPERATOR", "CONSOLE_TEST_CLIENT",
        "CONSOLE_TEST_SUSPENDED", "FAKE_LLM_API_KEY", "127.0.0.1", "settings", "token_env", "base_url",
    ):
        assert value not in response.text
    assert provider.calls == []


def test_console_usage_uses_real_client_pipelines_and_preserves_unknown_usage(console_app, caplog):
    app, provider = console_app()
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        headers = {"Authorization": "Bearer " + CLIENT}
        for usage in ({"input_tokens": 7, "output_tokens": 3}, None):
            provider.usage = usage
            response = client.post(
                "/chat", headers=headers,
                json={"messages": [{"role": "user", "content": "synthetic@example.com"}]},
            )
            assert response.status_code == 200
        response = client.get("/operator/state", headers=OPERATOR_HEADERS)
        metrics = generate_latest(app.state.metrics.registry).decode()
        assert "/operator/state" not in app.openapi()["paths"]
        assert "/operator/console" not in app.openapi()["paths"]
    row = response.json()["usage"]["clients"][ACCOUNT]
    assert row["provider_attempts"] == row["outcomes"]["complete"] == 2
    assert row["known_input_tokens"] == 7 and row["known_output_tokens"] == 3
    assert row["input_usage_unknown_attempts"] == row["output_usage_unknown_attempts"] == 1
    assert len(provider.calls) == 2
    assert all(call.messages[0].content == "[EMAIL]" for call in provider.calls)
    for value in (ACCOUNT, OPERATOR, CLIENT, PROVIDER_KEY, PRIVATE):
        assert value not in caplog.text + metrics
    assert ACCOUNT not in json.dumps([call.model_dump() for call in provider.calls])


@pytest.mark.parametrize("path", PATHS)
def test_operator_console_has_no_write_routes(console_app, path):
    app, provider = console_app()
    with TestClient(app) as client:
        response = client.post(path, headers=OPERATOR_HEADERS)
    assert response.status_code == 405
    assert response.headers["cache-control"] == "no-store"
    assert ACCOUNT not in response.text and provider.calls == []


@pytest.mark.parametrize("path", ["/operator/assets/unknown.js", "/operator/assets/%2e%2e/app.py"])
def test_operator_assets_never_resolve_arbitrary_package_paths(console_app, path):
    app, provider = console_app()
    with TestClient(app) as client:
        response = client.get(path, headers=OPERATOR_HEADERS)
    assert response.status_code == 404 and provider.calls == []
    assert "FastAPI" not in response.text and "Traceback" not in response.text

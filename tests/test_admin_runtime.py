"""Exercise live operator management using synthetic credentials and providers."""

import asyncio
import csv
import importlib
import io
import os
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway7.analytics import Analytics
from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.models import ChatResponse
from gateway7.responses_models import ResponsesResponse
from gateway7.telemetry import Telemetry

OPERATOR = "synthetic-admin-runtime-operator-token"
PROVIDER = "synthetic-admin-runtime-provider-token"
SEED = "synthetic-admin-runtime-seed-token"
WRITE = {"Authorization": "Bearer " + OPERATOR, "X-Gateway7-Operator": "true"}
READ = {"Authorization": "Bearer " + OPERATOR}
MODEL = "model-a"


class Provider:
    def __init__(self):
        self.calls = []
        self.wait = None
        self.entered = None

    async def complete(self, request, **options):
        self.calls.append(request)
        if self.entered is not None:
            self.entered.set()
        if self.wait is not None:
            await self.wait.wait()
        return ChatResponse(text="synthetic answer", usage={"input_tokens": 7, "output_tokens": 3})

    async def complete_early(self, request, *, on_text, **options):
        result = await self.complete(request, **options)
        await on_text(result.text)
        return result

    async def complete_responses(self, request, **options):
        self.calls.append(request)
        return ResponsesResponse.model_validate(
            {
                "id": "resp_synthetic",
                "object": "response",
                "created_at": 1.0,
                "model": MODEL,
                "status": "completed",
                "output": [],
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            }
        )

    async def complete_responses_early(self, request, **options):
        return await self.complete_responses(request, **options)

    async def aclose(self):
        pass


@pytest.fixture(params=["sqlite", "postgres"])
def managed(monkeypatch, tmp_path, request):
    monkeypatch.setenv("OPENAI_API_KEY", PROVIDER)
    monkeypatch.setenv("ADMIN_RUNTIME_OPERATOR", OPERATOR)
    monkeypatch.setenv("ADMIN_RUNTIME_SEED", SEED)
    backend = {"management_db": str(tmp_path / "private" / "users.sqlite3")}
    if request.param == "postgres":
        dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("Set GATEWAY7_TEST_POSTGRES_DSN to test a disposable PostgreSQL database")
        psycopg = pytest.importorskip("psycopg")
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
        monkeypatch.setenv("ADMIN_RUNTIME_DATABASE_URL", dsn)
        backend = {"management_database_url_env": "ADMIN_RUNTIME_DATABASE_URL"}
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": MODEL, "allowed_models": [MODEL, "model-b"]},
            "auth": {
                "enabled": True,
                "operator_token_env": "ADMIN_RUNTIME_OPERATOR",
                **backend,
                "clients": {},
            },
            "plugins": {"phone": {"module": "gateway7.plugins.phone_mask"}},
        }
    )
    providers = []

    def build(config_override=None):
        provider = Provider()
        providers.append(provider)
        monkeypatch.setattr(
            importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
        )
        return create_app(
            config=config_override or config,
            analytics=Analytics.disabled(),
            telemetry=Telemetry.disabled(),
        ), provider

    yield build, config
    if request.param == "postgres":
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


def create(client, identity="synthetic_user", **policy):
    response = client.post("/operator/clients", headers=WRITE, json={"id": identity, **policy})
    assert response.status_code == 201, response.text
    return response.json()["token"]


def bearer(token):
    return {"Authorization": "Bearer " + token}


def body(path, *, model=MODEL, stream=False):
    if path == "/v1/responses":
        return {"model": model, "input": "synthetic prompt", "store": False, "stream": stream}
    value = {"model": model, "messages": [{"role": "user", "content": "synthetic prompt"}]}
    if path != "/chat":
        value["stream"] = stream
    return value


SHAPES = [
    ("/chat", False, False),
    ("/v1/chat/completions", False, False),
    ("/v1/chat/completions", True, False),
    ("/v1/chat/completions", True, True),
    ("/v1/responses", False, False),
    ("/v1/responses", True, False),
    ("/v1/responses", True, True),
    ("/v1/models", False, False),
]


@pytest.mark.parametrize("action", ["rotate", "revoke", "suspend", "delete"])
@pytest.mark.parametrize("path,stream,early", SHAPES)
def test_removed_access_denies_every_api_shape_before_provider(
    managed, action, path, stream, early
):
    build, _ = managed
    app, provider = build()
    with TestClient(app) as client:
        token = create(client, models=[MODEL])
        if action == "rotate":
            response = client.post("/operator/clients/synthetic_user/token", headers=WRITE)
        elif action == "revoke":
            response = client.delete("/operator/clients/synthetic_user/token", headers=WRITE)
        elif action == "delete":
            response = client.delete("/operator/clients/synthetic_user", headers=WRITE)
        else:
            response = client.put(
                "/operator/clients/synthetic_user",
                headers=WRITE,
                json={"enabled": False, "models": [MODEL]},
            )
        assert response.status_code in (200, 204)
        headers = bearer(token)
        if early:
            headers["X-Gateway7-Stream-Mode"] = "early"
        response = (
            client.get(path, headers=headers)
            if path == "/v1/models"
            else client.post(path, headers=headers, json=body(path, stream=stream))
        )
        assert response.status_code == 401
        assert provider.calls == []


def test_live_policy_and_usage_survive_restart_without_bootstrap_env(managed, monkeypatch):
    build, config = managed
    seeded = config.model_dump()
    seeded["auth"]["clients"] = {"seed": {"token_env": "ADMIN_RUNTIME_SEED", "models": [MODEL]}}
    config = GatewayConfig.model_validate(seeded)
    app, provider = build(config)
    with TestClient(app) as client:
        token = create(client, models=[MODEL], additional_middleware=["phone"])
        assert client.post("/chat", headers=bearer(token), json=body("/chat")).status_code == 200
        assert (
            client.post(
                "/chat", headers=bearer(token), json=body("/chat", model="model-b")
            ).status_code
            == 403
        )
        rotated = client.post("/operator/clients/seed/token", headers=WRITE).json()["token"]
        snapshot = client.get("/operator/state", headers=READ).json()
        assert snapshot["configuration"]["management_enabled"] is True
        assert snapshot["configuration"]["client_changes_require_restart"] is False
        assert snapshot["usage"]["reset_on_restart"] is False
        assert snapshot["usage"]["rows"][0]["model"] == MODEL
        assert snapshot["usage"]["clients"]["synthetic_user"]["provider_attempts"] == 1
        for secret in (token, rotated, OPERATOR, PROVIDER, "token_env", config.auth.management_db):
            if secret is not None:
                assert secret not in str(snapshot)
    monkeypatch.delenv("ADMIN_RUNTIME_SEED")
    app, provider = build(config)
    with TestClient(app) as client:
        assert client.post("/chat", headers=bearer(rotated), json=body("/chat")).status_code == 200
        assert client.post("/chat", headers=bearer(SEED), json=body("/chat")).status_code == 401
        assert client.post("/chat", headers=bearer(token), json=body("/chat")).status_code == 200
        usage = client.get("/operator/usage", headers=READ).json()
        assert usage["clients"]["synthetic_user"]["provider_attempts"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"models": [MODEL, MODEL]},
        {"models": ["invalid model"]},
        {"additional_middleware": ["missing"]},
        {"additional_middleware": ["phone", "phone"]},
        {"token_env": "PRIVATE_ENV"},
        {"token": "synthetic-unaccepted-token"},
        {"limits": {"requests_per_minute": 0}},
        {"enabled": "true"},
    ],
)
def test_invalid_client_update_is_transactional_and_sanitized(managed, payload):
    build, _ = managed
    app, _ = build()
    with TestClient(app) as client:
        create(client, models=[MODEL])
        before = client.get("/operator/state", headers=READ).json()
        response = client.put("/operator/clients/synthetic_user", headers=WRITE, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"
        assert (
            "PRIVATE_ENV" not in response.text and "synthetic-unaccepted-token" not in response.text
        )
        assert client.get("/operator/state", headers=READ).json() == before


def test_failed_save_never_publishes_phantom_user_or_token(managed, monkeypatch):
    build, _ = managed
    app, _ = build()
    with TestClient(app) as client:
        before = client.get("/operator/state", headers=READ).json()

        def fail(*args):
            raise StartupError("synthetic private database error")

        monkeypatch.setattr(app.state.admin_store, "save_clients", fail)
        response = client.post("/operator/clients", headers=WRITE, json={"id": "phantom"})
        assert response.status_code == 503
        assert "synthetic private" not in response.text
        assert client.get("/operator/state", headers=READ).json() == before


def test_usage_filters_export_and_deleted_history(managed):
    build, _ = managed
    app, provider = build()
    with TestClient(app) as client:
        token = create(client, models=[MODEL, "model-b"])
        for model in (MODEL, "model-b"):
            assert (
                client.post(
                    "/chat", headers=bearer(token), json=body("/chat", model=model)
                ).status_code
                == 200
            )
        day = datetime.now(timezone.utc).date().isoformat()
        params = {"client_id": "synthetic_user", "model": "model-b", "start": day, "end": day}
        filtered = client.get("/operator/usage", headers=READ, params=params).json()
        assert len(filtered["rows"]) == 1 and filtered["rows"][0]["model"] == "model-b"
        assert filtered["clients"]["synthetic_user"]["known_input_tokens"] == 7
        export = client.get("/operator/usage/export", headers=READ, params=params)
        rows = list(csv.DictReader(io.StringIO(export.text)))
        assert rows[0]["model"] == "model-b" and rows[0]["provider_attempts"] == "1"
        assert "synthetic prompt" not in export.text and token not in export.text
        assert client.delete("/operator/clients/synthetic_user", headers=WRITE).status_code == 204
        assert (
            client.post(
                "/operator/clients", headers=WRITE, json={"id": "synthetic_user"}
            ).status_code
            == 422
        )
        assert (
            client.get("/operator/usage", headers=READ).json()["clients"]["synthetic_user"][
                "provider_attempts"
            ]
            == 2
        )
        for invalid in (
            {"start": "2026-02-30"},
            {"start": "2026-10-02", "end": "2026-10-01"},
            {"client_id": "../secret"},
        ):
            assert client.get("/operator/usage", headers=READ, params=invalid).status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        READ,
        {**WRITE, "Origin": "https://cross-site.invalid"},
        {**WRITE, "Sec-Fetch-Site": "cross-site"},
        {**WRITE, "Sec-Fetch-Site": "same-site"},
    ],
)
def test_operator_writes_require_explicit_same_origin_client(managed, headers):
    build, _ = managed
    app, _ = build()
    with TestClient(app) as client:
        response = client.post("/operator/clients", headers=headers, json={"id": "blocked"})
        assert response.status_code == 422
        assert client.get("/operator/state", headers=READ).json()["clients"] == []


async def test_admin_authentication_precedes_reading_mutation_body(managed):
    build, _ = managed
    app, _ = build()
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/operator/clients",
        "raw_path": b"/operator/clients",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("synthetic", 1000),
    }
    sent = []

    async def receive():
        pytest.fail("Mutation body read before operator authentication")

    async def send(message):
        sent.append(message)

    async with app.router.lifespan_context(app):
        await app(scope, receive, send)
    assert (
        next(message["status"] for message in sent if message["type"] == "http.response.start")
        == 401
    )


async def test_live_policy_update_preserves_active_leases_and_unrelated_rate_budget(managed):
    build, _ = managed
    app, provider = build()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://synthetic"
        ) as client:
            response = await client.post(
                "/operator/clients",
                headers=WRITE,
                json={
                    "id": "active",
                    "models": [MODEL],
                    "limits": {"max_concurrent_requests": 1, "requests_per_minute": 1},
                },
            )
            token = response.json()["token"]
            provider.wait, provider.entered = asyncio.Event(), asyncio.Event()
            running = asyncio.create_task(
                client.post("/chat", headers=bearer(token), json=body("/chat"))
            )
            await asyncio.wait_for(provider.entered.wait(), 2)
            assert app.state.admission.active == 1
            response = await client.post(
                "/operator/clients", headers=WRITE, json={"id": "unrelated", "models": [MODEL]}
            )
            assert response.status_code == 201
            assert app.state.admission.active == 1
            assert app.state.admission._client_active["active"] == 1
            assert (
                await client.post("/chat", headers=bearer(token), json=body("/chat"))
            ).status_code == 429
            provider.wait.set()
            assert (await running).status_code == 200
            assert (
                await client.post("/chat", headers=bearer(token), json=body("/chat"))
            ).status_code == 429
            assert app.state.admission.active == 0


async def test_revoked_token_is_rechecked_after_delayed_body_delivery(managed):
    import json

    build, _ = managed
    app, provider = build()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://synthetic"
        ) as client:
            created = await client.post(
                "/operator/clients", headers=WRITE, json={"id": "delayed", "models": [MODEL]}
            )
            token = created.json()["token"]
            receiving, release = asyncio.Event(), asyncio.Event()
            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/chat",
                "raw_path": b"/chat",
                "query_string": b"",
                "headers": [
                    (b"authorization", ("Bearer " + token).encode()),
                    (b"content-type", b"application/json"),
                ],
                "server": ("synthetic", 80),
                "client": ("synthetic", 1000),
            }
            sent = []

            async def receive():
                receiving.set()
                await release.wait()
                return {
                    "type": "http.request",
                    "body": json.dumps(body("/chat")).encode(),
                    "more_body": False,
                }

            async def send(message):
                sent.append(message)

            waiting = asyncio.create_task(app(scope, receive, send))
            await asyncio.wait_for(receiving.wait(), 2)
            assert (
                await client.delete("/operator/clients/delayed/token", headers=WRITE)
            ).status_code == 204
            release.set()
            await asyncio.wait_for(waiting, 2)
            assert (
                next(
                    message["status"]
                    for message in sent
                    if message["type"] == "http.response.start"
                )
                == 401
            )
            assert provider.calls == []


def test_live_allowlist_and_additional_middleware_actually_change_provider_requests(managed):
    build, _ = managed
    app, provider = build()
    with TestClient(app) as client:
        token = create(client, models=[MODEL, "model-b"])
        payload = body("/chat")
        payload["messages"][0]["content"] = "synthetic +7 999 123-45-67"
        assert client.post("/chat", headers=bearer(token), json=payload).status_code == 200
        assert provider.calls[-1].messages[0].content == "synthetic +7 999 123-45-67"
        updated = client.put(
            "/operator/clients/synthetic_user",
            headers=WRITE,
            json={"models": [MODEL], "additional_middleware": ["phone"]},
        )
        assert updated.status_code == 200
        assert client.post("/chat", headers=bearer(token), json=payload).status_code == 200
        assert provider.calls[-1].messages[0].content == "synthetic [PHONE]"
        assert (
            client.post(
                "/chat", headers=bearer(token), json=body("/chat", model="model-b")
            ).status_code
            == 403
        )
        assert len(provider.calls) == 2


def test_operator_cannot_reuse_persisted_client_token_and_failed_start_closes_store(
    managed, monkeypatch
):
    build, _ = managed
    app, _ = build()
    with TestClient(app) as client:
        token = create(client, models=[MODEL])
    monkeypatch.setenv("ADMIN_RUNTIME_OPERATOR", token)
    app, _ = build()
    with pytest.raises(StartupError, match="must differ"):
        with TestClient(app):
            pass
    assert app.state.admin_store is None
    monkeypatch.setenv("ADMIN_RUNTIME_OPERATOR", OPERATOR)
    app, _ = build()
    with TestClient(app) as client:
        assert client.post("/chat", headers=bearer(token), json=body("/chat")).status_code == 200


def test_postgres_session_loss_stops_cached_auth_and_requires_restart(managed):
    build, config = managed
    if config.auth.management_database_url_env is None:
        pytest.skip("PostgreSQL session loss applies to the PostgreSQL backend")
    import psycopg

    app, provider = build()
    with TestClient(app) as client:
        token = create(client, models=[MODEL])
        assert client.post("/chat", headers=bearer(token), json=body("/chat")).status_code == 200
        pid = app.state.admin_store._db.info.backend_pid
        dsn = os.environ[config.auth.management_database_url_env]
        with psycopg.connect(dsn, autocommit=True) as connection:
            assert connection.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
        calls = len(provider.calls)
        for path in ("/chat", "/v1/chat/completions", "/v1/responses"):
            response = client.post(path, headers=bearer(token), json=body(path))
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "unavailable"
            assert dsn not in response.text
        assert client.get("/v1/models", headers=bearer(token)).status_code == 503
        assert client.get("/operator/state", headers=READ).status_code == 503
        assert client.get("/ready").status_code == 503
        assert len(provider.calls) == calls
    app, _ = build()
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert client.post("/chat", headers=bearer(token), json=body("/chat")).status_code == 200

"""Exercise the integrated management boundary and operational signals."""

import asyncio
import importlib
import os
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.db_execution import DBExecutor
from gateway7.errors import GatewayError, StartupError
from gateway7.metrics import Metrics
from gateway7.models import ChatResponse
from gateway7.providers import CatalogModel
from gateway7.responses_models import ResponsesResponse

ADMIN = "synthetic-integrated-operator-token"


class Provider:
    def __init__(self):
        self.calls = 0
        self.closed = False
        self.close_calls = 0

    async def complete(self, request, **options):
        self.calls += 1
        return ChatResponse(text="synthetic answer", usage={"input_tokens": 7, "output_tokens": 3})

    async def complete_early(self, request, *, on_text, **options):
        answer = await self.complete(request, **options)
        await on_text(answer.text)
        return answer

    async def complete_responses(self, request, **options):
        self.calls += 1
        return ResponsesResponse.model_validate(
            {
                "id": "resp_synthetic",
                "object": "response",
                "created_at": 1,
                "model": "model-a",
                "status": "completed",
                "output": [],
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            }
        )

    async def complete_responses_early(self, request, **options):
        return await self.complete_responses(request, **options)

    async def get_models(self, **options):
        return (CatalogModel("model-a", 0, "synthetic"),)

    async def aclose(self):
        self.close_calls += 1
        self.closed = True


@pytest.fixture(params=["sqlite", "postgres"])
def managed(monkeypatch, tmp_path, request):
    monkeypatch.setenv("OPS_ADMIN", ADMIN)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-integrated-provider-token")
    backend = {"management_db": str(tmp_path / "admin.sqlite3")}
    dsn = os.environ.get("GATEWAY7_TEST_POSTGRES_DSN")
    if request.param == "postgres":
        if not dsn:
            pytest.skip("Set GATEWAY7_TEST_POSTGRES_DSN to a disposable PostgreSQL database")
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as connection:
            assert connection.info.dbname.startswith(("gateway7_test", "gateway7_task")), (
                "A named disposable test database is required"
            )
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")
        monkeypatch.setenv("OPS_DATABASE_URL", dsn)
        backend = {"management_database_url_env": "OPS_DATABASE_URL"}
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {"enabled": True, "operator_token_env": "OPS_ADMIN", **backend},
        }
    )
    provider = Provider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    app = create_app(config=config)
    with TestClient(app) as client:
        yield app, client, provider
    if request.param == "postgres":
        with psycopg.connect(dsn, autocommit=True) as connection:
            assert connection.info.dbname.startswith(("gateway7_test", "gateway7_task"))
            connection.execute("DROP SCHEMA IF EXISTS gateway7_admin CASCADE")


def read(client, path):
    response = client.get(path, headers={"Authorization": "Bearer " + ADMIN})
    assert response.status_code == 200, response.text
    return response.json()


def write(client, path, body, *, method="POST"):
    revision = read(client, "/operator/state")["revision"]
    return client.request(
        method,
        path,
        json=body,
        headers={
            "Authorization": "Bearer " + ADMIN,
            "X-Gateway7-Operator": "true",
            "If-Match": str(revision),
        },
    )


@pytest.mark.parametrize(
    "path,stream,early",
    [
        ("/chat", False, False),
        ("/v1/chat/completions", False, False),
        ("/v1/chat/completions", True, False),
        ("/v1/chat/completions", True, True),
        ("/v1/responses", False, False),
        ("/v1/responses", True, False),
        ("/v1/responses", True, True),
    ],
)
def test_precise_accounting_and_budget_guard_all_http_shapes(managed, path, stream, early):
    app, client, provider = managed
    created = write(client, "/operator/clients", {"id": "alice", "models": ["model-a"]})
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    priced = write(
        client,
        "/operator/pricing",
        {
            "prices": [
                {
                    "model": "model-a",
                    "input_micro_usd_per_million": 1000000,
                    "output_micro_usd_per_million": 1000000,
                }
            ]
        },
        method="PUT",
    )
    assert priced.status_code == 200, priced.text
    headers = {"Authorization": "Bearer " + token}
    if early:
        headers["X-Gateway7-Stream-Mode"] = "early"
    body = (
        {"model": "model-a", "input": "synthetic prompt", "max_output_tokens": 16, "stream": stream}
        if path == "/v1/responses"
        else {
            "model": "model-a",
            "messages": [{"role": "user", "content": "synthetic prompt"}],
            "max_tokens": 16,
        }
    )
    if path != "/chat":
        body["stream"] = stream
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert provider.calls == 1
    report = read(client, "/operator/usage?client_id=alice&bucket=hour")
    assert report["summary"]["provider_attempts"] == 1
    assert report["summary"]["known_input_tokens"] == 7
    assert report["summary"]["known_output_tokens"] == 3
    assert report["summary"]["cost_micro_usd"] == 10
    denied = write(
        client,
        "/operator/budgets",
        {
            "rules": [
                {
                    "id": "daily",
                    "client_id": "alice",
                    "model": None,
                    "period": "day",
                    "tokens": 1,
                    "micro_usd": None,
                    "mode": "hard",
                    "enabled": True,
                }
            ]
        },
        method="PUT",
    )
    assert denied.status_code == 200, denied.text
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert provider.calls == 1
    diagnostics = read(client, "/operator/diagnostics?client_id=alice")
    assert diagnostics["http_outcomes"]["budget_exceeded"] == 1
    assert read(client, "/operator/usage?client_id=alice")["summary"]["provider_attempts"] == 1


def test_readiness_signal_detects_database_loss_while_scrape_remains_available(
    managed, monkeypatch
):
    app, client, provider = managed

    def unavailable():
        raise StartupError("synthetic unavailable")

    monkeypatch.setattr(app.state.admin_store, "ensure_available", unavailable)
    assert client.get("/ready").status_code == 503
    scrape = client.get("/metrics")
    assert scrape.status_code == 200
    assert "gateway7_ready 0.0" in scrape.text
    assert "gateway7_management_database_available 0.0" in scrape.text
    assert (
        client.get("/operator/state", headers={"Authorization": "Bearer " + ADMIN}).status_code
        == 503
    )
    assert provider.calls == 0


async def test_database_executor_keeps_loop_responsive_and_does_not_abandon_running_write():
    db = DBExecutor(capacity=1)
    entered, release, committed = threading.Event(), threading.Event(), threading.Event()

    def operation():
        entered.set()
        release.wait(3)
        committed.set()

    running = asyncio.create_task(db.call(operation))
    for _ in range(100):
        if entered.is_set():
            break
        await asyncio.sleep(0.001)
    assert entered.is_set()
    with pytest.raises(GatewayError) as overloaded:
        await db.call(lambda: None)
    assert overloaded.value.code == "overloaded"
    running.cancel()
    await asyncio.sleep(0.01)
    assert not running.done() and not committed.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert committed.is_set()
    await db.close()


def test_partial_token_observation_preserves_known_direction():
    metrics = Metrics()
    metrics.observe_provider("fake", "provider_error", 0.1, {"input_tokens": 7})
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_tokens_total", {"provider": "fake", "direction": "input"}
        )
        == 7
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_tokens_total", {"provider": "fake", "direction": "output"}
        )
        is None
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_usage_unknown_total", {"provider": "fake"}
        )
        == 1
    )


async def test_cancelled_management_http_caller_cannot_leave_commit_unpublished(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OPS_ADMIN", ADMIN)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-integrated-provider-token")
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {
                "enabled": True,
                "operator_token_env": "OPS_ADMIN",
                "management_db": str(tmp_path / "admin.sqlite3"),
            },
        }
    )
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: Provider()
    )
    app = create_app(config=config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://gateway.test"
        ) as client:
            auth = {"Authorization": "Bearer " + ADMIN}
            revision = (await client.get("/operator/state", headers=auth)).json()["revision"]
            entered, release = threading.Event(), threading.Event()
            original = app.state.admin_store.write_control

            def blocked(*args, **kwargs):
                entered.set()
                release.wait(3)
                return original(*args, **kwargs)

            monkeypatch.setattr(app.state.admin_store, "write_control", blocked)
            request = asyncio.create_task(
                client.post(
                    "/operator/clients",
                    json={"id": "committed"},
                    headers={**auth, "If-Match": str(revision), "X-Gateway7-Operator": "true"},
                )
            )
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.001)
            assert entered.is_set()
            request.cancel()
            await asyncio.sleep(0.01)
            assert not request.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await request
            snapshot = (await client.get("/operator/state", headers=auth)).json()
            assert snapshot["revision"] == revision + 1
            assert snapshot["clients"][0]["id"] == "committed"
            stored, _ = await app.state.db.call(app.state.admin_store.load_clients)
            assert set(stored) == set(app.state.config.auth.clients) == {"committed"}


async def test_provider_swap_drains_captured_request_before_closing_old_adapter(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OPS_ADMIN", ADMIN)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-integrated-provider-token")
    entered, release = asyncio.Event(), asyncio.Event()
    old, new = Provider(), Provider()
    original = old.complete

    async def waiting(request, **options):
        entered.set()
        await release.wait()
        return await original(request, **options)

    old.complete = waiting
    monkeypatch.setattr(importlib.import_module("gateway7.app"), "build_provider", lambda *_: old)
    monkeypatch.setattr(
        importlib.import_module("gateway7.provider_admin"),
        "build_provider",
        lambda *_args, **_kwargs: new,
    )
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {
                "enabled": True,
                "operator_token_env": "OPS_ADMIN",
                "management_db": str(tmp_path / "admin.sqlite3"),
            },
        }
    )
    app = create_app(config=config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://gateway.test"
        ) as client:
            auth = {"Authorization": "Bearer " + ADMIN}

            async def change(path, data, method="POST"):
                revision = (await client.get("/operator/state", headers=auth)).json()["revision"]
                return await client.request(
                    method,
                    path,
                    json=data,
                    headers={**auth, "If-Match": str(revision), "X-Gateway7-Operator": "true"},
                )

            created = await change("/operator/clients", {"id": "alice", "models": ["model-a"]})
            token = created.json()["token"]
            body = {
                "model": "model-a",
                "messages": [{"role": "user", "content": "synthetic"}],
                "max_tokens": 16,
            }
            ongoing = asyncio.create_task(
                client.post("/chat", json=body, headers={"Authorization": "Bearer " + token})
            )
            await asyncio.wait_for(entered.wait(), 2)
            changed = await change(
                "/operator/provider",
                {
                    "kind": "openai",
                    "model": "model-a",
                    "base_url": "https://api.openai.com",
                    "allowed_models": ["model-a"],
                },
                "PUT",
            )
            assert changed.status_code == 200, changed.text
            assert not old.closed
            release.set()
            assert (await ongoing).status_code == 200
            for _ in range(100):
                if old.closed:
                    break
                await asyncio.sleep(0.01)
            assert old.closed and not new.closed
            assert (
                await client.post("/chat", json=body, headers={"Authorization": "Bearer " + token})
            ).status_code == 200
            assert old.calls == new.calls == 1
    assert old.close_calls == new.close_calls == 1


async def test_provider_default_is_captured_after_management_await(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ADMIN", ADMIN)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-integrated-provider-token")
    app_module = importlib.import_module("gateway7.app")

    class TrackingProvider(Provider):
        def __init__(self, default):
            super().__init__()
            self.default = default

        async def complete(self, request, **options):
            self.calls += 1
            return ChatResponse(
                text=options.get("model", self.default),
                usage={"input_tokens": 7, "output_tokens": 3},
            )

    old = TrackingProvider("model-a")
    monkeypatch.setattr(app_module, "build_provider", lambda *_: old)
    monkeypatch.setattr(
        importlib.import_module("gateway7.provider_admin"),
        "build_provider",
        lambda config, *_args, **_kwargs: TrackingProvider(config.model),
    )
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {
                "enabled": True,
                "operator_token_env": "OPS_ADMIN",
                "management_db": str(tmp_path / "admin.sqlite3"),
            },
        }
    )
    app = create_app(config=config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://gateway.test"
        ) as client:
            auth = {"Authorization": "Bearer " + ADMIN}

            async def change(path, data, method="POST"):
                revision = (await client.get("/operator/state", headers=auth)).json()["revision"]
                return await client.request(
                    method,
                    path,
                    json=data,
                    headers={**auth, "If-Match": str(revision), "X-Gateway7-Operator": "true"},
                )

            created = await change(
                "/operator/clients", {"id": "alice", "models": ["model-a", "model-b"]}
            )
            gate, release = asyncio.Event(), asyncio.Event()
            ensure = app_module._ensure_management_available
            count = 0

            async def delayed(owner):
                nonlocal count
                if asyncio.current_task().get_name() == "waiting-chat":
                    count += 1
                    if count == 2:
                        gate.set()
                        await release.wait()
                await ensure(owner)

            monkeypatch.setattr(app_module, "_ensure_management_available", delayed)
            request = asyncio.create_task(
                client.post(
                    "/chat",
                    headers={"Authorization": "Bearer " + created.json()["token"]},
                    json={"messages": [{"role": "user", "content": "synthetic"}], "max_tokens": 16},
                ),
                name="waiting-chat",
            )
            await asyncio.wait_for(gate.wait(), 2)
            changed = await change(
                "/operator/provider",
                {
                    "kind": "openai",
                    "model": "model-b",
                    "base_url": "https://api.openai.com",
                    "allowed_models": ["model-a", "model-b"],
                },
                "PUT",
            )
            assert changed.status_code == 200, changed.text
            release.set()
            result = await request
            assert result.status_code == 200 and result.json()["text"] == "model-b"


async def test_analytics_transport_failures_are_distinct_from_disabled_export(monkeypatch):
    from gateway7.analytics import Analytics

    metrics = Metrics()
    statuses = iter((503, 202))

    async def backend(request):
        return httpx.Response(next(statuses))

    analytics = Analytics.from_environment(
        {
            "ANALYTICS_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "staging",
            "OPENPANEL_API_URL": "http://synthetic.invalid",
            "OPENPANEL_CLIENT_ID": "synthetic-id",
            "OPENPANEL_CLIENT_SECRET": "synthetic-secret",
        },
        metrics=metrics,
        transport=httpx.MockTransport(backend),
    )
    await analytics.start()
    try:
        analytics.started(request_id="a" * 32, route="chat")
        await asyncio.wait_for(analytics._queue.join(), 1)
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_enabled", {"exporter": "analytics"}
            )
            == 1
        )
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_events_total", {"exporter": "analytics", "outcome": "failure"}
            )
            == 1
        )
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_last_success_timestamp_seconds", {"exporter": "analytics"}
            )
            == 0
        )
        analytics.completed(request_id="a" * 32, route="chat", status=200, duration_ms=1)
        await asyncio.wait_for(analytics._queue.join(), 1)
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_events_total", {"exporter": "analytics", "outcome": "success"}
            )
            == 1
        )
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_last_success_timestamp_seconds", {"exporter": "analytics"}
            )
            > 0
        )
        assert metrics.registry.get_sample_value("gateway7_analytics_queue_depth") == 0
    finally:
        await analytics.shutdown()


def test_otel_sdk_delivery_results_reach_operational_metrics(monkeypatch):
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
    from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
    from gateway7.telemetry import Telemetry

    class FailureExporter(MetricExporter):
        def export(self, data, timeout_millis=10000, **kwargs):
            return MetricExportResult.FAILURE

        def force_flush(self, timeout_millis=10000):
            return True

        def shutdown(self, timeout_millis=30000, **kwargs):
            return None

    logs = InMemoryLogRecordExporter()
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter",
        lambda **kwargs: logs,
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter",
        lambda **kwargs: FailureExporter(),
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://synthetic.invalid")
    metrics = Metrics()
    telemetry = Telemetry.from_environment(
        {
            "TELEMETRY_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "staging",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://synthetic.invalid",
            "OTEL_METRIC_EXPORT_INTERVAL": "100000",
        },
        metrics=metrics,
    )
    try:
        telemetry.record(
            request_id="a" * 32, route="chat", status=200, error_code=None, duration_ms=1
        )
        telemetry._logger_provider.force_flush()
        telemetry._meter_provider.force_flush()
        assert len(logs.get_finished_logs()) == 1
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_events_total",
                {"exporter": "telemetry_logs", "outcome": "success"},
            )
            >= 1
        )
        assert (
            metrics.registry.get_sample_value(
                "gateway7_exporter_events_total",
                {"exporter": "telemetry_metrics", "outcome": "failure"},
            )
            >= 1
        )
    finally:
        telemetry.shutdown()


@pytest.mark.parametrize(
    "seed_kind,seed_model,target_kind,target_model",
    [
        ("fake", "fake", "openai", "org/model:1"),
        ("openai", "org/model:seed", "fake", "fake"),
    ],
)
def test_restart_validates_authoritative_provider_and_clients_together(
    monkeypatch, tmp_path, seed_kind, seed_model, target_kind, target_model
):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("OPS_ADMIN", ADMIN)
    monkeypatch.setenv("OPS_PROVIDER", "synthetic-bootstrap-provider-token")
    monkeypatch.setenv("OPS_SEED", "synthetic-bootstrap-client-token")
    monkeypatch.setenv("GATEWAY7_CONTROL_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"),
        "build_provider",
        lambda *_args, **_kwargs: Provider(),
    )
    monkeypatch.setattr(
        importlib.import_module("gateway7.provider_admin"),
        "build_provider",
        lambda *_args, **_kwargs: Provider(),
    )
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": seed_kind, "model": seed_model, "key_env": "OPS_PROVIDER"},
            "auth": {
                "enabled": True,
                "operator_token_env": "OPS_ADMIN",
                "management_db": str(tmp_path / "admin.sqlite3"),
                "clients": {"seed": {"token_env": "OPS_SEED", "models": [seed_model]}},
            },
        }
    )
    with TestClient(create_app(config=config)) as client:
        assert write(client, "/operator/clients/seed", None, method="DELETE").status_code == 204
        changed = write(
            client,
            "/operator/provider",
            {
                "kind": target_kind,
                "model": target_model,
                "base_url": "https://api.openai.com"
                if target_kind == "openai"
                else "http://127.0.0.1:8001",
                "allowed_models": [target_model],
                "credential": "synthetic-managed-provider-token",
            },
            method="PUT",
        )
        assert changed.status_code == 200, changed.text
        created = write(client, "/operator/clients", {"id": "live_user", "models": [target_model]})
        assert created.status_code == 201, created.text
        token = created.json()["token"]
    monkeypatch.delenv("OPS_PROVIDER")
    monkeypatch.delenv("OPS_SEED")
    restarted = create_app(config=config)
    with TestClient(restarted) as client:
        assert restarted.state.config.provider.kind == target_kind
        assert set(restarted.state.config.auth.clients) == {"live_user"}
        models = client.get("/v1/models", headers={"Authorization": "Bearer " + token})
        assert models.status_code == 200
        assert models.json()["data"][0]["id"] == target_model

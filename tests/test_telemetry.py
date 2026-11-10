"""The exported request signal carries one safe point per API request and stays off by default."""

import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.models import ChatResponse
from gateway7.telemetry import DURATION_METRIC, Telemetry, outcome_for

TOKEN = "gateway7-synthetic-telemetry-client"
SECRET_TEXT = "synthetic-private-prompt-value"


class Provider:
    async def complete(self, request, *, model=None):
        await asyncio.sleep(0)
        return ChatResponse(
            text="answer " + SECRET_TEXT, usage={"input_tokens": 3, "output_tokens": 2}
        )

    async def aclose(self):
        pass


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", "gateway7-synthetic-provider-secret")
    monkeypatch.setenv("CLIENT_TELEMETRY", TOKEN)
    app_module = importlib.import_module("gateway7.app")
    monkeypatch.setattr(app_module, "build_provider", lambda *_: Provider())
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "model": "model-a"},
            "auth": {
                "enabled": True,
                "clients": {
                    "telemetry": {"token_env": "CLIENT_TELEMETRY", "models": ["model-a"]},
                },
            },
        }
    )
    logs = InMemoryLogRecordExporter()
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(logs))
    reader = InMemoryMetricReader()
    telemetry = Telemetry(
        logger_provider=logger_provider,
        meter_provider=MeterProvider(metric_readers=[reader]),
        environment="staging",
    )
    return create_app(config=config, telemetry=telemetry), logs, reader


def histogram_points(reader):
    data = reader.get_metrics_data()
    points = []
    for resource in data.resource_metrics if data else ():
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name == DURATION_METRIC:
                    assert metric.unit == "ms"
                    points.extend(metric.data.data_points)
    return points


def test_each_api_request_exports_one_safe_log_point_and_histogram_observation(gateway):
    app, logs, reader = gateway
    headers = {"Authorization": "Bearer " + TOKEN}
    body = {"messages": [{"role": "user", "content": SECRET_TEXT}]}
    with TestClient(app) as client:
        ok = client.post("/v1/chat/completions", headers=headers, json={"model": "model-a", **body})
        failed = client.post(
            "/v1/chat/completions", headers=headers, json={"model": "not-allowed", **body}
        )
        unauthorized = client.post("/chat", json=body)
        for path in ("/health", "/ready", "/metrics"):
            assert client.get(path).status_code == 200
    assert (ok.status_code, failed.status_code, unauthorized.status_code) == (200, 403, 401)

    records = [item.log_record for item in logs.get_finished_logs()]
    assert len(records) == 3
    by_id = {record.attributes["request_id"]: record for record in records}
    expected = {
        ok.headers["x-request-id"]: ("openai_chat", "ok", 200, "none"),
        failed.headers["x-request-id"]: ("openai_chat", "client_error", 403, "model_forbidden"),
        unauthorized.headers["x-request-id"]: ("chat", "client_error", 401, "unauthorized"),
    }
    assert set(by_id) == set(expected)
    for request_id, (route, outcome, status, error_code) in expected.items():
        record = by_id[request_id]
        attributes = dict(record.attributes)
        assert set(attributes) == {
            "request_id",
            "route",
            "outcome",
            "status",
            "error_code",
            "duration_ms",
        }
        assert (attributes["route"], attributes["outcome"]) == (route, outcome)
        assert (attributes["status"], attributes["error_code"]) == (status, error_code)
        assert attributes["duration_ms"] >= 0
        assert record.body == "gateway request"
        assert record.severity_text == ("INFO" if outcome == "ok" else "WARN")
        exported = repr(attributes) + repr(record.body)
        assert SECRET_TEXT not in exported and TOKEN not in exported and "model-a" not in exported

    points = {
        (point.attributes["route"], point.attributes["outcome"]): point
        for point in histogram_points(reader)
    }
    assert set(points) == {
        ("openai_chat", "ok"),
        ("openai_chat", "client_error"),
        ("chat", "client_error"),
    }
    assert all(
        point.count == 1 and set(point.attributes) == {"route", "outcome"}
        for point in points.values()
    )
    failed_duration = by_id[failed.headers["x-request-id"]].attributes["duration_ms"]
    assert points[("openai_chat", "client_error")].sum == pytest.approx(failed_duration, abs=0.001)


def test_telemetry_is_disabled_until_explicitly_enabled():
    for environ in ({}, {"TELEMETRY_ENABLED": "false"}, {"TELEMETRY_ENABLED": "0"}):
        telemetry = Telemetry.from_environment(environ)
        assert not telemetry.enabled
        telemetry.record(request_id="x", route="chat", status=500, error_code=None, duration_ms=1)
        telemetry.shutdown()


@pytest.mark.parametrize(
    "environ",
    [
        {"TELEMETRY_ENABLED": "sometimes"},
        {"TELEMETRY_ENABLED": "true"},
        {
            "TELEMETRY_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "development",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9/api/staging",
        },
        {"TELEMETRY_ENABLED": "true", "GATEWAY7_ENVIRONMENT": "staging"},
        {
            "TELEMETRY_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "staging",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9/api/staging",
            "OTEL_METRIC_EXPORT_INTERVAL": "soon",
        },
    ],
    ids=["switch", "environment", "unknown-environment", "endpoint", "interval"],
)
def test_incomplete_telemetry_configuration_stops_startup(environ):
    with pytest.raises(StartupError):
        Telemetry.from_environment(environ)


def test_enabled_configuration_builds_exporters_without_contacting_the_backend():
    telemetry = Telemetry.from_environment(
        {
            "TELEMETRY_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "production",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9/api/production",
        }
    )
    assert telemetry.enabled and telemetry.environment == "production"
    telemetry.shutdown()
    assert not telemetry.enabled


def test_outcome_labels_are_a_fixed_set():
    assert [outcome_for(status) for status in (200, 304, 401, 499, 502)] == [
        "ok",
        "ok",
        "client_error",
        "cancelled",
        "server_error",
    ]


def load_check_sli():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "check_sli.py"
    spec = importlib.util.spec_from_file_location("check_sli", path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stored", [True, False], ids=["stored", "missing"])
def test_diagnosability_check_reads_the_failed_requests_point_and_series(
    monkeypatch, capsys, stored
):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    check_sli = load_check_sli()
    monkeypatch.setattr(check_sli, "LOG_LIMIT_SECONDS", 0.2)
    monkeypatch.setattr(check_sli, "SLI_LIMIT_SECONDS", 0.2)
    failed_id = "f" * 32
    seen = {"sql": [], "promql": [], "auth": set(), "counts": 0, "successful_posts": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, headers=()):
            data = json.dumps(body).encode()
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/ready":
                return self.reply(200, {"status": "ready"})
            if url.path == "/v1/models":
                if not self.headers.get("Authorization"):
                    return self.reply(401, {"error": {"code": "unauthorized"}})
                return self.reply(200, {"data": [{"id": "model-a"}]})
            seen["auth"].add(self.headers["Authorization"])
            seen["promql"].append(parse_qs(url.query)["query"][0])
            result = [
                {
                    "metric": {"route": "openai_chat", "outcome": "client_error"},
                    "value": [0, "4.75" if stored else "NaN"],
                }
            ]
            if seen["promql"][-1] == check_sli.COUNT_QUERY:
                seen["counts"] += 1
                result = [{"metric": {}, "value": [0, str(min(seen["counts"] - 1, 1))]}]
            return self.reply(
                200, {"status": "success", "data": {"resultType": "vector", "result": result}}
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/v1/chat/completions":
                if body["model"] == "model-a":
                    seen["successful_posts"] += 1
                    return self.reply(200, {"choices": []}, [("X-Request-ID", "a" * 32)])
                return self.reply(
                    403,
                    {"request_id": failed_id, "error": {"code": "model_forbidden"}},
                    [("X-Request-ID", failed_id)],
                )
            seen["auth"].add(self.headers["Authorization"])
            seen["sql"].append(body["query"]["sql"])
            hits = [
                {
                    "request_id": failed_id,
                    "route": "openai_chat",
                    "outcome": "client_error",
                    "status": 403,
                    "error_code": "model_forbidden",
                    "duration_ms": 0.5,
                }
            ]
            return self.reply(200, {"hits": hits if stored else []})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    address = f"http://127.0.0.1:{server.server_address[1]}"
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("GATEWAY7_ENVIRONMENT", "staging")
    monkeypatch.setenv("GATEWAY7_CLIENT_TOKEN", TOKEN)
    monkeypatch.setenv("OPENOBSERVE_USER", "synthetic-reader")
    monkeypatch.setenv("OPENOBSERVE_TOKEN", "synthetic-reader-secret")
    try:
        code = check_sli.main(
            ["--gateway", address, "--observe", address, "--confirm-staging", "--commit", "a" * 40]
        )
    finally:
        server.shutdown()
    output = capsys.readouterr().out

    assert code == (0 if stored else 1)
    assert output.splitlines()[-1] == ("PASS QR-05 QRT-01" if stored else "FAIL QR-05 QRT-01")
    assert f"WHERE request_id = '{failed_id}'" in seen["sql"][0]
    assert seen["promql"][0] == check_sli.COUNT_QUERY
    if stored:
        assert check_sli.SLI_QUERY in seen["promql"]
    assert seen["successful_posts"] == 0
    assert len(seen["auth"]) == 1 and next(iter(seen["auth"])).startswith("Basic ")
    for private in (address, TOKEN, "synthetic-reader-secret"):
        assert private not in output


def test_tracked_dashboard_runs_the_sli_query_the_observability_plan_records():
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    plan = (root / "docs" / "observability.md").read_text(encoding="utf-8")
    recorded = re.search(r"^- \*\*Query:\*\* `(.+)`$", plan.split("### SLI-01", 1)[1], re.M)
    dashboard = json.loads(
        (root / "monitoring" / "openobserve" / "gateway7-sli-dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    panels = [panel for tab in dashboard["tabs"] for panel in tab["panels"]]
    assert [panel["title"] for panel in panels] == ["SLI-01 API request P95 by outcome"]
    assert [query["query"] for query in panels[0]["queries"]] == [recorded.group(1)]
    assert recorded.group(1) == load_check_sli().SLI_QUERY
    text = json.dumps(dashboard)
    assert "http" not in text and "@" not in text and "Authorization" not in text

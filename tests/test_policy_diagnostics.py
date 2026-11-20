"""US-04 exposes only the runner-owned instance and bounded action identifiers."""

import importlib
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway7.app import create_app
from gateway7.analytics import Analytics
from gateway7.cli import main
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError, StartupError
from gateway7.loader import load_plugins
from gateway7.models import ChatResponse
from gateway7.openai_api import error_body

SECRET = "synthetic-private-policy-message"


@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions"])
def test_policy_metadata_preserves_exported_failure_code(monkeypatch, path):
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    from gateway7.telemetry import Telemetry

    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-provider-key")
    provider = Provider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    logs = InMemoryLogRecordExporter()
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(logs))
    telemetry = Telemetry(
        logger_provider=logger_provider,
        meter_provider=MeterProvider(metric_readers=[InMemoryMetricReader()]),
        environment="staging",
    )
    events = []

    def collect(request):
        events.append(json.loads(request.content)["payload"])
        return httpx.Response(200)

    analytics = Analytics.from_environment(
        {
            "ANALYTICS_ENABLED": "true",
            "GATEWAY7_ENVIRONMENT": "staging",
            "ANALYTICS_SOURCE": "smoke",
            "OPENPANEL_API_URL": "http://analytics.invalid/api",
            "OPENPANEL_CLIENT_ID": "synthetic-policy-analytics-client",
            "OPENPANEL_CLIENT_SECRET": "synthetic-policy-analytics-secret",
        },
        transport=httpx.MockTransport(collect),
    )
    config = GatewayConfig.model_validate(
        {
            "plugins": {
                "company-policy": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": [SECRET], "action": "block"},
                }
            },
            "middleware": ["company-policy"],
        }
    )
    with TestClient(create_app(config=config, telemetry=telemetry, analytics=analytics)) as client:
        response = client.post(
            path, json={"model": "fake", "messages": [{"role": "user", "content": SECRET}]}
        )
    assert response.status_code == 403
    assert response.json()["error"]["middleware"] == "company-policy"
    records = [item.log_record for item in logs.get_finished_logs()]
    assert len(records) == 1
    attributes = dict(records[0].attributes)
    assert attributes["request_id"] == response.headers["x-request-id"]
    assert attributes["error_code"] == "policy_denied"
    assert attributes["outcome"] == "client_error" and attributes["status"] == 403
    assert set(attributes) == {
        "request_id",
        "route",
        "outcome",
        "status",
        "error_code",
        "duration_ms",
    }
    assert SECRET not in repr(attributes) and not provider.requests
    assert [event["name"] for event in events] == ["chat_started", "chat_completed"]
    completion = events[1]["properties"]
    assert completion["request_id"] == response.headers["x-request-id"]
    assert completion["status"] == 403 and completion["outcome"] == "client_error"
    assert "middleware" not in completion
    assert SECRET not in json.dumps(events) and "company-policy" not in json.dumps(events)


class Provider:
    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ChatResponse(text="synthetic answer")

    async def aclose(self):
        pass


@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions"])
@pytest.mark.parametrize("action,status", [("block", 403), ("log", 200)])
def test_block_names_inner_instance_and_log_forwards_unchanged(
    monkeypatch, caplog, path, action, status
):
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-provider-key")
    provider = Provider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    config = GatewayConfig.model_validate(
        {
            "plugins": {
                "outer": {"module": "gateway7.plugins.phone_mask"},
                "company-policy": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": ["BLOCK-ME-TEST"], "action": action, "phase": "request"},
                },
            },
            "middleware": ["outer", "company-policy"],
        }
    )
    message = "BLOCK-ME-TEST " + SECRET
    with (
        caplog.at_level(logging.INFO, logger="gateway7"),
        TestClient(create_app(config=config)) as client,
    ):
        response = client.post(
            path,
            json={
                "model": "fake",
                "messages": [{"role": "user", "content": message}],
            },
        )
    assert response.status_code == status
    if action == "block":
        assert response.json()["error"]["code"] == "policy_denied"
        assert response.json()["error"]["middleware"] == "company-policy"
        assert response.json()["request_id"] == response.headers["x-request-id"]
        assert not provider.requests
        assert SECRET not in response.text
    else:
        assert len(provider.requests) == 1
        assert provider.requests[0].messages[0].content == message
    entries = [r.getMessage() for r in caplog.records if "outcome=policy_match" in r.getMessage()]
    assert len(entries) == 1
    assert f"component=company-policy phase=request action={action}" in entries[0]
    assert SECRET not in caplog.text and "BLOCK-ME-TEST" not in caplog.text


@pytest.mark.parametrize("action", ["explode", "unsupported-action", "another_action"])
def test_startup_names_only_bounded_unsupported_action_and_instance(
    action, tmp_path, capsys, monkeypatch
):
    path = tmp_path / "invalid-policy.yaml"
    path.write_text(
        "plugins:\n  company-policy:\n    module: gateway7.plugins.content_policy\n"
        f"    settings:\n      terms: ['{SECRET}']\n      action: {action}\n"
        "middleware: [company-policy]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-provider-key")
    monkeypatch.setattr(
        "gateway7.cli.uvicorn.Server.serve", lambda *_: pytest.fail("Must not start serving")
    )
    assert main(["serve", "--config", str(path)]) == 1
    output = capsys.readouterr().err
    assert (
        f"Unsupported content policy action {action} for plugin instance company-policy" in output
    )
    assert SECRET not in output and "Traceback" not in output


@pytest.mark.parametrize(
    "action", ["private value", "private\nvalue", "x" * 33, 42, {}, ["private"]]
)
def test_malformed_action_values_stay_redacted(action):
    config = GatewayConfig.model_validate(
        {
            "plugins": {
                "guard": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": [SECRET], "action": action},
                }
            },
            "middleware": ["guard"],
        }
    )
    with pytest.raises(StartupError, match="^Invalid settings for plugin instance guard$"):
        load_plugins(config)


@pytest.mark.parametrize("value", [SECRET + " private", "x" * 65, 42, {}, ["guard"], None])
def test_error_metadata_rejects_arbitrary_values_and_other_error_codes(value):
    error = GatewayError("policy_denied", middleware=value)
    assert "middleware" not in error.body("opaque")["error"]
    assert "middleware" not in error_body(error, "opaque")["error"]
    assert (
        "middleware"
        not in GatewayError("provider_error", middleware="guard").body("opaque")["error"]
    )


def test_merged_early_chat_request_denial_keeps_instance_metadata(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-merge-provider-key")
    monkeypatch.setenv("MERGE_POLICY_TOKEN", "synthetic-merge-policy-client-token")

    class UnusedProvider(Provider):
        async def complete_early(self, *args, **kwargs):
            pytest.fail("Denied request must not reach the provider")

    provider = UnusedProvider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "openai", "model": "model-a"},
            "auth": {
                "enabled": True,
                "clients": {
                    "test": {
                        "token_env": "MERGE_POLICY_TOKEN",
                        "models": ["model-a"],
                    }
                },
            },
            "plugins": {
                "company-policy": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": [SECRET], "phase": "request"},
                }
            },
            "middleware": ["company-policy"],
        }
    )
    body = {"model": "model-a", "stream": True, "messages": [{"role": "user", "content": SECRET}]}
    with TestClient(create_app(config=config)) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer synthetic-merge-policy-client-token",
                "X-Gateway7-Stream-Mode": "early",
            },
            json=body,
        )
    assert response.status_code == 403
    assert response.json()["error"]["middleware"] == "company-policy"
    assert response.json()["error"]["code"] == "policy_denied"
    assert not provider.requests and SECRET not in response.text

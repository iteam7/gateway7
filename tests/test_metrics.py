"""Metrics describe attempts and owned work without exposing request content."""

import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient

from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import GatewayError
from gateway7.loader import load_plugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline

SECRET = "synthetic-private-metric-value"


class Provider:
    def __init__(self, *, usage=None, fail=False, delay=0.0):
        self.usage = usage
        self.fail = fail
        self.delay = delay

    async def complete(self, request):
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError(SECRET)
        return ChatResponse(text="SECRET-TEST " + SECRET, usage=self.usage)

    async def aclose(self):
        pass


def policy_config(action="block", phase="request"):
    return GatewayConfig.model_validate({
        "plugins": {"guard": {"module": "gateway7.plugins.content_policy", "settings": {
            "terms": ["SECRET-TEST"], "action": action, "phase": phase,
        }}},
        "middleware": ["guard"],
    })


def sample(metrics, name, **labels):
    return metrics.registry.get_sample_value("gateway7_" + name, labels)


async def test_request_denial_does_not_count_provider_or_tokens():
    config = policy_config()
    metrics = Metrics()
    pipeline = Pipeline(load_plugins(config), Provider(), config.limits, metrics=metrics)
    with pytest.raises(GatewayError, match="denied"):
        await pipeline.run(ChatRequest(messages=[Message(role="user", content="SECRET-TEST")]), "request-private")
    assert sample(metrics, "provider_calls_total", provider="fake", outcome="complete") is None
    assert sample(metrics, "middleware_steps_total", middleware="guard", phase="request", outcome="policy_denied") == 1


async def test_response_denial_still_records_provider_usage_once():
    config = policy_config(phase="response")
    metrics = Metrics()
    provider = Provider(usage={"input_tokens": 12, "output_tokens": 4}, delay=0.03)
    pipeline = Pipeline(load_plugins(config), provider, config.limits, metrics=metrics)
    with pytest.raises(GatewayError, match="denied"):
        await pipeline.run(ChatRequest(messages=[Message(role="user", content="hello")]), "request-private")
    assert sample(metrics, "provider_calls_total", provider="fake", outcome="complete") == 1
    assert sample(metrics, "provider_tokens_total", provider="fake", direction="input") == 12
    assert sample(metrics, "provider_tokens_total", provider="fake", direction="output") == 4
    assert sample(metrics, "provider_usage_unknown_total", provider="fake") is None
    assert sample(metrics, "middleware_steps_total", middleware="guard", phase="request", outcome="continue") == 1
    assert sample(metrics, "middleware_steps_total", middleware="guard", phase="response", outcome="policy_denied") == 1
    provider_duration = sample(metrics, "provider_duration_seconds_sum", provider="fake", outcome="complete")
    own_duration = sum(sample(metrics, "middleware_duration_seconds_sum", middleware="guard", phase=phase) for phase in ("request", "response"))
    assert own_duration < provider_duration


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": -1, "output_tokens": 2}, {"input_tokens": True, "output_tokens": 2}, {"input_tokens": 10**400, "output_tokens": 2}])
def test_unknown_usage_never_creates_zero_token_measurement(usage):
    metrics = Metrics()
    metrics.observe_provider("fake", "complete", 0.1, usage)
    assert sample(metrics, "provider_usage_unknown_total", provider="fake") == 1
    assert sample(metrics, "provider_tokens_total", provider="fake", direction="input") is None


async def test_provider_error_is_counted_once_and_not_as_own_policy_failure():
    config = policy_config()
    metrics = Metrics()
    pipeline = Pipeline(load_plugins(config), Provider(fail=True), config.limits, metrics=metrics)
    with pytest.raises(GatewayError):
        await pipeline.run(ChatRequest(messages=[Message(role="user", content="hello")]), "request-private")
    assert sample(metrics, "provider_calls_total", provider="fake", outcome="provider_error") == 1
    assert sample(metrics, "provider_usage_unknown_total", provider="fake") == 1
    assert sample(metrics, "middleware_steps_total", middleware="guard", phase="response", outcome="downstream_error") == 1
    assert sample(metrics, "middleware_steps_total", middleware="guard", phase="request", outcome="continue") == 1


async def test_cancelled_provider_attempt_has_unknown_usage():
    started = asyncio.Event()

    class WaitingProvider(Provider):
        async def complete(self, request):
            started.set()
            await asyncio.Event().wait()

    config = GatewayConfig()
    metrics = Metrics()
    pipeline = Pipeline(load_plugins(config), WaitingProvider(), config.limits, metrics=metrics)
    task = asyncio.create_task(pipeline.run(ChatRequest(messages=[Message(role="user", content="hello")]), "request-private"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sample(metrics, "provider_calls_total", provider="fake", outcome="cancelled") == 1
    assert sample(metrics, "provider_usage_unknown_total", provider="fake") == 1


def test_health_readiness_and_metrics_without_lifespan():
    app = create_app()
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/metrics").status_code == 200
    assert client.post("/chat", json={"messages": [{"role": "user", "content": "hello"}]}).status_code == 503
    assert sample(app.state.metrics, "http_requests_in_flight") == 0


async def test_invalid_next_payload_is_own_middleware_failure(monkeypatch):
    from gateway7.plugins.phone_mask import PhoneMaskPlugin

    async def invalid_next(self, request, context, call_next):
        return await call_next(request.model_copy(update={"max_tokens": "invalid"}))

    monkeypatch.setattr(PhoneMaskPlugin, "handle", invalid_next)
    config = GatewayConfig.model_validate({
        "plugins": {"phone": {"module": "gateway7.plugins.phone_mask"}},
        "middleware": ["phone"],
    })
    metrics = Metrics()
    pipeline = Pipeline(load_plugins(config), Provider(), config.limits, metrics=metrics)
    with pytest.raises(GatewayError):
        await pipeline.run(ChatRequest(messages=[Message(role="user", content="hello")]), "request-private")
    assert sample(metrics, "middleware_steps_total", middleware="phone", phase="request", outcome="plugin_error") == 1
    assert sample(metrics, "provider_calls_total", provider="fake", outcome="complete") is None


def test_http_metrics_fixed_route_labels_and_app_registry_isolation(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-only")
    app_module = importlib.import_module("gateway7.app")
    monkeypatch.setattr(app_module, "build_provider", lambda *_: Provider(usage={"input_tokens": 12, "output_tokens": 4}))
    app = create_app(config=GatewayConfig())
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        response = client.post("/chat", json={"messages": [{"role": "user", "content": SECRET}]})
        assert response.status_code == 200
        assert client.get("/arbitrary-" + SECRET + "?token=" + SECRET).status_code == 404
        assert client.post("/chat", json={"invalid": SECRET}).status_code == 422
        report = client.get("/metrics")
        assert report.headers["content-type"].startswith("text/plain")
        assert SECRET not in report.text
        assert response.json()["request_id"] not in report.text
        assert sample(app.state.metrics, "http_requests_total", route="chat", status="200") == 1
        assert sample(app.state.metrics, "http_requests_total", route="chat", status="422") == 1
        assert sample(app.state.metrics, "http_requests_total", route="other", status="404") == 1
        assert sample(app.state.metrics, "http_requests_in_flight") == 0
    assert app.state.ready is False
    separate = create_app(config=GatewayConfig())
    assert sample(separate.state.metrics, "http_requests_total", route="chat", status="200") is None


@pytest.mark.parametrize("failure", ["rate_limit", "timeout"])
def test_real_adapter_failure_reaches_safe_http_error_and_metrics(monkeypatch, caplog, failure):
    import httpx
    from gateway7 import providers

    key = "synthetic-adapter-key-private"
    monkeypatch.setenv("FAKE_LLM_API_KEY", key)
    attempts = []

    def upstream(request):
        attempts.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(SECRET + key, request=request)
        return httpx.Response(429, text=SECRET + key)

    client_class = httpx.AsyncClient
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(upstream), **kwargs,
    ))
    app = create_app(config=GatewayConfig())
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        response = client.post("/chat", json={"messages": [{"role": "user", "content": SECRET}]})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "provider_error"
        assert len(attempts) == 1
        metrics = client.get("/metrics").text
        assert sample(app.state.metrics, "provider_calls_total", provider="fake", outcome="provider_error") == 1
        assert sample(app.state.metrics, "provider_usage_unknown_total", provider="fake") == 1
        assert sample(app.state.metrics, "http_requests_total", route="chat", status="502") == 1
        assert all(value not in response.text + metrics + caplog.text for value in (SECRET, key))


def test_oversized_provider_usage_does_not_prevent_answer(monkeypatch):
    import httpx
    from gateway7 import providers

    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-only")
    client_class = httpx.AsyncClient
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "text": "pong", "usage": {"input_tokens": 10**400, "output_tokens": 2},
        })), **kwargs,
    ))
    app = create_app(config=GatewayConfig())
    with TestClient(app) as client:
        response = client.post("/chat", json={"messages": [{"role": "user", "content": "hello"}]})
        assert response.status_code == 200
        assert response.json()["text"] == "pong"
        assert response.json()["usage"] is None
        assert sample(app.state.metrics, "provider_usage_unknown_total", provider="fake") == 1
        assert sample(app.state.metrics, "provider_calls_total", provider="fake", outcome="complete") == 1

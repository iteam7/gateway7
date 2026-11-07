"""Product events stay bounded, private, isolated, and outside the response path."""

import asyncio
import importlib
import json
from collections import Counter
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from gateway7.analytics import Analytics, TaskEvent
from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError
from gateway7.models import ChatResponse

TOKEN = "synthetic-analytics-client-token"
PRIVATE_TEXT = "synthetic-content-should-never-leave-the-gateway"


def settings(**updates):
    return {
        "ANALYTICS_ENABLED": "true",
        "GATEWAY7_ENVIRONMENT": "staging",
        "ANALYTICS_SOURCE": "smoke",
        "OPENPANEL_API_URL": "http://analytics.invalid/api",
        "OPENPANEL_CLIENT_ID": "synthetic-openpanel-client",
        "OPENPANEL_CLIENT_SECRET": "synthetic-openpanel-secret",
        **updates,
    }


class Provider:
    async def complete(self, request, *, model=None):
        return ChatResponse(text=PRIVATE_TEXT, usage={"input_tokens": 2, "output_tokens": 1})

    async def aclose(self):
        pass


@pytest.fixture
def gateway_factory(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-provider-secret")
    monkeypatch.setenv("CLIENT_ANALYTICS", TOKEN)
    app_module = importlib.import_module("gateway7.app")
    monkeypatch.setattr(app_module, "build_provider", lambda *_: Provider())
    config = GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "model": "synthetic-private-model"},
            "auth": {
                "enabled": True,
                "clients": {
                    "synthetic-private-client": {
                        "token_env": "CLIENT_ANALYTICS",
                        "models": ["synthetic-private-model"],
                    },
                },
            },
        }
    )
    return lambda analytics: create_app(config=config, analytics=analytics)


@pytest.mark.asyncio
async def test_both_chat_apis_record_the_core_task_and_failures_without_content(gateway_factory):
    sent = []

    async def collect(request):
        sent.append((request.url, dict(request.headers), json.loads(request.content)))
        return httpx.Response(200)

    analytics = Analytics.from_environment(settings(), transport=httpx.MockTransport(collect))
    app = gateway_factory(analytics)
    body = {"messages": [{"role": "user", "content": PRIVATE_TEXT}]}
    headers = {"Authorization": "Bearer " + TOKEN, "X-Gateway7-Traffic-Source": "web"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            native = await client.post("/chat", headers=headers, json=body)
            openai = await client.post(
                "/v1/chat/completions",
                headers=headers,
                json={**body, "model": "synthetic-private-model"},
            )
            denied = await client.post("/chat", json=body)
            invalid = await client.post("/chat", headers=headers, json={"messages": []})
            forbidden = await client.post(
                "/chat", headers=headers, json={**body, "model": "forbidden"}
            )
            for path in ("/health", "/ready", "/metrics", "/v1/models"):
                assert (await client.get(path, headers=headers)).status_code == 200
    assert [r.status_code for r in (native, openai, denied, invalid, forbidden)] == [
        200,
        200,
        401,
        422,
        403,
    ]
    assert len(sent) == 10
    by_id = {}
    for url, export_headers, envelope in sent:
        assert str(url) == "http://analytics.invalid/api/track"
        assert export_headers["openpanel-client-id"] == "synthetic-openpanel-client"
        assert export_headers["openpanel-client-secret"] == "synthetic-openpanel-secret"
        assert "x-client-ip" not in export_headers and "authorization" not in export_headers
        assert export_headers["user-agent"] == "gateway7-analytics"
        assert set(envelope) == {"type", "payload"} and envelope["type"] == "track"
        payload = envelope["payload"]
        assert set(payload) == {"name", "profileId", "properties"}
        properties = payload["properties"]
        request_id = properties["request_id"]
        assert payload["profileId"] == request_id
        assert properties["source"] == "smoke" and properties["environment"] == "staging"
        assert datetime.fromisoformat(properties["occurred_at"]).utcoffset().total_seconds() == 0
        assert properties["__timestamp"] == properties["occurred_at"]
        expected = {"request_id", "route", "source", "environment", "occurred_at", "__timestamp"}
        if payload["name"] == "chat_completed":
            expected |= {"status", "outcome", "duration_ms"}
            assert properties["duration_ms"] >= 0
        assert set(properties) == expected
        by_id.setdefault(request_id, []).append(payload)
        exported = json.dumps(envelope)
        for private in (
            PRIVATE_TEXT,
            TOKEN,
            "synthetic-private-client",
            "synthetic-private-model",
            "synthetic-provider-secret",
            "synthetic-openpanel-secret",
        ):
            assert private not in exported
    expected_status = {
        r.headers["x-request-id"]: r.status_code
        for r in (native, openai, denied, invalid, forbidden)
    }
    assert set(by_id) == set(expected_status)
    for request_id, events in by_id.items():
        assert [event["name"] for event in events] == ["chat_started", "chat_completed"]
        assert events[1]["properties"]["status"] == expected_status[request_id]
        assert events[1]["properties"]["outcome"] == (
            "ok" if expected_status[request_id] == 200 else "client_error"
        )


@pytest.mark.asyncio
async def test_slow_or_failed_export_does_not_hold_a_gateway_response(gateway_factory, caplog):
    exporting = asyncio.Event()
    release = asyncio.Event()
    attempts = []

    async def unavailable(request):
        attempts.append(request)
        exporting.set()
        await release.wait()
        if len(attempts) == 1:
            raise httpx.ConnectError("synthetic-secret-backend-error", request=request)
        return httpx.Response(503, text="synthetic-secret-response")

    analytics = Analytics.from_environment(settings(), transport=httpx.MockTransport(unavailable))
    app = gateway_factory(analytics)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await asyncio.wait_for(
                client.post(
                    "/chat",
                    headers={"Authorization": "Bearer " + TOKEN},
                    json={"messages": [{"role": "user", "content": "hello"}]},
                ),
                timeout=1,
            )
            assert response.status_code == 200
            await asyncio.wait_for(exporting.wait(), timeout=1)
            assert not release.is_set()
            release.set()
    assert len(attempts) == 2
    assert "synthetic-secret-backend-error" not in caplog.text
    assert "synthetic-secret-response" not in caplog.text
    assert "outcome=export_failed" in caplog.text


@pytest.mark.asyncio
async def test_queue_overflow_drops_events_without_blocking_or_retries(caplog):
    sent = []

    async def collect(request):
        sent.append(json.loads(request.content))
        return httpx.Response(302, headers={"Location": "http://redirect.invalid/secret"})

    analytics = Analytics.from_environment(settings(), transport=httpx.MockTransport(collect))
    await analytics.start()
    for _ in range(1000):
        analytics.started(request_id=uuid4().hex, route="chat")
    await analytics.shutdown()
    assert 0 < len(sent) <= 256
    assert "outcome=event_dropped" in caplog.text
    assert "outcome=export_failed" in caplog.text
    assert "redirect.invalid" not in caplog.text
    assert not analytics.enabled


@pytest.mark.asyncio
async def test_shutdown_bounds_a_stuck_export_and_stops_worker(monkeypatch, caplog):
    import gateway7.analytics as module

    monkeypatch.setattr(module, "SHUTDOWN_TIMEOUT_SECONDS", 0.02)
    exporting = asyncio.Event()
    stopped = asyncio.Event()

    async def stuck(request):
        exporting.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    analytics = Analytics.from_environment(settings(), transport=httpx.MockTransport(stuck))
    await analytics.start()
    analytics.started(request_id=uuid4().hex, route="chat")
    await exporting.wait()
    await asyncio.wait_for(analytics.shutdown(), timeout=1)
    assert stopped.is_set() and not analytics.enabled
    assert "outcome=flush_timeout" in caplog.text
    await analytics.shutdown()


@pytest.mark.parametrize(
    "environment,source",
    [
        ("staging", "smoke"),
        ("staging", "usability-test"),
        ("staging", "web"),
        ("production", "web"),
    ],
)
@pytest.mark.asyncio
async def test_environment_source_is_owned_by_deployment(environment, source):
    sent = []

    async def collect(request):
        sent.append(json.loads(request.content)["payload"]["properties"])
        return httpx.Response(200)

    analytics = Analytics.from_environment(
        settings(GATEWAY7_ENVIRONMENT=environment, ANALYTICS_SOURCE=source),
        transport=httpx.MockTransport(collect),
    )
    await analytics.start()
    analytics.completed(request_id=uuid4().hex, route="openai_chat", status=499, duration_ms=1)
    await analytics.shutdown()
    assert sent[0]["source"] == source and sent[0]["environment"] == environment
    assert sent[0]["outcome"] == "cancelled"


@pytest.mark.parametrize(
    "updates",
    [
        {"ANALYTICS_ENABLED": "sometimes"},
        {"GATEWAY7_ENVIRONMENT": "development"},
        {"ANALYTICS_SOURCE": "caller-text"},
        {"GATEWAY7_ENVIRONMENT": "production", "ANALYTICS_SOURCE": "smoke"},
        {"GATEWAY7_ENVIRONMENT": "production", "ANALYTICS_SOURCE": "usability-test"},
        {"OPENPANEL_API_URL": "file:///tmp/events"},
        {"OPENPANEL_API_URL": "https://user:secret@analytics.invalid"},
        {"OPENPANEL_API_URL": "https://analytics.invalid?secret=value"},
        {"OPENPANEL_API_URL": "https://analytics.invalid/#fragment"},
        {"OPENPANEL_CLIENT_ID": ""},
        {"OPENPANEL_CLIENT_SECRET": ""},
        {"OPENPANEL_CLIENT_SECRET": "synthetic-secret\nheader"},
    ],
)
def test_invalid_configuration_fails_without_echoing_input(updates):
    with pytest.raises(StartupError) as error:
        Analytics.from_environment(settings(**updates))
    for private in ("secret=value", "secret@", "synthetic-secret", "caller-text"):
        assert private not in str(error.value)


def test_disabled_collection_creates_no_http_client(monkeypatch):
    def unexpected_client(*args, **kwargs):
        raise AssertionError("disabled collection must not create a client")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_client)
    for env in ({}, {"ANALYTICS_ENABLED": "false", "OPENPANEL_API_URL": "not-a-url"}):
        analytics = Analytics.from_environment(env)
        assert not analytics.enabled
        analytics.started(request_id=uuid4().hex, route="chat")


def test_event_contract_rejects_extra_fields_and_arbitrary_labels():
    fields = dict(
        name="chat_started",
        request_id=uuid4().hex,
        route="chat",
        environment="staging",
        source="smoke",
        occurred_at="2026-11-07T00:00:00+00:00",
    )
    for extra in ({"prompt": PRIVATE_TEXT}, {"route": PRIVATE_TEXT}, {"source": PRIVATE_TEXT}):
        with pytest.raises(ValidationError):
            TaskEvent(**{**fields, **extra})
    with pytest.raises(ValidationError):
        TaskEvent(**{**fields, "name": "chat_completed"})
    with pytest.raises(ValidationError):
        TaskEvent(**{**fields, "status": 200})
    with pytest.raises(ValidationError):
        TaskEvent(**{**fields, "occurred_at": PRIVATE_TEXT})
    with pytest.raises(ValidationError):
        TaskEvent(**{**fields, "occurred_at": "2026-11-07T00:00:00+03:00"})
    with pytest.raises(ValidationError):
        TaskEvent(**{**fields, "occurred_at": "2026-11-07T00:00:00"})


@pytest.mark.parametrize("path,route", [("/chat", "chat"), ("/v1/chat/completions", "openai_chat")])
@pytest.mark.parametrize(
    "failure,expected_status,expected_outcome",
    [(TimeoutError, 504, "server_error"), (asyncio.CancelledError, 499, "cancelled")],
    ids=["send-timeout", "send-cancelled"],
)
@pytest.mark.asyncio
async def test_incomplete_or_failed_send_is_never_counted_as_success(
    gateway_factory, path, route, failure, expected_status, expected_outcome
):
    sent = []

    async def collect(request):
        sent.append(json.loads(request.content)["payload"])
        return httpx.Response(200)

    analytics = Analytics.from_environment(settings(), transport=httpx.MockTransport(collect))
    app = gateway_factory(analytics)
    body = json.dumps(
        {"model": "synthetic-private-model", "messages": [{"role": "user", "content": "hello"}]}
    ).encode()
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "query_string": b"",
        "headers": [
            (b"authorization", ("Bearer " + TOKEN).encode()),
            (b"content-type", b"application/json"),
        ],
        "server": ("test", 80),
        "client": ("test", 1),
    }
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()

    response_statuses = []

    async def failing_send(message):
        if message["type"] == "http.response.start":
            response_statuses.append(message["status"])
        if message["type"] == "http.response.body":
            raise failure("synthetic-incomplete-send")

    async with app.router.lifespan_context(app):
        if failure is asyncio.CancelledError:
            with pytest.raises(asyncio.CancelledError):
                await app(scope, receive, failing_send)
        else:
            await app(scope, receive, failing_send)
    assert response_statuses == [200]
    assert Counter(item["name"] for item in sent) == {"chat_started": 1, "chat_completed": 1}
    completed = sent[1]["properties"]
    assert completed["route"] == route
    assert completed["status"] == expected_status
    assert completed["outcome"] == expected_outcome


@pytest.mark.asyncio
async def test_client_close_failure_is_sanitized_and_cannot_break_shutdown(caplog):
    class BrokenClose(httpx.AsyncClient):
        async def aclose(self):
            raise RuntimeError("synthetic-private-close-error")

    analytics = Analytics(client=BrokenClose(trust_env=False))
    await analytics.start()
    await analytics.shutdown()
    assert not analytics.enabled
    assert "outcome=shutdown_error" in caplog.text
    assert "synthetic-private-close-error" not in caplog.text

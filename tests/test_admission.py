"""The HTTP APIs share bounded admission until each pipeline task really exits."""

import asyncio
import gc
import importlib
import json
import sys
import time
from types import ModuleType

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.requests import Request

from gateway7.app import create_app
from gateway7.config import GatewayConfig, LimitsConfig, load_config
from gateway7.errors import StartupError
from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_api import Deny, PluginDescriptor

app_module = importlib.import_module("gateway7.app")
SENTINEL = "synthetic-admission-private-message"


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Gate:
    def __init__(self, *, resist=False, outcome="success"):
        self.entered = asyncio.Queue()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.resist = resist
        self.outcome = outcome
        self.calls = 0

    async def handle(self, request, context, call_next):
        self.calls += 1
        self.entered.put_nowait(request.messages[-1].content)
        while True:
            try:
                await self.release.wait()
                break
            except asyncio.CancelledError:
                self.cancelled.set()
                if not self.resist:
                    raise
        if self.outcome == "plugin_error":
            raise RuntimeError(SENTINEL)
        if self.outcome == "policy_denied":
            return Deny()
        return await call_next(request)


class Provider:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    async def complete(self, request):
        self.calls.append(request)
        if self.fail:
            raise RuntimeError(SENTINEL)
        return ChatResponse(text="synthetic answer")

    async def aclose(self):
        pass


def make_app(
    monkeypatch,
    gate,
    *,
    limit=1,
    hook_timeout=10,
    request_timeout=10,
    provider_fail=False,
    authenticated=False,
):
    module = ModuleType("test_gateway7_admission_plugin")
    module.PLUGIN = PluginDescriptor("admission-test", 2, Settings, lambda _: gate)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("FAKE_LLM_API_KEY", "synthetic-admission-provider-key")
    provider = Provider(fail=provider_fail)
    monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
    config = GatewayConfig.model_validate(
        {
            "limits": {
                "max_concurrent_requests": limit,
                "hook_timeout_seconds": hook_timeout,
                "request_timeout_seconds": request_timeout,
            },
            "plugins": {"gate": {"module": module.__name__}},
            "middleware": ["gate"],
        }
    )
    if authenticated:
        monkeypatch.setenv("GATEWAY7_ADMISSION_CLIENT_TOKEN", "synthetic-admission-client-token")
        config = GatewayConfig.model_validate(
            {
                **config.model_dump(),
                "auth": {
                    "enabled": True,
                    "clients": {
                        "test": {"token_env": "GATEWAY7_ADMISSION_CLIENT_TOKEN", "models": ["fake"]}
                    },
                },
            }
        )
    return create_app(config=config), provider


def body(*, openai=False):
    payload = {"messages": [{"role": "user", "content": SENTINEL}]}
    if openai:
        payload["model"] = "fake"
    return payload


def sample(app, name):
    return app.state.metrics.registry.get_sample_value("gateway7_" + name)


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://gateway.test")


async def test_capacity_is_shared_by_both_chat_apis_and_operational_endpoints_bypass(monkeypatch):
    gate = Gate()
    app, provider = make_app(monkeypatch, gate, limit=2)
    async with app.router.lifespan_context(app), client_for(app) as client:
        first = asyncio.create_task(client.post("/chat", json=body()))
        second = asyncio.create_task(client.post("/v1/chat/completions", json=body(openai=True)))
        try:
            await asyncio.wait_for(gate.entered.get(), 1)
            await asyncio.wait_for(gate.entered.get(), 1)
            assert sample(app, "active_pipelines") == 2
            for path, openai in (("/chat", False), ("/v1/chat/completions", True)):
                response = await asyncio.wait_for(client.post(path, json=body(openai=openai)), 1)
                assert response.status_code == 503
                error = response.json()["error"]
                assert error["code"] == "overloaded"
                assert response.json()["request_id"] == response.headers["x-request-id"]
                assert SENTINEL not in response.text
                if openai:
                    assert error["type"] == "api_error" and error["param"] is None
            assert gate.calls == 2 and provider.calls == []
            assert sample(app, "admission_rejections_total") == 2
            for path in ("/health", "/ready", "/metrics", "/v1/models"):
                assert (await client.get(path)).status_code == 200
            assert sample(app, "active_pipelines") == 2
            # Validation and model authorization still precede admission.
            assert (await client.post("/chat", json={"unexpected": SENTINEL})).status_code == 422
            assert (
                await client.post("/chat", json={**body(), "model": "forbidden"})
            ).status_code == 403
            assert sample(app, "admission_rejections_total") == 2
            report = (await client.get("/metrics")).text
            assert "gateway7_active_pipelines 2.0" in report
            assert "gateway7_admission_rejections_total 2.0" in report
            assert SENTINEL not in report and "synthetic-admission-provider-key" not in report
        finally:
            gate.release.set()
            results = await asyncio.wait_for(asyncio.gather(first, second), 1)
        assert [response.status_code for response in results] == [200, 200]
        assert len(provider.calls) == 2 and sample(app, "active_pipelines") == 0
        assert (await client.post("/chat", json=body())).status_code == 200
        assert len(provider.calls) == 3 and sample(app, "active_pipelines") == 0


@pytest.mark.parametrize(
    "outcome,status,calls",
    [
        ("success", 200, 1),
        ("plugin_error", 500, 0),
        ("policy_denied", 403, 0),
        ("provider_error", 502, 1),
        ("timeout", 504, 0),
    ],
)
async def test_finished_pipeline_releases_capacity_on_every_outcome(
    monkeypatch, outcome, status, calls
):
    gate = Gate(outcome=outcome)
    app, provider = make_app(
        monkeypatch,
        gate,
        hook_timeout=0.03 if outcome == "timeout" else 10,
        provider_fail=outcome == "provider_error",
    )
    async with app.router.lifespan_context(app), client_for(app) as client:
        pending = asyncio.create_task(client.post("/chat", json=body()))
        await asyncio.wait_for(gate.entered.get(), 1)
        assert sample(app, "active_pipelines") == 1
        if outcome != "timeout":
            gate.release.set()
        response = await asyncio.wait_for(pending, 1)
        assert response.status_code == status
        assert len(provider.calls) == calls
        assert sample(app, "active_pipelines") == 0
        assert sample(app, "admission_rejections_total") == 0
        retry = await asyncio.wait_for(client.post("/chat", json=body()), 1)
        assert retry.status_code == status
        assert len(provider.calls) == calls * 2
        assert sample(app, "active_pipelines") == 0


async def raw_request(app):
    incoming = asyncio.Queue()
    await incoming.put(
        {"type": "http.request", "body": json.dumps(body()).encode(), "more_body": False}
    )
    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/chat",
        "raw_path": b"/chat",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "server": ("gateway.test", 80),
        "client": ("synthetic", 1000),
    }
    return asyncio.create_task(app(scope, incoming.get, send)), incoming, sent


@pytest.mark.parametrize("termination", ["disconnect", "cancel"])
@pytest.mark.parametrize("resist", [False, True])
async def test_cancelled_pipeline_holds_slot_until_actual_completion(
    monkeypatch, termination, resist
):
    gate = Gate(resist=resist)
    app, provider = make_app(monkeypatch, gate)
    async with app.router.lifespan_context(app), client_for(app) as client:
        pending, incoming, sent = await raw_request(app)
        await asyncio.wait_for(gate.entered.get(), 1)
        if termination == "disconnect":
            await incoming.put({"type": "http.disconnect"})
        else:
            pending.cancel()
        await asyncio.wait_for(gate.cancelled.wait(), 1)
        try:
            if resist:
                assert not pending.done()
                assert sample(app, "active_pipelines") == 1
                assert (await client.post("/chat", json=body())).status_code == 503
                assert gate.calls == 1 and provider.calls == []
        finally:
            gate.release.set()
            if termination == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(pending, 1)
            else:
                await asyncio.wait_for(pending, 1)
                assert sent[0]["status"] == 499
        assert sample(app, "active_pipelines") == 0
        assert provider.calls == []  # No late forwarding after observed cancellation.
        assert (await client.post("/chat", json=body())).status_code == 200
        assert len(provider.calls) == 1 and sample(app, "active_pipelines") == 0


@pytest.mark.parametrize("deadline", ["middleware", "request"])
async def test_expired_timeout_keeps_capacity_until_cancellation_resistant_plugin_exits(
    monkeypatch,
    deadline,
):
    gate = Gate(resist=True)
    app, provider = make_app(
        monkeypatch,
        gate,
        hook_timeout=0.03 if deadline == "middleware" else 10,
        request_timeout=0.03 if deadline == "request" else 10,
    )
    async with app.router.lifespan_context(app), client_for(app) as client:
        # Clear earlier tests' cyclic app graphs before arming the 30 ms budget;
        # this case requires the hook to enter before its deliberate timeout.
        gc.collect()
        pending = asyncio.create_task(client.post("/chat", json=body()))
        await asyncio.wait_for(gate.entered.get(), 1)
        await asyncio.wait_for(gate.cancelled.wait(), 1)
        try:
            assert sample(app, "active_pipelines") == 1 and not pending.done()
            rejected = await client.post("/v1/chat/completions", json=body(openai=True))
            assert rejected.status_code == 503 and provider.calls == []
        finally:
            gate.release.set()
            response = await asyncio.wait_for(pending, 1)
        assert response.status_code == 504
        assert sample(app, "active_pipelines") == 0 and provider.calls == []
        assert (await client.post("/chat", json=body())).status_code == 200


async def test_capacity_and_metric_registries_are_isolated_between_apps(monkeypatch):
    first_gate = Gate()
    first, _ = make_app(monkeypatch, first_gate)
    async with first.router.lifespan_context(first), client_for(first) as first_client:
        pending = asyncio.create_task(first_client.post("/chat", json=body()))
        await asyncio.wait_for(first_gate.entered.get(), 1)
        try:
            second_gate = Gate()
            second_gate.release.set()
            second, provider = make_app(monkeypatch, second_gate)
            async with second.router.lifespan_context(second), client_for(second) as second_client:
                assert (await first_client.post("/chat", json=body())).status_code == 503
                assert (await second_client.post("/chat", json=body())).status_code == 200
                assert sample(first, "active_pipelines") == 1
                assert sample(first, "admission_rejections_total") == 1
                assert sample(second, "active_pipelines") == 0
                assert sample(second, "admission_rejections_total") == 0
                assert len(provider.calls) == 1
        finally:
            first_gate.release.set()
            await asyncio.wait_for(pending, 1)
        assert sample(first, "active_pipelines") == 0


@pytest.mark.parametrize("value", [0, -1, 10001, 1.5, "2", True, None])
def test_concurrency_limit_rejects_invalid_or_coerced_values(value, tmp_path):
    with pytest.raises(ValidationError):
        LimitsConfig(max_concurrent_requests=value)
    path = tmp_path / "gateway.yaml"
    import yaml

    path.write_text(yaml.safe_dump({"limits": {"max_concurrent_requests": value}}))
    with pytest.raises(StartupError, match="^Invalid gateway configuration$"):
        load_config(path)


def test_concurrency_default_and_bounds():
    assert LimitsConfig().max_concurrent_requests == 64
    assert LimitsConfig(max_concurrent_requests=1).max_concurrent_requests == 1
    assert LimitsConfig(max_concurrent_requests=10000).max_concurrent_requests == 10000


@pytest.mark.parametrize("failure_at", [1, 2])
async def test_task_creation_failure_rolls_back_or_reaps_without_leaking_capacity(
    monkeypatch, failure_at
):
    gate = Gate()
    app, provider = make_app(monkeypatch, gate)
    original_create_task = asyncio.create_task
    creations = 0

    def fail_creation(coroutine):
        nonlocal creations
        creations += 1
        if creations == failure_at:
            raise RuntimeError("Synthetic task creation failure")
        return original_create_task(coroutine)

    async with app.router.lifespan_context(app), client_for(app) as client:
        request = Request(
            {
                "type": "http",
                "app": app,
                "state": {
                    "request_id": "synthetic-task-creation",
                    "deadline": time.monotonic() + 10,
                },
            }
        )
        with monkeypatch.context() as patch:
            patch.setattr(app_module.asyncio, "create_task", fail_creation)
            with pytest.raises(RuntimeError, match="Synthetic task creation failure"):
                await app_module._run_connected(request, ChatRequest.model_validate(body()), "fake")
        assert sample(app, "active_pipelines") == 0
        assert gate.calls == 0 and provider.calls == []
        gate.release.set()
        assert (await client.post("/chat", json=body())).status_code == 200
        assert len(provider.calls) == 1 and sample(app, "active_pipelines") == 0


async def test_abandoned_task_exception_is_consumed_without_unhandled_private_traceback():
    app = create_app(config=GatewayConfig())
    admission = app.state.admission
    release = asyncio.Event()
    finished = asyncio.Event()
    warnings = []
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: warnings.append(context))

    async def abandoned_pipeline():
        try:
            await release.wait()
            raise RuntimeError(SENTINEL)
        finally:
            finished.set()

    try:
        admission.acquire()
        task = asyncio.create_task(abandoned_pipeline())
        admission.track(task)
        del task  # The HTTP caller no longer holds or awaits this task.
        release.set()
        await asyncio.wait_for(finished.wait(), 1)
        callback_ran = asyncio.Event()
        loop.call_soon(callback_ran.set)
        await callback_ran.wait()
        gc.collect()
        assert sample(app, "active_pipelines") == 0
        assert warnings == []
    finally:
        loop.set_exception_handler(original_handler)


async def test_authentication_and_model_permissions_precede_full_capacity(monkeypatch):
    gate = Gate()
    app, provider = make_app(monkeypatch, gate, authenticated=True)
    headers = {"Authorization": "Bearer synthetic-admission-client-token"}
    async with app.router.lifespan_context(app), client_for(app) as client:
        pending = asyncio.create_task(client.post("/chat", json=body(), headers=headers))
        await asyncio.wait_for(gate.entered.get(), 1)
        try:
            for path, openai in (("/chat", False), ("/v1/chat/completions", True)):
                for bad_headers in ({}, {"Authorization": "Bearer synthetic-invalid-client-token"}):
                    denied = await client.post(path, json=body(openai=openai), headers=bad_headers)
                    assert denied.status_code == 401
                    assert denied.json()["error"]["code"] == "unauthorized"
                forbidden = await client.post(
                    path, json={**body(openai=openai), "model": "forbidden"}, headers=headers
                )
                assert forbidden.status_code == 403
                assert forbidden.json()["error"]["code"] == "model_forbidden"
            models = await client.get("/v1/models", headers=headers)
            assert models.status_code == 200
            assert [item["id"] for item in models.json()["data"]] == ["fake"]
            assert (await client.get("/v1/models")).status_code == 401
            assert sample(app, "admission_rejections_total") == 0
            overloaded = await client.post("/chat", json=body(), headers=headers)
            assert overloaded.status_code == 503
            assert overloaded.json()["error"]["code"] == "overloaded"
            assert sample(app, "admission_rejections_total") == 1
            assert sample(app, "active_pipelines") == 1
            assert gate.calls == 1 and provider.calls == []
        finally:
            gate.release.set()
            assert (await asyncio.wait_for(pending, 1)).status_code == 200
        assert sample(app, "active_pipelines") == 0
        assert len(provider.calls) == 1

"""Boundary tests for configuration, middleware ordering, privacy, and fail-closed work."""

import asyncio
import importlib
import json
import os
import subprocess
import sys
import time
from types import ModuleType

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from gateway7.app import create_app
from gateway7.config import GatewayConfig, LimitsConfig, load_config, provider_key
from gateway7.errors import GatewayError, StartupError
from gateway7.loader import load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import API_VERSION, Deny, PluginDescriptor

app_module = importlib.import_module("gateway7.app")
SECRET = "synthetic-private-sentinel-712"


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    label: str = "test"
    count: int = Field(default=1, ge=1)


class PassThrough:
    async def handle(self, request, context, call_next):
        return await call_next(request)


class FakeProvider:
    def __init__(self, events=None):
        self.calls = []
        self.events = events
        self.closed = False

    async def complete(self, request):
        self.calls.append(request)
        if self.events is not None:
            self.events.append("provider")
        return ChatResponse(text="answer", usage={"input_tokens": 8, "output_tokens": 2})

    async def aclose(self):
        self.closed = True


def module(monkeypatch, factory=None, name="test_gateway7_plugin", descriptor=None):
    item = ModuleType(name)
    item.PLUGIN = descriptor or PluginDescriptor(
        id="test-type", api_version=API_VERSION, settings_model=Settings,
        create=factory or (lambda _: PassThrough()),
    )
    monkeypatch.setitem(sys.modules, name, item)
    return name


def configuration(plugins=None, middleware=None, limits=None):
    return GatewayConfig.model_validate({
        "provider": {"key_env": "GATEWAY7_TEST_KEY"},
        "plugins": plugins or {},
        "middleware": middleware or [],
        "limits": limits or {},
    })


def payload(text="hello"):
    return ChatRequest(messages=[Message(role="user", content=text)])


def pipeline_for(monkeypatch, plugin, *, limits=None):
    name = module(monkeypatch, lambda _: plugin)
    config = configuration({"p": {"module": name}}, ["p"], limits=limits)
    provider = FakeProvider()
    return Pipeline(load_plugins(config), provider, config.limits), provider


def write_config(tmp_path, config):
    path = tmp_path / "gateway.yaml"
    path.write_text(yaml.safe_dump(config.model_dump()), encoding="utf-8")
    return path


def test_config_is_strict_and_redacts_validation(tmp_path):
    for content in (
        f"provider:\n  unknown: {SECRET}\n",
        f"limits:\n  max_body_bytes: '{SECRET}'\n",
        f"plugins: [{SECRET}]\n",
        f"broken: [ {SECRET}\n",
        "plugins: {}\nplugins: {}\n",
        "plugins: &recursive\n  again: *recursive\n",
    ):
        path = tmp_path / "invalid.yaml"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(StartupError) as error:
            load_config(path)
        assert SECRET not in str(error.value)


def test_environment_key_is_required_and_never_in_error(monkeypatch):
    config = configuration()
    monkeypatch.delenv("GATEWAY7_TEST_KEY", raising=False)
    with pytest.raises(StartupError, match="GATEWAY7_TEST_KEY"):
        provider_key(config.provider)
    monkeypatch.setenv("GATEWAY7_TEST_KEY", "   ")
    with pytest.raises(StartupError):
        provider_key(config.provider)
    monkeypatch.setenv("GATEWAY7_TEST_KEY", SECRET)
    assert provider_key(config.provider) == SECRET


def test_disabled_modules_are_validated_but_not_constructed(monkeypatch):
    created = []
    name = module(monkeypatch, lambda settings: created.append(settings))
    config = configuration({"off": {"module": name, "enabled": False}}, ["off"])
    loaded = load_plugins(config)
    assert loaded.instances == {} and loaded.middleware_chain == ()
    assert created == []
    invalid = configuration({"off": {"module": name, "enabled": False, "settings": {"count": 0}}})
    with pytest.raises(StartupError, match="Invalid settings"):
        load_plugins(invalid)
    missing = configuration({"off": {"module": "module_that_does_not_exist", "enabled": False}})
    with pytest.raises(StartupError, match="Cannot load module"):
        load_plugins(missing)


@pytest.mark.parametrize("change", [
    {"api_version": 3}, {"api_version": True}, {"settings_model": int},
    {"create": None}, {"id": "invalid type id"},
])
def test_invalid_descriptor_is_rejected(monkeypatch, change):
    values = {"id": "test", "api_version": API_VERSION, "settings_model": Settings, "create": lambda _: PassThrough()}
    values.update(change)
    name = module(monkeypatch, descriptor=PluginDescriptor(**values))
    with pytest.raises(StartupError, match="Invalid PLUGIN descriptor"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))


@pytest.mark.parametrize("settings", [{"count": "1"}, {"unknown": SECRET}, {"count": 0}])
def test_invalid_plugin_settings_are_safe(monkeypatch, settings):
    name = module(monkeypatch)
    with pytest.raises(StartupError) as error:
        load_plugins(configuration({"p": {"module": name, "settings": settings}}, ["p"]))
    assert SECRET not in str(error.value)


def test_factory_cannot_inject_startup_error_details(monkeypatch):
    def failing_factory(settings):
        raise StartupError(SECRET)

    name = module(monkeypatch, failing_factory)
    with pytest.raises(StartupError) as error:
        load_plugins(configuration({"p": {"module": name}}, ["p"]))
    assert SECRET not in str(error.value)
    assert "Cannot construct plugin instance p" in str(error.value)


def test_loose_settings_model_and_wrong_hook_signature_fail_at_startup(monkeypatch):
    class LooseSettings(BaseModel):
        value: str = "default"

    name = module(monkeypatch, descriptor=PluginDescriptor("test", API_VERSION, LooseSettings, lambda _: PassThrough()))
    with pytest.raises(StartupError, match="Invalid PLUGIN descriptor"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))

    class WrongSignature:
        async def handle(self, request):
            return request

    module(monkeypatch, lambda _: WrongSignature())
    with pytest.raises(StartupError, match="invalid async hook"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))


def test_required_unknown_duplicate_and_wrong_hooks(monkeypatch):
    name = module(monkeypatch)
    with pytest.raises(StartupError, match="must be enabled"):
        load_plugins(configuration({"p": {"module": name, "required": True, "enabled": False}}))
    with pytest.raises(StartupError, match="missing from middleware chain"):
        load_plugins(configuration({"p": {"module": name, "required": True}}))
    with pytest.raises(StartupError, match="Unknown plugin instance"):
        load_plugins(configuration({}, ["missing"]))
    with pytest.raises(StartupError, match="Duplicate"):
        load_plugins(configuration({"p": {"module": name}}, ["p", "p"]))

    class Legacy:
        async def on_request(self, request, context):
            return request

    module(monkeypatch, lambda _: Legacy())
    with pytest.raises(StartupError, match="migrate legacy"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))

    class Synchronous:
        def handle(self, request, context, call_next):
            return request

    module(monkeypatch, lambda _: Synchronous())
    with pytest.raises(StartupError, match="invalid async hook"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))


def test_legacy_version_and_configuration_explain_migration(monkeypatch, tmp_path):
    name = module(monkeypatch, descriptor=PluginDescriptor("legacy", 1, Settings, lambda _: PassThrough()))
    with pytest.raises(StartupError, match="migrate to API v2"):
        load_plugins(configuration({"p": {"module": name}}, ["p"]))
    path = tmp_path / "legacy.yaml"
    path.write_text("chains:\n  request: []\n  response: []\n", encoding="utf-8")
    with pytest.raises(StartupError, match="replace chains.request/response with middleware"):
        load_config(path)


def test_startup_failure_cleans_started_plugins_and_is_safe(monkeypatch):
    events = []

    class Lifecycle(PassThrough):
        def __init__(self, settings):
            self.label = settings.label

        async def startup(self):
            events.append("start:" + self.label)
            if self.label == "fail":
                raise RuntimeError(SECRET)

        async def shutdown(self):
            events.append("stop:" + self.label)

    name = module(monkeypatch, Lifecycle)
    config = configuration({
        "first": {"module": name}, "second": {"module": name, "settings": {"label": "fail"}},
        "off": {"module": name, "enabled": False},
    })
    loaded = load_plugins(config)
    with pytest.raises(StartupError) as error:
        asyncio.run(start_plugins(loaded, 1))
    assert SECRET not in str(error.value)
    assert events == ["start:test", "start:fail", "stop:fail", "stop:test"]


def test_onion_order_and_provider_usage_are_preserved(monkeypatch):
    events = []

    class Ordered:
        def __init__(self, settings):
            self.label = settings.label

        async def handle(self, request, context, call_next):
            events.append("request:" + self.label)
            request = ChatRequest(messages=[Message(role="user", content=request.messages[0].content + self.label)])
            response = await call_next(request)
            events.append("response:" + self.label)
            response.usage["input_tokens"] = 0
            return ChatResponse(text=response.text + self.label, usage={"input_tokens": 0})

    name = module(monkeypatch, Ordered)
    config = configuration({
        "a": {"module": name, "settings": {"label": "A"}},
        "b": {"module": name, "settings": {"label": "B"}},
    }, ["a", "b"])
    provider = FakeProvider(events)
    response = asyncio.run(Pipeline(load_plugins(config), provider, config.limits).run(payload(), "order"))
    assert events == ["request:A", "request:B", "provider", "response:B", "response:A"]
    assert provider.calls[0].messages[0].content == "helloAB"
    assert response.text == "answerBA"
    assert response.usage == {"input_tokens": 8, "output_tokens": 2}


@pytest.mark.parametrize("failure,code", [
    (Deny(SECRET), "policy_denied"), (None, "plugin_error"), ({"text": SECRET}, "plugin_error"),
    (ChatResponse(text=SECRET), "plugin_error"),
    (ChatRequest.model_construct(messages=[]), "plugin_error"),
    (RuntimeError(SECRET), "plugin_error"),
    (GatewayError("provider_error"), "plugin_error"),
    (TimeoutError(SECRET), "plugin_error"),
])
def test_request_failure_never_reaches_provider(monkeypatch, caplog, failure, code):
    class Failing:
        async def handle(self, request, context, call_next):
            if isinstance(failure, Exception):
                raise failure
            return failure

    runner, provider = pipeline_for(monkeypatch, Failing())
    with caplog.at_level("INFO", logger="gateway7"), pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(SECRET), "failure"))
    assert error.value.code == code and provider.calls == []
    assert SECRET not in caplog.text + str(error.value) + str(error.value.body("failure"))


def test_response_denial_stops_outer_response_processing(monkeypatch):
    events = []

    class ResponseDeny:
        async def handle(self, request, context, call_next):
            await call_next(request)
            events.append("deny")
            return Deny()

    class Never:
        async def handle(self, request, context, call_next):
            response = await call_next(request)
            events.append("unexpected")
            return response

    first = module(monkeypatch, lambda _: ResponseDeny(), "test_deny_plugin")
    second = module(monkeypatch, lambda _: Never(), "test_never_plugin")
    config = configuration({"deny": {"module": first}, "outer": {"module": second}}, ["outer", "deny"])
    provider = FakeProvider()
    with pytest.raises(GatewayError, match="denied"):
        asyncio.run(Pipeline(load_plugins(config), provider, config.limits).run(payload(), "response"))
    assert len(provider.calls) == 1 and events == ["deny"]


def test_concurrent_context_state_is_per_request_and_per_instance(monkeypatch):
    contexts = {}

    class Stateful:
        def __init__(self, settings):
            self.label = settings.label

        async def handle(self, request, context, call_next):
            contexts[(context.request_id, self.label)] = context
            context.state["original"] = request.messages[0].content
            await asyncio.sleep(0)
            response = await call_next(request)
            assert contexts[(context.request_id, self.label)] is context
            await asyncio.sleep(0)
            return ChatResponse(text=response.text + ":" + context.state["original"])

    name = module(monkeypatch, Stateful)
    config = configuration({
        "a": {"module": name, "settings": {"label": "A"}},
        "b": {"module": name, "settings": {"label": "B"}},
    }, ["a", "b"])
    runner = Pipeline(load_plugins(config), FakeProvider(), config.limits)

    async def run():
        return await asyncio.gather(runner.run(payload("one"), "one"), runner.run(payload("two"), "two"))

    responses = asyncio.run(run())
    assert [item.text for item in responses] == ["answer:one:one", "answer:two:two"]
    assert len({id(context.state) for context in contexts.values()}) == 4
    assert all(context.state == {} for context in contexts.values())


@pytest.mark.parametrize("suppress_cancellation", [False, True])
def test_middleware_deadline_refuses_late_results(monkeypatch, suppress_cancellation):
    class Slow:
        async def handle(self, request, context, call_next):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                if not suppress_cancellation:
                    raise
            return await call_next(request)

    runner, provider = pipeline_for(monkeypatch, Slow(), limits={"hook_timeout_seconds": 0.01})
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "timeout"))
    assert error.value.code == "timeout" and provider.calls == []


def test_external_cancellation_cannot_be_swallowed_into_provider_call(monkeypatch):
    async def scenario():
        entered = asyncio.Event()

        class Slow:
            async def handle(self, request, context, call_next):
                entered.set()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    return await call_next(request)

        runner, provider = pipeline_for(monkeypatch, Slow())
        job = asyncio.create_task(runner.run(payload(), "cancelled"))
        await entered.wait()
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert provider.calls == []

    asyncio.run(scenario())


def test_total_timeout_and_provider_failures(monkeypatch, caplog):
    class SlowProvider(FakeProvider):
        async def complete(self, request):
            await asyncio.sleep(10)

    empty = load_plugins(configuration())
    runner = Pipeline(empty, SlowProvider(), LimitsConfig(request_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "total"))
    assert error.value.code == "timeout"

    class BadProvider(FakeProvider):
        async def complete(self, request):
            raise RuntimeError(SECRET)

    runner = Pipeline(empty, BadProvider(), LimitsConfig())
    with caplog.at_level("INFO", logger="gateway7"), pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "bad-provider"))
    assert error.value.code == "provider_error" and SECRET not in caplog.text + str(error.value)


def test_http_schema_body_limit_and_safe_errors(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", SECRET)
    provider = FakeProvider()
    monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
    path = write_config(tmp_path, configuration(limits={"max_body_bytes": 256}))
    with caplog.at_level("INFO", logger="gateway7"), TestClient(create_app(path)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        valid = client.post("/chat", json=payload().model_dump())
        assert valid.status_code == 200 and valid.json()["text"] == "answer"
        assert valid.headers["x-request-id"] == valid.json()["request_id"]
        for data in (
            {"messages": [{"role": "bad", "content": SECRET}]},
            {"messages": [{"role": "user", "content": SECRET}], "max_tokens": True},
            {"messages": [], "extra": SECRET},
        ):
            result = client.post("/chat", json=data)
            assert result.status_code == 422 and SECRET not in result.text
        malformed = client.post("/chat", content='{"messages": "' + SECRET)
        assert malformed.status_code == 422 and SECRET not in malformed.text
        oversized = client.post("/chat", content=SECRET * 20)
        assert oversized.status_code == 413 and SECRET not in oversized.text
    assert len(provider.calls) == 1 and provider.closed
    assert SECRET not in caplog.text


def test_http_disconnect_cancels_hook_before_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", SECRET)
    provider = FakeProvider()
    monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)

    async def scenario():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        class Slow:
            async def handle(self, request, context, call_next):
                entered.set()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        name = module(monkeypatch, lambda _: Slow())
        path = write_config(tmp_path, configuration({"p": {"module": name}}, ["p"]))
        app = create_app(path)
        messages = asyncio.Queue()
        await messages.put({"type": "http.request", "body": json.dumps(payload().model_dump()).encode(), "more_body": False})
        responses = []

        async def send(message):
            responses.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/chat", "raw_path": b"/chat",
            "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")],
            "server": ("test", 80), "client": ("test", 1000),
        }
        async with app.router.lifespan_context(app):
            request = asyncio.create_task(app(scope, messages.get, send))
            await entered.wait()
            await messages.put({"type": "http.disconnect"})
            await asyncio.wait_for(request, 1)
        assert cancelled.is_set() and provider.calls == []
        assert responses[0]["status"] == 499

    asyncio.run(scenario())


def test_cli_startup_failure_has_no_traceback_or_values(tmp_path):
    path = write_config(tmp_path, configuration())
    environment = dict(os.environ)
    environment.pop("GATEWAY7_TEST_KEY", None)
    result = subprocess.run(
        [sys.executable, "-m", "gateway7", "--config", str(path)],
        capture_output=True, text=True, timeout=10, env=environment,
    )
    assert result.returncode == 1
    assert "GATEWAY7_TEST_KEY" in result.stderr
    assert "Traceback" not in result.stderr and SECRET not in result.stderr


def test_next_can_only_run_once_even_if_plugin_catches_the_error(monkeypatch):
    class Repeated:
        async def handle(self, request, context, call_next):
            response = await call_next(request)
            try:
                await call_next(request)
            except GatewayError:
                pass
            return response

    runner, provider = pipeline_for(monkeypatch, Repeated())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "repeat"))
    assert error.value.code == "plugin_error" and len(provider.calls) == 1


def test_next_cannot_escape_into_a_concurrent_task(monkeypatch):
    class Concurrent:
        async def handle(self, request, context, call_next):
            task = asyncio.create_task(call_next(request))
            await asyncio.gather(task, return_exceptions=True)
            return Deny()

    runner, provider = pipeline_for(monkeypatch, Concurrent())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "concurrent-next"))
    assert error.value.code == "plugin_error" and provider.calls == []


def test_saved_next_cannot_run_after_middleware_return(monkeypatch):
    callbacks = []

    class Escape:
        async def handle(self, request, context, call_next):
            callbacks.append(call_next)
            return Deny()

    runner, provider = pipeline_for(monkeypatch, Escape())

    async def scenario():
        with pytest.raises(GatewayError, match="denied"):
            await runner.run(payload(), "escape")
        with pytest.raises(GatewayError) as error:
            await callbacks[0](payload())
        assert error.value.code == "plugin_error"

    asyncio.run(scenario())
    assert provider.calls == []


@pytest.mark.parametrize("failure", ["deny", "crash", "provider"])
def test_outer_middleware_cannot_swallow_downstream_failures(monkeypatch, failure):
    class Swallow:
        async def handle(self, request, context, call_next):
            try:
                await call_next(request)
            except Exception:
                return ChatResponse(text="invented-success")

    class Inner:
        async def handle(self, request, context, call_next):
            if failure == "deny":
                return Deny()
            if failure == "crash":
                raise RuntimeError(SECRET)
            return await call_next(request)

    class Provider(FakeProvider):
        async def complete(self, request):
            self.calls.append(request)
            raise RuntimeError(SECRET)

    outer = module(monkeypatch, lambda _: Swallow(), "test_swallow")
    inner = module(monkeypatch, lambda _: Inner(), "test_inner")
    config = configuration({"outer": {"module": outer}, "inner": {"module": inner}}, ["outer", "inner"])
    provider = Provider()
    with pytest.raises(GatewayError) as error:
        asyncio.run(Pipeline(load_plugins(config), provider, config.limits).run(payload(), "swallowed"))
    assert error.value.code == {"deny": "policy_denied", "crash": "plugin_error", "provider": "provider_error"}[failure]
    assert len(provider.calls) == (1 if failure == "provider" else 0)


@pytest.mark.parametrize("bad_request", [None, {"messages": []}, ChatRequest.model_construct(messages=[])])
def test_next_revalidates_request_before_forwarding(monkeypatch, bad_request):
    class Invalid:
        async def handle(self, request, context, call_next):
            return await call_next(bad_request)

    runner, provider = pipeline_for(monkeypatch, Invalid())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "invalid-next"))
    assert error.value.code == "plugin_error" and provider.calls == []


@pytest.mark.parametrize("bad_response", [None, {"text": "invalid"}, ChatResponse.model_construct(text=1)])
def test_postprocessing_response_is_revalidated(monkeypatch, bad_response):
    class Invalid:
        async def handle(self, request, context, call_next):
            await call_next(request)
            return bad_response

    runner, provider = pipeline_for(monkeypatch, Invalid())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "invalid-response"))
    assert error.value.code == "plugin_error" and len(provider.calls) == 1


def test_middleware_budget_excludes_downstream_provider_wait(monkeypatch):
    class SlowProvider(FakeProvider):
        async def complete(self, request):
            await asyncio.sleep(0.1)
            return await super().complete(request)

    name = module(monkeypatch)
    config = configuration({"outer": {"module": name}, "inner": {"module": name}}, ["outer", "inner"], limits={"hook_timeout_seconds": 0.03, "request_timeout_seconds": 1.0})
    provider = SlowProvider()
    response = asyncio.run(Pipeline(load_plugins(config), provider, config.limits).run(payload(), "provider-wait"))
    assert response.text == "answer" and len(provider.calls) == 1


def test_pre_and_postprocessing_share_one_own_work_budget(monkeypatch):
    class Slow:
        async def handle(self, request, context, call_next):
            await asyncio.sleep(0.04)
            response = await call_next(request)
            await asyncio.sleep(0.04)
            return response

    runner, provider = pipeline_for(monkeypatch, Slow(), limits={"hook_timeout_seconds": 0.06})
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "cumulative-budget"))
    assert error.value.code == "timeout" and len(provider.calls) == 1


@pytest.mark.parametrize("suppress_cancellation", [False, True])
def test_response_timeout_discards_late_result(monkeypatch, suppress_cancellation):
    class Slow:
        async def handle(self, request, context, call_next):
            response = await call_next(request)
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                if not suppress_cancellation:
                    raise
            return response

    runner, provider = pipeline_for(monkeypatch, Slow(), limits={"hook_timeout_seconds": 0.01})
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "response-timeout"))
    assert error.value.code == "timeout" and len(provider.calls) == 1


def test_expired_timer_is_terminal_even_before_clock_deadline(monkeypatch):
    real_timeout_at = asyncio.timeout_at
    created = 0

    class EarlyExpiry:
        def __init__(self, when):
            self.inner = real_timeout_at(when)

        async def __aenter__(self):
            await self.inner.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.inner.__aexit__(*args)

        def expired(self):
            return True

        def reschedule(self, when):
            self.inner.reschedule(when)

    def timeout_at(when):
        nonlocal created
        created += 1
        return EarlyExpiry(when) if created == 2 else real_timeout_at(when)

    class Late:
        async def handle(self, request, context, call_next):
            return Deny()

    monkeypatch.setattr(asyncio, "timeout_at", timeout_at)
    runner, provider = pipeline_for(monkeypatch, Late())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "early-timer"))
    assert error.value.code == "timeout" and provider.calls == []


def test_execution_logs_expose_phases_without_content(monkeypatch, caplog):
    runner, provider = pipeline_for(monkeypatch, PassThrough())
    with caplog.at_level("INFO", logger="gateway7"):
        asyncio.run(runner.run(payload(SECRET), "trace-id"))
    lines = caplog.text
    assert "request_id=trace-id" in lines and "component=p" in lines
    assert "phase=request" in lines and "phase=response" in lines
    assert "outcome=start" in lines and "outcome=complete" in lines
    assert "duration_ms=" in lines and SECRET not in lines



def test_slow_request_revalidation_cannot_forward_after_own_budget(monkeypatch):
    pipeline_module = importlib.import_module("gateway7.pipeline")
    validate = pipeline_module._validated
    request_checks = 0

    def slow_validation(value, expected):
        nonlocal request_checks
        if expected is ChatRequest:
            request_checks += 1
            if request_checks == 2:
                # Synchronous validation cannot yield to the timer callback.
                time.sleep(0.03)
        return validate(value, expected)

    monkeypatch.setattr(pipeline_module, "_validated", slow_validation)
    runner, provider = pipeline_for(monkeypatch, PassThrough(), limits={"hook_timeout_seconds": 0.01})
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "validation-budget"))
    assert error.value.code == "timeout" and provider.calls == []


def test_wrong_task_next_violation_is_terminal_before_owner_retry(monkeypatch):
    class Retry:
        async def handle(self, request, context, call_next):
            await asyncio.gather(asyncio.create_task(call_next(request)), return_exceptions=True)
            return await call_next(request)

    runner, provider = pipeline_for(monkeypatch, Retry())
    with pytest.raises(GatewayError) as error:
        asyncio.run(runner.run(payload(), "wrong-task-retry"))
    assert error.value.code == "plugin_error" and provider.calls == []



def test_module_descriptor_access_cannot_inject_startup_error(monkeypatch):
    name = "test_descriptor_access"
    item = ModuleType(name)

    def missing_attribute(attribute):
        if attribute == "PLUGIN":
            raise StartupError(SECRET)
        raise AttributeError(attribute)

    item.__getattr__ = missing_attribute
    monkeypatch.setitem(sys.modules, name, item)
    with pytest.raises(StartupError) as error:
        load_plugins(configuration({"p": {"module": name}}, ["p"]))
    assert "Invalid PLUGIN descriptor" in str(error.value)
    assert SECRET not in str(error.value)



def test_legacy_continue_import_gets_safe_migration_guidance(monkeypatch, tmp_path):
    name = "test_legacy_continue_import"
    (tmp_path / (name + ".py")).write_text(
        "from gateway7.plugin_api import Continue\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(StartupError) as error:
        load_plugins(configuration({"p": {"module": name}}, ["p"]))
    assert "Cannot load module" in str(error.value)
    assert "migrate API v1 hooks/Continue to API v2 handle" in str(error.value)
    assert str(tmp_path) not in str(error.value)

"""Early text requires an explicit request-only chain and fully validated final tools."""

import asyncio
import sys
import time
from dataclasses import replace
from types import ModuleType

import pytest
from pydantic import BaseModel, ConfigDict

from gateway7.config import GatewayConfig, LimitsConfig
from gateway7.errors import GatewayError, ProviderError, ProviderErrorReason, StartupError
from gateway7.loader import LoadedPlugin, LoadedPlugins, load_plugins, start_plugins, stop_plugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse, Message, ToolCall, ToolDefinition
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import API_VERSION, Deny, EarlyStreamUnsupported, PluginDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    phase: str = "response"


class Legacy:
    async def handle(self, request, context, call_next):
        return await call_next(request)


class Prepared(Legacy):
    async def prepare_early_stream(self, request, context):
        return request


class Provider:
    def __init__(self, response=None, *, events=None):
        self.calls = []
        self.events = events if events is not None else []
        self.response = response or ChatResponse(
            text="answer", usage={"input_tokens": 8, "output_tokens": 2}
        )

    async def complete(self, request):
        self.calls.append((request, None))
        return self.response

    async def complete_early(self, request, *, on_text, model=None):
        self.calls.append((request, model))
        self.events.append("provider")
        if self.response.text:
            await on_text(self.response.text)
        return self.response


def payload(text="hello", *, tools=False, choice=None, history=False):
    messages = [Message(role="user", content=text)]
    if history:
        messages += [
            Message(role="assistant", content=None, tool_calls=[call(identifier="call_old")]),
            Message(role="tool", content="synthetic result", tool_call_id="call_old"),
        ]
    return ChatRequest(
        messages=messages,
        tools=[definition()] if tools else [],
        tool_choice=choice,
    )


def definition(name="read"):
    return ToolDefinition.model_validate(
        {
            "function": {"name": name, "parameters": {"type": "object"}},
        }
    )


def call(name="read", identifier="call_read"):
    return ToolCall.model_validate(
        {
            "id": identifier,
            "function": {"name": name, "arguments": '{"path":"synthetic.txt"}'},
        }
    )


def loaded(*instances, tools=True):
    plugins = {}
    for index, instance in enumerate(instances):
        name = "p" + str(index)
        descriptor = PluginDescriptor("synthetic", API_VERSION, Settings, lambda _: instance, tools)
        plugins[name] = LoadedPlugin(
            name,
            descriptor,
            instance,
            instance.handle,
            None,
            None,
            getattr(instance, "prepare_early_stream", None),
        )
    return LoadedPlugins(plugins, tuple(plugins.values()))


def runner(*instances, provider=None, limits=None, metrics=None, tools=True):
    provider = provider or Provider()
    return Pipeline(
        loaded(*instances, tools=tools),
        provider,
        limits or LimitsConfig(),
        metrics=metrics,
        provider_name="openai",
    ), provider


async def discard_text(text):
    pass


def register(monkeypatch, instance):
    name = "synthetic_early_plugin"
    module = ModuleType(name)
    module.PLUGIN = PluginDescriptor("synthetic", API_VERSION, Settings, lambda _: instance)
    monkeypatch.setitem(sys.modules, name, module)
    return GatewayConfig.model_validate(
        {
            "plugins": {"p": {"module": name}},
            "middleware": ["p"],
        }
    )


def builtin_chain(*specifications):
    config = GatewayConfig.model_validate(
        {
            "plugins": {
                "p" + str(index): {"module": "gateway7.plugins." + module, "settings": settings}
                for index, (module, settings) in enumerate(specifications)
            },
            "middleware": ["p" + str(index) for index in range(len(specifications))],
        }
    )
    return load_plugins(config)


def sample(metrics, name, labels):
    return metrics.registry.get_sample_value(name, labels) or 0


async def test_preflight_checks_entire_chain_before_any_hook_or_provider():
    events = []

    class First(Prepared):
        async def prepare_early_stream(self, request, context):
            events.append("unexpected")
            return request

    pipeline, provider = runner(First(), Legacy())
    with pytest.raises(EarlyStreamUnsupported):
        await pipeline.run_early(payload(), on_text=discard_text)
    assert provider.calls == [] and events == []


@pytest.mark.parametrize("kind", ["fake", "claude", "gemini"])
async def test_non_openai_provider_is_rejected_before_hooks(kind):
    events = []

    class First(Prepared):
        async def prepare_early_stream(self, request, context):
            events.append("unexpected")
            return request

    pipeline, provider = runner(First())
    pipeline.provider_name = kind
    with pytest.raises(EarlyStreamUnsupported):
        await pipeline.run_early(payload(), on_text=discard_text)
    assert provider.calls == [] and events == []


async def test_missing_provider_method_does_not_fall_back_to_buffered_call():
    provider = Provider()
    provider.complete_early = None
    pipeline, _ = runner(provider=provider)
    with pytest.raises(EarlyStreamUnsupported):
        await pipeline.run_early(payload(), on_text=discard_text)
    assert provider.calls == []


@pytest.mark.parametrize(
    "module,settings",
    [
        ("content_policy", {"terms": ["blocked"], "phase": "both"}),
        ("content_policy", {"terms": ["blocked"], "phase": "response"}),
        ("email_mask", {"phase": "both"}),
        ("email_mask", {"phase": "response"}),
        ("phone_mask", {"phase": "both"}),
        ("phone_mask", {"phase": "response"}),
    ],
)
async def test_response_policy_is_unsupported_not_denied_or_skipped(module, settings):
    provider = Provider()
    pipeline = Pipeline(
        builtin_chain((module, settings)),
        provider,
        LimitsConfig(),
        provider_name="openai",
    )
    with pytest.raises(EarlyStreamUnsupported):
        await pipeline.run_early(payload("blocked"), on_text=discard_text)
    assert provider.calls == []


async def test_request_builtin_masks_and_redaction_complete_before_text():
    chain = builtin_chain(
        ("content_policy", {"terms": ["secret"], "action": "redact", "phase": "request"}),
        ("email_mask", {"phase": "request"}),
        ("phone_mask", {"phase": "request"}),
    )
    provider = Provider()
    pipeline = Pipeline(chain, provider, LimitsConfig(), provider_name="openai")
    original = payload("secret fixture@example.invalid +79000000000")
    chunks = []

    async def on_text(text):
        assert len(provider.calls) == 1
        assert provider.calls[0][0].messages[0].content == "[removed] [EMAIL] [PHONE]"
        chunks.append(text)

    response = await pipeline.run_early(
        original,
        "synthetic-masks",
        on_text=on_text,
        provider_model="selected-model",
    )
    assert response == provider.response and chunks == ["answer"]
    assert provider.calls[0][1] == "selected-model"
    assert original.messages[0].content == "secret fixture@example.invalid +79000000000"
    assert "stream" not in provider.calls[0][0].model_dump()


async def test_request_block_returns_current_policy_denial_without_provider_attempt():
    metrics = Metrics()
    provider = Provider()
    chain = builtin_chain(("content_policy", {"terms": ["blocked"], "phase": "request"}))
    pipeline = Pipeline(chain, provider, LimitsConfig(), metrics=metrics, provider_name="openai")
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload("blocked"), on_text=discard_text)
    assert caught.value.code == "policy_denied" and caught.value.status_code == 403
    assert provider.calls == []
    assert (
        sample(
            metrics,
            "gateway7_middleware_steps_total",
            {
                "middleware": "p0",
                "phase": "request",
                "outcome": "policy_denied",
            },
        )
        == 1
    )
    assert not list(metrics.provider_calls.collect())[0].samples


@pytest.mark.parametrize(
    "module,settings",
    [
        ("content_policy", {"terms": ["synthetic.txt"], "action": "redact", "phase": "request"}),
        ("email_mask", {"phase": "request"}),
        ("phone_mask", {"phase": "request"}),
    ],
)
async def test_builtin_request_guards_do_not_rewrite_executable_tool_strings(module, settings):
    request = payload(tools=True)
    if module != "content_policy":
        description = "fixture@example.invalid" if module == "email_mask" else "+79000000000"
        request = request.model_copy(
            update={
                "tools": [
                    ToolDefinition.model_validate(
                        {
                            "function": {
                                "name": "read",
                                "description": description,
                                "parameters": {"type": "object"},
                            },
                        }
                    )
                ]
            }
        )
    else:
        request = payload(tools=True, history=True)
    provider = Provider()
    pipeline = Pipeline(
        builtin_chain((module, settings)),
        provider,
        LimitsConfig(),
        provider_name="openai",
    )
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(request, on_text=discard_text)
    assert caught.value.code == "policy_denied" and provider.calls == []


async def test_hooks_run_in_order_without_interpreting_third_party_phase(monkeypatch):
    events = []
    contexts = []

    class Ordered(Prepared):
        settings = Settings(phase="response")

        def __init__(self, label):
            self.label = label

        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            events.append(self.label)
            assert "text" not in events
            return request.model_copy(
                update={
                    "messages": [
                        Message(
                            role="user",
                            content=request.messages[0].content + self.label,
                        )
                    ]
                }
            )

        async def handle(self, request, context, call_next):
            pytest.fail("Early mode must not invoke nested handle")

    provider = Provider(events=events)
    pipeline, _ = runner(Ordered("A"), Ordered("B"), provider=provider)

    async def on_text(text):
        events.append("text")

    await pipeline.run_early(payload(), "synthetic-order", on_text=on_text)
    assert events == ["A", "B", "provider", "text"]
    assert provider.calls[0][0].messages[0].content == "helloAB"
    assert len({id(context.state) for context in contexts}) == 2
    assert all(context.state == {} for context in contexts)
    assert all(context.request_id == "synthetic-order" for context in contexts)


async def test_legacy_hook_absence_preserves_loading_lifecycle_and_buffered_run(monkeypatch):
    events = []

    class Lifecycle(Legacy):
        async def startup(self):
            events.append("startup")

        async def shutdown(self):
            events.append("shutdown")

    config = register(monkeypatch, Lifecycle())
    plugins = load_plugins(config)
    assert API_VERSION == 2 and plugins.instances["p"].prepare_early_stream is None
    old_constructor = replace(plugins.instances["p"], prepare_early_stream=None)
    assert (
        LoadedPlugin(
            old_constructor.name,
            old_constructor.descriptor,
            old_constructor.instance,
            old_constructor.handle,
            old_constructor.startup,
            old_constructor.shutdown,
        ).prepare_early_stream
        is None
    )
    provider = Provider()
    pipeline = Pipeline(plugins, provider, config.limits, provider_name="openai")
    await start_plugins(plugins, 1)
    assert await pipeline.run(payload(), "synthetic-legacy") == provider.response
    with pytest.raises(EarlyStreamUnsupported):
        await pipeline.run_early(payload(), on_text=discard_text)
    await stop_plugins(plugins, 1)
    assert len(provider.calls) == 1 and events == ["startup", "shutdown"]


@pytest.mark.parametrize("kind", ["sync", "arity", "required_keyword", "value"])
def test_loader_rejects_invalid_optional_hook_with_safe_diagnostic(monkeypatch, kind):
    class Invalid(Legacy):
        pass

    if kind == "sync":

        def hook(self, request, context):
            return request
    elif kind == "arity":

        async def hook(self, request):
            return request
    elif kind == "required_keyword":

        async def hook(self, request, context, *, secret):
            return request
    else:
        hook = "synthetic-private-sentinel"
    Invalid.prepare_early_stream = hook
    with pytest.raises(StartupError, match="invalid async hook prepare_early_stream") as caught:
        load_plugins(register(monkeypatch, Invalid()))
    assert "synthetic-private-sentinel" not in str(caught.value)


def test_loader_accepts_and_binds_valid_optional_hook(monkeypatch):
    instance = Prepared()
    plugin = load_plugins(register(monkeypatch, instance)).instances["p"]
    assert plugin.prepare_early_stream == instance.prepare_early_stream


@pytest.mark.parametrize(
    "failure",
    [
        None,
        {},
        ChatResponse(text="wrong type"),
        ChatRequest.model_construct(messages=[]),
        RuntimeError("synthetic-private-sentinel"),
        GatewayError("provider_error"),
        TimeoutError("synthetic-private-sentinel"),
    ],
)
async def test_invalid_hook_results_fail_closed_and_clear_context(failure, caplog):
    contexts = []

    class Invalid(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            if isinstance(failure, Exception):
                raise failure
            return failure

    pipeline, provider = runner(Invalid())
    with caplog.at_level("INFO", logger="gateway7"), pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "plugin_error" and provider.calls == []
    assert all(context.state == {} for context in contexts)
    assert "synthetic-private-sentinel" not in str(caught.value) + caplog.text


async def test_hook_denial_uses_allowlisted_code_and_clears_context():
    contexts = []

    class Denied(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return Deny("synthetic-private-sentinel")

    pipeline, provider = runner(Denied())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "policy_denied" and provider.calls == []
    assert "synthetic-private-sentinel" not in str(caught.value)
    assert all(context.state == {} for context in contexts)


async def test_hook_cannot_add_transport_control_to_request():
    class Inject(Prepared):
        async def prepare_early_stream(self, request, context):
            return request.model_copy(update={"stream": True})

    pipeline, provider = runner(Inject())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "plugin_error" and provider.calls == []


@pytest.mark.parametrize("history", [False, True])
async def test_tool_capability_checked_before_any_hook(history):
    events = []

    class Inspect(Prepared):
        async def prepare_early_stream(self, request, context):
            events.append("unexpected")
            return request

    pipeline, provider = runner(Inspect(), tools=False)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(tools=not history, history=history), on_text=discard_text)
    assert caught.value.code == "invalid_request" and provider.calls == [] and events == []


async def test_new_tools_from_request_hook_cannot_bypass_chain_capability():
    events = []

    class AddTools(Prepared):
        async def prepare_early_stream(self, request, context):
            return request.model_copy(update={"tools": [definition()]})

    class Later(Prepared):
        async def prepare_early_stream(self, request, context):
            events.append("unexpected")
            return request

    pipeline, provider = runner(AddTools(), Later(), tools=False)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "invalid_request" and provider.calls == [] and events == []


@pytest.mark.parametrize("suppress_cancellation", [False, True])
@pytest.mark.parametrize("budget", ["hook", "request"])
async def test_timeouts_refuse_late_hook_results_and_clear_context(suppress_cancellation, budget):
    contexts = []

    class Slow(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not suppress_cancellation:
                    raise
            return request

    limits = LimitsConfig(**{budget + "_timeout_seconds": 0.01})
    pipeline, provider = runner(Slow(), limits=limits)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and provider.calls == []
    assert all(context.state == {} for context in contexts)


async def test_external_cancellation_cannot_be_swallowed_into_provider_attempt():
    entered = asyncio.Event()
    contexts = []

    class Slow(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return request

    pipeline, provider = runner(Slow())
    task = asyncio.create_task(pipeline.run_early(payload(), on_text=discard_text))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.calls == [] and all(context.state == {} for context in contexts)


async def test_synchronous_hook_cannot_forward_after_deadline():
    class Slow(Prepared):
        async def prepare_early_stream(self, request, context):
            time.sleep(0.03)
            return request

    pipeline, provider = runner(Slow(), limits=LimitsConfig(hook_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and provider.calls == []


async def test_slow_hook_result_validation_cannot_forward_after_own_budget(monkeypatch):
    import gateway7.pipeline as pipeline_module

    validate = pipeline_module._validated
    checks = 0

    def slow_validation(value, expected):
        nonlocal checks
        if expected is ChatRequest:
            checks += 1
            if checks == 2:
                time.sleep(0.03)
        return validate(value, expected)

    monkeypatch.setattr(pipeline_module, "_validated", slow_validation)
    pipeline, provider = runner(Prepared(), limits=LimitsConfig(hook_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and provider.calls == []


async def test_expired_hook_timer_refuses_result_even_before_monotonic_deadline(monkeypatch):
    timeout_at = asyncio.timeout_at
    created = 0

    class EarlyExpiry:
        def __init__(self, when):
            self.inner = timeout_at(when)

        async def __aenter__(self):
            await self.inner.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.inner.__aexit__(*args)

        def expired(self):
            return True

    def early_timeout_at(when):
        nonlocal created
        created += 1
        return EarlyExpiry(when) if created == 2 else timeout_at(when)

    monkeypatch.setattr(asyncio, "timeout_at", early_timeout_at)
    pipeline, provider = runner(Prepared())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and provider.calls == []


async def test_expired_deadline_is_checked_before_first_hook():
    events = []

    class Never(Prepared):
        async def prepare_early_stream(self, request, context):
            events.append("unexpected")
            return request

    pipeline, provider = runner(Never())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text, deadline=time.monotonic() - 1)
    assert caught.value.code == "timeout" and provider.calls == [] and events == []


async def test_hook_budget_excludes_provider_and_callback_wait():
    class SlowProvider(Provider):
        async def complete_early(self, request, *, on_text, model=None):
            await asyncio.sleep(0.03)
            return await super().complete_early(request, on_text=on_text, model=model)

    async def slow_text(text):
        await asyncio.sleep(0.03)

    pipeline, provider = runner(
        Prepared(),
        provider=SlowProvider(),
        limits=LimitsConfig(hook_timeout_seconds=0.01, request_timeout_seconds=1),
    )
    assert await pipeline.run_early(payload(), on_text=slow_text) == provider.response
    assert len(provider.calls) == 1


@pytest.mark.parametrize("synchronous", [False, True])
async def test_absolute_deadline_covers_callback_work(synchronous):
    async def slow_text(text):
        if synchronous:
            time.sleep(0.03)
        else:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass

    pipeline, provider = runner(limits=LimitsConfig(request_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=slow_text)
    assert caught.value.code == "timeout" and len(provider.calls) == 1


@pytest.mark.parametrize("synchronous", [False, True])
async def test_callback_exception_cannot_replace_expired_deadline(synchronous):
    async def failing_text(text):
        if synchronous:
            time.sleep(0.03)
        else:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        raise RuntimeError("synthetic callback failure")

    metrics = Metrics()
    pipeline, provider = runner(limits=LimitsConfig(request_timeout_seconds=0.01), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=failing_text)
    assert caught.value.code == "timeout" and len(provider.calls) == 1
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "cancelled",
            },
        )
        == 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "provider_error",
            },
        )
        == 0
    )
    assert sample(metrics, "gateway7_provider_usage_unknown_total", {"provider": "openai"}) == 1


async def test_absolute_deadline_covers_final_response_validation(monkeypatch):
    import gateway7.pipeline as pipeline_module

    validate = pipeline_module._validated

    def slow_validation(value, expected):
        if expected is ChatResponse:
            time.sleep(0.03)
        return validate(value, expected)

    monkeypatch.setattr(pipeline_module, "_validated", slow_validation)
    pipeline, provider = runner(limits=LimitsConfig(request_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and len(provider.calls) == 1


async def test_provider_cancellation_clears_context_and_records_one_attempt():
    entered = asyncio.Event()
    contexts = []

    class Stateful(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return request

    class SlowProvider(Provider):
        async def complete_early(self, request, *, on_text, model=None):
            self.calls.append((request, model))
            entered.set()
            await asyncio.Event().wait()

    metrics = Metrics()
    pipeline, provider = runner(Stateful(), provider=SlowProvider(), metrics=metrics)
    task = asyncio.create_task(pipeline.run_early(payload(), on_text=discard_text))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(provider.calls) == 1 and all(context.state == {} for context in contexts)
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "cancelled",
            },
        )
        == 1
    )


@pytest.mark.parametrize("error_type", [ProviderError, RuntimeError])
@pytest.mark.parametrize("interruption", ["cancel", "deadline"])
async def test_provider_exception_cannot_replace_cancellation_or_deadline(error_type, interruption):
    entered = asyncio.Event()
    contexts = []

    class Stateful(Prepared):
        async def prepare_early_stream(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return request

    class FailingProvider(Provider):
        async def complete_early(self, request, *, on_text, model=None):
            self.calls.append((request, model))
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if error_type is ProviderError:
                    raise ProviderError(
                        ProviderErrorReason.TRANSPORT,
                        usage={"input_tokens": 8, "output_tokens": 2},
                    ) from None
                raise RuntimeError("synthetic provider failure") from None

    metrics = Metrics()
    limits = LimitsConfig(request_timeout_seconds=0.01 if interruption == "deadline" else 1)
    pipeline, provider = runner(
        Stateful(), provider=FailingProvider(), limits=limits, metrics=metrics
    )
    task = asyncio.create_task(pipeline.run_early(payload(), on_text=discard_text))
    await entered.wait()
    if interruption == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    assert len(provider.calls) == 1 and all(context.state == {} for context in contexts)
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "cancelled",
            },
        )
        == 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "provider_error",
            },
        )
        == 0
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "complete",
            },
        )
        == 0
    )
    known_usage = error_type is ProviderError
    assert sample(metrics, "gateway7_provider_usage_unknown_total", {"provider": "openai"}) == (
        0 if known_usage else 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_tokens_total",
            {
                "provider": "openai",
                "direction": "input",
            },
        )
        == (8 if known_usage else 0)
    )
    assert sample(
        metrics, "gateway7_provider_tokens_total", {"provider": "openai", "direction": "output"}
    ) == (2 if known_usage else 0)


async def test_provider_exception_cannot_replace_early_total_timer_expiry(monkeypatch):
    timeout_at = asyncio.timeout_at

    class EarlyExpiry:
        def __init__(self, when):
            self.inner = timeout_at(when)

        async def __aenter__(self):
            await self.inner.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.inner.__aexit__(*args)

        def expired(self):
            return True

    class FailingProvider(Provider):
        async def complete_early(self, request, *, on_text, model=None):
            self.calls.append((request, model))
            raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(asyncio, "timeout_at", EarlyExpiry)
    metrics = Metrics()
    pipeline, provider = runner(provider=FailingProvider(), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(payload(), on_text=discard_text)
    assert caught.value.code == "timeout" and len(provider.calls) == 1
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "cancelled",
            },
        )
        == 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": "provider_error",
            },
        )
        == 0
    )


@pytest.mark.parametrize(
    "case", ["unadvertised", "reused", "disabled", "named", "required", "json"]
)
async def test_final_tool_response_is_checked_against_prepared_request(case):
    request = payload(tools=True, history=case == "reused")
    tool = call(identifier="call_old" if case == "reused" else "call_read")
    if case == "unadvertised":
        tool = call(name="missing")
    elif case == "disabled":
        request = payload(tools=True, choice="none")
    elif case == "named":
        request = request.model_copy(
            update={
                "tools": [definition(), definition("other")],
                "tool_choice": {"type": "function", "function": {"name": "other"}},
            }
        )
    elif case == "required":
        request = payload(tools=True, choice="required")
    elif case == "json":
        tool = tool.model_copy(
            update={
                "function": tool.function.model_copy(
                    update={
                        "arguments": '{"path":',
                    }
                )
            }
        )
    response = (
        ChatResponse(text="missing tool", usage={"input_tokens": 8, "output_tokens": 2})
        if case == "required"
        else ChatResponse.model_construct(
            text="",
            tool_calls=[tool],
            finish_reason="tool_calls",
            usage={"input_tokens": 8, "output_tokens": 2},
        )
    )
    metrics = Metrics()
    pipeline, provider = runner(Prepared(), provider=Provider(response), metrics=metrics)
    chunks = []

    async def on_text(text):
        chunks.append(text)

    with pytest.raises(GatewayError) as caught:
        await pipeline.run_early(request, on_text=on_text)
    assert caught.value.code == "provider_error" and len(provider.calls) == 1
    assert chunks == (["missing tool"] if case == "required" else [])
    assert (
        sample(
            metrics,
            "gateway7_provider_errors_total",
            {
                "provider": "openai",
                "reason": "invalid_response",
            },
        )
        == 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_tokens_total",
            {
                "provider": "openai",
                "direction": "input",
            },
        )
        == 8
    )


async def test_valid_tool_calls_are_returned_only_as_complete_validated_response():
    response = ChatResponse(
        text="",
        tool_calls=[call()],
        finish_reason="tool_calls",
        usage={"input_tokens": 8, "output_tokens": 2},
    )
    pipeline, provider = runner(Prepared(), provider=Provider(response))
    result = await pipeline.run_early(payload(tools=True), on_text=discard_text)
    assert result == response and len(provider.calls) == 1
    assert result is not response and result.usage is not response.usage


@pytest.mark.parametrize("outcome", ["complete", "provider_error"])
async def test_provider_usage_and_attempts_are_accounted_exactly_once(outcome):
    class Failing(Provider):
        async def complete_early(self, request, *, on_text, model=None):
            self.calls.append((request, model))
            raise ProviderError(
                ProviderErrorReason.INVALID_RESPONSE,
                usage={"input_tokens": 8, "output_tokens": 2},
            )

    metrics = Metrics()
    provider = Failing() if outcome == "provider_error" else Provider()
    pipeline, _ = runner(Prepared(), provider=provider, metrics=metrics)
    if outcome == "provider_error":
        with pytest.raises(GatewayError, match="Provider request failed"):
            await pipeline.run_early(payload(), on_text=discard_text)
    else:
        result = await pipeline.run_early(payload(), on_text=discard_text)
        assert result.usage == {"input_tokens": 8, "output_tokens": 2}
    assert len(provider.calls) == 1
    assert (
        sample(
            metrics,
            "gateway7_provider_calls_total",
            {
                "provider": "openai",
                "outcome": outcome,
            },
        )
        == 1
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_tokens_total",
            {
                "provider": "openai",
                "direction": "input",
            },
        )
        == 8
    )
    assert (
        sample(
            metrics,
            "gateway7_provider_tokens_total",
            {
                "provider": "openai",
                "direction": "output",
            },
        )
        == 2
    )
    assert sample(metrics, "gateway7_provider_usage_unknown_total", {"provider": "openai"}) == 0

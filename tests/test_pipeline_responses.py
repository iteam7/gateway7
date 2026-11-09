"""Native Responses policies are explicit and never borrow Chat capabilities."""

import asyncio
import sys
import time
from types import ModuleType

import pytest
from pydantic import BaseModel, ConfigDict

from gateway7.config import GatewayConfig, LimitsConfig
from gateway7.errors import GatewayError, ProviderError, ProviderErrorReason, StartupError
from gateway7.loader import LoadedPlugin, LoadedPlugins, load_plugins
from gateway7.metrics import Metrics
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import Deny, PluginDescriptor, ResponsesContext, ResponsesUnsupported
from gateway7.responses_events import ResponsesStreamHead, ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesRequest, ResponsesResponse


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Legacy:
    async def handle(self, request, context, call_next):
        return await call_next(request)


class Native(Legacy):
    async def prepare_responses(self, request, context):
        return request

    async def check_responses(self, response, context):
        return response

    async def prepare_early_responses(self, request, context):
        return await self.prepare_responses(request, context)


def request(*, consent=ResponsesConsent(), **changes):
    return ResponsesRequest.model_validate(
        {"input": "hello", **changes}, context={"consent": consent}
    )


def response(text="answer", **changes):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_synthetic",
            "created_at": 1800000000,
            "model": "synthetic-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_new",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 8, "output_tokens": 2},
            **changes,
        }
    )


class Provider:
    def __init__(self, result=None):
        self.result = result or response()
        self.calls = []

    async def complete_responses(
        self, request, *, model=None, stream=False, consent=ResponsesConsent()
    ):
        self.calls.append((request, model, stream, consent))
        return self.result

    async def complete_responses_early(
        self, request, *, model=None, consent=ResponsesConsent(), on_text
    ):
        self.calls.append((request, model, True, consent))
        if self.result.output_text:
            await on_text(self.result.output_text)
        return self.result


def loaded(*instances):
    plugins = {}
    for index, instance in enumerate(instances):
        name = "p" + str(index)
        plugins[name] = LoadedPlugin(
            name,
            PluginDescriptor("synthetic", 2, Settings, lambda _: instance),
            instance,
            instance.handle,
            None,
            None,
            prepare_responses=getattr(instance, "prepare_responses", None),
            check_responses=getattr(instance, "check_responses", None),
            prepare_early_responses=getattr(instance, "prepare_early_responses", None),
        )
    return LoadedPlugins(plugins, tuple(plugins.values()))


def runner(*instances, provider=None, metrics=None, limits=None, kind="openai"):
    provider = provider or Provider()
    return Pipeline(
        loaded(*instances), provider, limits or LimitsConfig(), metrics=metrics, provider_name=kind
    ), provider


async def discard_text(text):
    pass


def metric(metrics, name, **labels):
    return metrics.registry.get_sample_value("gateway7_" + name, labels) or 0


@pytest.mark.parametrize(
    "early,missing",
    [
        (False, "prepare_responses"),
        (False, "check_responses"),
        (True, "prepare_responses"),
        (True, "check_responses"),
        (True, "prepare_early_responses"),
    ],
)
async def test_whole_chain_preflight_precedes_all_hooks_and_provider(early, missing):
    events = []

    class First(Native):
        async def prepare_responses(self, request, context):
            events.append("unexpected")
            return request

    second = Native()
    setattr(second, missing, None)
    pipeline, provider = runner(First(), second)
    with pytest.raises(ResponsesUnsupported):
        if early:
            await pipeline.run_responses_early(request(), on_text=discard_text)
        else:
            await pipeline.run_responses(request())
    assert events == [] and provider.calls == []


async def test_native_order_typed_contexts_and_external_routing():
    events, contexts = [], []

    class Ordered(Native):
        def __init__(self, label):
            self.label = label

        async def prepare_responses(self, request, context):
            assert type(request) is ResponsesRequest and type(context) is ResponsesContext
            contexts.append(context)
            context.state["label"] = self.label
            events.append("request:" + self.label)
            return request.model_copy(update={"input": request.input + self.label})

        async def check_responses(self, response, context):
            assert context in contexts and context.state["label"] == self.label
            events.append("response:" + self.label)
            item = response.output[0]
            part = item.content[0].model_copy(update={"text": item.content[0].text + self.label})
            return response.model_copy(
                update={"output": [item.model_copy(update={"content": [part]})]}
            )

        async def handle(self, *args):
            pytest.fail("Native requests must not invoke Chat middleware")

    pipeline, provider = runner(Ordered("A"), Ordered("B"))
    consent = ResponsesConsent(allow_opaque=True)
    result = await pipeline.run_responses(
        request(), "synthetic-order", provider_model="pinned", stream=True, consent=consent
    )
    assert events == ["request:A", "request:B", "response:B", "response:A"]
    assert result.output_text == "answerBA" and result.usage == provider.result.usage
    assert provider.calls[0][0].input == "helloAB"
    assert provider.calls[0][1:] == ("pinned", True, consent)
    assert provider.calls[0][3] is not consent
    assert all(
        context.state == {} and context.request_id == "synthetic-order" for context in contexts
    )
    assert not {"model", "stream", "consent"} & provider.calls[0][0].wire_dict().keys()


@pytest.mark.parametrize(
    "hook_name", ["prepare_responses", "check_responses", "prepare_early_responses"]
)
@pytest.mark.parametrize("invalid", ["sync", "arity", "required_keyword"])
def test_loader_validates_optional_native_signatures(monkeypatch, hook_name, invalid):
    instance = Native()
    if invalid == "sync":

        def hook(value, context):
            return value
    elif invalid == "arity":

        async def hook(value):
            return value
    else:

        async def hook(value, context, *, authority):
            return value

    setattr(instance, hook_name, hook)
    module = ModuleType("synthetic_responses_plugin")
    module.PLUGIN = PluginDescriptor("native", 2, Settings, lambda _: instance)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = GatewayConfig.model_validate(
        {"plugins": {"p": {"module": module.__name__}}, "middleware": ["p"]}
    )
    with pytest.raises(StartupError, match="invalid async hook " + hook_name):
        load_plugins(config)


def test_loader_native_opt_in_and_legacy_absence_are_explicit(monkeypatch):
    for instance in (Native(), Legacy()):
        module = ModuleType("synthetic_responses_plugin")
        module.PLUGIN = PluginDescriptor("native", 2, Settings, lambda _: instance)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        config = GatewayConfig.model_validate(
            {"plugins": {"p": {"module": module.__name__}}, "middleware": ["p"]}
        )
        plugin = load_plugins(config).instances["p"]
        assert plugin.prepare_responses == getattr(instance, "prepare_responses", None)
        assert plugin.check_responses == getattr(instance, "check_responses", None)
        assert plugin.prepare_early_responses == getattr(instance, "prepare_early_responses", None)


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize("kind", ["fake", "claude", "gemini", "missing", "wrong_adapter"])
async def test_only_available_native_openai_capability_can_attempt(early, kind):
    pipeline, provider = runner(
        Native(), kind=kind if kind in ("fake", "claude", "gemini") else "openai"
    )
    if kind == "missing":
        setattr(provider, "complete_responses_early" if early else "complete_responses", None)
    if kind == "wrong_adapter":
        provider._kind = "fake"
    with pytest.raises(ResponsesUnsupported):
        if early:
            await pipeline.run_responses_early(request(), on_text=discard_text)
        else:
            await pipeline.run_responses(request())
    assert provider.calls == []


@pytest.mark.parametrize(
    "authority", ["model", "stream", "consent", "allow_opaque", "allow_hosted"]
)
async def test_request_hook_cannot_inject_transport_authority(authority):
    class Inject(Native):
        async def prepare_responses(self, request, context):
            return request.model_copy(update={authority: True})

    pipeline, provider = runner(Inject())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "plugin_error" and provider.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_output_tokens", 1),
        ("parallel_tool_calls", False),
        ("prompt_cache_key", "new"),
        ("reasoning", {"effort": "high"}),
        ("tools", [{"type": "function", "name": "new", "parameters": {}}]),
    ],
)
async def test_request_hook_cannot_rewrite_protected_controls(field, value):
    class Change(Native):
        async def prepare_responses(self, request, context):
            return request.model_copy(update={field: value})

    pipeline, provider = runner(Change())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "plugin_error" and provider.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "resp_changed"),
        ("model", "changed"),
        ("created_at", 2),
        ("completed_at", 2),
        ("status", "failed"),
        ("usage", {"input_tokens": 0, "output_tokens": 0}),
        ("tools", []),
        ("instructions", "invented"),
        ("metadata", {"new": "value"}),
        ("parallel_tool_calls", False),
        ("max_output_tokens", 1),
        ("output", []),
    ],
)
async def test_response_hook_cannot_rewrite_provider_owned_fields(field, value):
    class Change(Native):
        async def check_responses(self, response, context):
            return response.model_copy(update={field: value})

    metrics = Metrics()
    pipeline, provider = runner(Change(), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "plugin_error" and len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="complete") == 1
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == 8


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": 8},
        {"output_tokens": 2},
        {"input_tokens": 0, "output_tokens": 0},
        {
            "input_tokens": 8,
            "output_tokens": 2,
            "total_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 1},
        },
    ],
)
async def test_actual_usage_is_preserved_once_without_filling_unknown_counts(usage):
    metrics = Metrics()
    pipeline, provider = runner(Native(), provider=Provider(response(usage=usage)), metrics=metrics)
    result = await pipeline.run_responses(request())
    assert result.wire_dict()["usage"] == usage
    known = usage is not None and "input_tokens" in usage and "output_tokens" in usage
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="complete") == 1
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == int(not known)
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == (
        usage["input_tokens"] if known else 0
    )
    assert len(provider.calls) == 1


@pytest.mark.parametrize("phase", ["request", "response"])
async def test_denial_stops_chain_and_clears_native_context(phase):
    contexts = []

    class Denied(Native):
        async def prepare_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return Deny("private") if phase == "request" else request

        async def check_responses(self, response, context):
            return Deny("private")

    metrics = Metrics()
    pipeline, provider = runner(Denied(), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "policy_denied" and caught.value.status_code == 403
    assert "private" not in str(caught.value) and all(context.state == {} for context in contexts)
    assert len(provider.calls) == int(phase == "response")
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="complete") == int(
        phase == "response"
    )


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize("kind", ["opaque", "hosted"])
async def test_consent_is_external_separate_and_default_denied(early, kind):
    all_consent = ResponsesConsent(allow_opaque=True, allow_hosted=True)
    changes = (
        {"input": [{"type": "reasoning", "encrypted_content": "SYNTHETIC"}]}
        if kind == "opaque"
        else {"tools": [{"type": "web_search"}]}
    )
    payload = request(consent=all_consent, **changes)
    wrong_consent = ResponsesConsent(allow_hosted=kind == "opaque", allow_opaque=kind == "hosted")
    pipeline, provider = runner(Native())
    with pytest.raises(GatewayError) as caught:
        if early:
            await pipeline.run_responses_early(payload, consent=wrong_consent, on_text=discard_text)
        else:
            await pipeline.run_responses(payload, consent=wrong_consent)
    assert caught.value.code == "invalid_request" and provider.calls == []
    result = (
        await pipeline.run_responses_early(payload, consent=all_consent, on_text=discard_text)
        if early
        else await pipeline.run_responses(payload, consent=all_consent)
    )
    assert result.output_text == "answer" and len(provider.calls) == 1
    assert provider.calls[0][0].wire_dict() == payload.wire_dict()


@pytest.mark.parametrize("phase", ["request", "response"])
async def test_opaque_bytes_cannot_be_changed_even_with_consent(phase):
    class Change(Native):
        async def prepare_responses(self, request, context):
            if phase != "request":
                return request
            item = request.input[0].model_copy(update={"encrypted_content": "CHANGED"})
            return request.model_copy(update={"input": [item]})

        async def check_responses(self, response, context):
            item = response.output[0].model_copy(update={"encrypted_content": "CHANGED"})
            return response.model_copy(update={"output": [item]})

    consent = ResponsesConsent(allow_opaque=True)
    pipeline, provider = runner(
        Change(),
        provider=Provider(
            response(
                output=[
                    {
                        "type": "reasoning",
                        "id": "rs_new",
                        "encrypted_content": "SYNTHETIC",
                    }
                ]
            )
        ),
    )
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(
            request(
                consent=consent,
                input=[
                    {
                        "type": "reasoning",
                        "encrypted_content": "SYNTHETIC",
                    }
                ],
            ),
            consent=consent,
        )
    assert caught.value.code == "plugin_error" and len(provider.calls) == int(phase == "response")


@pytest.mark.parametrize("phase", ["request", "response"])
@pytest.mark.parametrize("interruption", ["hook_timeout", "deadline", "cancel"])
@pytest.mark.parametrize("replace_error", [False, True])
async def test_resistant_native_hooks_cannot_replace_interruption(
    phase, interruption, replace_error
):
    entered, contexts = asyncio.Event(), []

    class Slow(Native):
        async def work(self, value, context):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if replace_error:
                    raise RuntimeError("synthetic") from None
                return value

        async def prepare_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return await self.work(request, context) if phase == "request" else request

        async def check_responses(self, response, context):
            return await self.work(response, context)

    limits = LimitsConfig(
        hook_timeout_seconds=0.01 if interruption == "hook_timeout" else 1,
        request_timeout_seconds=0.01 if interruption == "deadline" else 1,
    )
    pipeline, provider = runner(Slow(), limits=limits)
    task = asyncio.create_task(pipeline.run_responses(request()))
    await entered.wait()
    if interruption == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    assert len(provider.calls) == int(phase == "response")
    assert all(context.state == {} for context in contexts)


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize("interruption", ["deadline", "cancel"])
async def test_provider_error_cannot_replace_interruption_and_counts_once(early, interruption):
    entered = asyncio.Event()

    class Failing(Provider):
        async def fail(self, request, **options):
            self.calls.append(request)
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise ProviderError(
                    ProviderErrorReason.TRANSPORT, usage={"input_tokens": 8, "output_tokens": 2}
                ) from None

        complete_responses = fail
        complete_responses_early = fail

    metrics = Metrics()
    pipeline, provider = runner(
        Native(),
        provider=Failing(),
        metrics=metrics,
        limits=LimitsConfig(request_timeout_seconds=0.01 if interruption == "deadline" else 1),
    )
    task = asyncio.create_task(
        pipeline.run_responses_early(request(), on_text=discard_text)
        if early
        else pipeline.run_responses(request())
    )
    await entered.wait()
    if interruption == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    assert len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="cancelled") == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 0
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == 1


async def test_early_text_waits_for_complete_request_chain_and_never_calls_response_hooks():
    events = []

    class Prepared(Native):
        async def prepare_early_responses(self, request, context):
            events.append(context.instance_name)
            return request

        async def check_responses(self, response, context):
            pytest.fail("Native early mode cannot claim response policy enforcement")

    pipeline, provider = runner(Prepared(), Prepared())

    async def on_text(text):
        assert events == ["p0", "p1"] and len(provider.calls) == 1
        events.append(text)

    result = await pipeline.run_responses_early(request(), on_text=on_text)
    assert events == ["p0", "p1", "answer"] and result.output_text == "answer"


async def test_hook_budget_excludes_provider_wait_but_is_shared_across_native_phases():
    class Wait(Provider):
        async def complete_responses(self, request, **options):
            await asyncio.sleep(0.04)
            return await super().complete_responses(request, **options)

    pipeline, _ = runner(Native(), provider=Wait(), limits=LimitsConfig(hook_timeout_seconds=0.02))
    assert (await pipeline.run_responses(request())).output_text == "answer"

    class Slow(Native):
        async def prepare_responses(self, request, context):
            await asyncio.sleep(0.02)
            return request

        async def check_responses(self, response, context):
            await asyncio.sleep(0.02)
            return response

    pipeline, provider = runner(Slow(), limits=LimitsConfig(hook_timeout_seconds=0.03))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "timeout" and len(provider.calls) == 1


@pytest.mark.parametrize("early", [False, True])
async def test_native_parallel_namespace_custom_reasoning_order_and_raw_bytes_survive(early):
    consent = ResponsesConsent(allow_opaque=True)
    function = {"type": "function", "name": "read", "parameters": {"type": "object"}}
    custom = {
        "type": "custom",
        "name": "patch",
        "format": {
            "type": "grammar",
            "syntax": "lark",
            "definition": "start: /.+/",
        },
    }
    tools = [
        {"type": "namespace", "name": name, "description": "tools", "tools": [function]}
        for name in ("alpha", "beta")
    ] + [custom]

    def function_call(suffix, namespace):
        return {
            "type": "function_call",
            "id": "item_" + suffix,
            "call_id": "call_" + suffix,
            "name": "read",
            "namespace": namespace,
            "arguments": ' {"path": "synthetic.txt"} ',
        }

    output = [
        {
            "type": "reasoning",
            "id": "rs_new",
            "summary": [{"type": "summary_text", "text": "summary"}],
            "content": [{"type": "reasoning_text", "text": "reasoning"}],
            "encrypted_content": "SYNTHETIC==",
        },
        function_call("a", "alpha"),
        function_call("b", "beta"),
        {
            "type": "custom_tool_call",
            "id": "custom_new",
            "call_id": "call_patch",
            "name": "patch",
            "input": "*** Begin Patch\n+synthetic\n*** End Patch\n",
        },
        {
            "type": "message",
            "id": "msg_new",
            "role": "assistant",
            "phase": "final_answer",
            "content": [{"type": "output_text", "text": "done"}],
        },
    ]
    answer = response(output=output)
    pipeline, provider = runner(Native(), provider=Provider(answer))
    original = request(
        consent=consent,
        tools=tools,
        parallel_tool_calls=True,
        reasoning={"effort": "high"},
        max_output_tokens=4096,
    )
    chunks = []

    async def on_text(text):
        chunks.append(text)

    result = (
        await pipeline.run_responses_early(original, consent=consent, on_text=on_text)
        if early
        else await pipeline.run_responses(original, consent=consent)
    )
    assert result.wire_dict() == answer.wire_dict()
    assert provider.calls[0][0].wire_dict() == original.wire_dict()
    assert chunks == (["done"] if early else [])


@pytest.mark.parametrize("change", ["name", "call_id", "id", "arguments", "remove", "reorder"])
async def test_response_hooks_cannot_change_native_calls_or_output_order(change):
    function = {"type": "function", "name": "read", "parameters": {}}
    output = [
        {
            "type": "function_call",
            "id": "item_" + suffix,
            "call_id": "call_" + suffix,
            "name": "read",
            "arguments": "{}",
        }
        for suffix in ("a", "b")
    ]

    class Change(Native):
        async def check_responses(self, response, context):
            if change == "remove":
                return response.model_copy(update={"output": response.output[1:]})
            if change == "reorder":
                return response.model_copy(update={"output": list(reversed(response.output))})
            first = response.output[0].model_copy(
                update={change: '{"new":true}' if change == "arguments" else "changed"}
            )
            return response.model_copy(update={"output": [first, response.output[1]]})

    pipeline, provider = runner(Change(), provider=Provider(response(output=output)))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request(tools=[function]))
    assert caught.value.code == "plugin_error" and len(provider.calls) == 1


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": 8},
        {"output_tokens": 2},
        {"input_tokens": 8, "output_tokens": 2},
        {"total_tokens": 10},
    ],
)
@pytest.mark.parametrize(
    "violation",
    ["unadvertised", "reused", "disabled", "parallel", "required", "malformed", "terminal"],
)
async def test_provider_contract_is_checked_before_any_response_hook(early, usage, violation):
    events, contexts = [], []

    class Inspect(Native):
        async def prepare_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return request

        async def check_responses(self, response, context):
            events.append("unexpected")
            return response

    function = {"type": "function", "name": "read", "parameters": {}}
    original = request(tools=[function])
    output = [
        {
            "type": "function_call",
            "id": "item_new",
            "call_id": "call_new",
            "name": "read",
            "arguments": "{}",
        }
    ]
    if violation == "unadvertised":
        output[0]["name"] = "missing"
    elif violation == "reused":
        original = request(
            tools=[function],
            input=[
                {**output[0]},
                {
                    "type": "function_call_output",
                    "call_id": "call_new",
                    "output": "safe",
                },
            ],
        )
    elif violation == "disabled":
        original = request(tools=[function], tool_choice="none")
    elif violation == "parallel":
        original = request(tools=[function], parallel_tool_calls=False)
        output.append({**output[0], "id": "item_second", "call_id": "call_second"})
    elif violation == "required":
        original = request(tools=[function], tool_choice="required")
        output = []
    answer = response(output=output, usage=usage)
    if violation == "malformed":
        answer.output[0].__dict__["arguments"] = '{"path":'
    elif violation == "terminal":
        answer = answer.model_copy(update={"status": "in_progress"})
    metrics = Metrics()
    pipeline, provider = runner(Inspect(), provider=Provider(answer), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        if early:
            await pipeline.run_responses_early(original, on_text=discard_text)
        else:
            await pipeline.run_responses(original)
    assert caught.value.code == "provider_error" and events == [] and len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 1
    assert (
        metric(metrics, "provider_errors_total", provider="openai", reason="invalid_response") == 1
    )
    known_pair = (
        violation not in ("malformed", "terminal")
        and usage is not None
        and all(name in usage for name in ("input_tokens", "output_tokens"))
    )
    # Existing metrics require both reported directions; never synthesize a missing count.
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == int(not known_pair)
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == (
        8 if known_pair else 0
    )
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="output") == (
        2 if known_pair else 0
    )
    if not known_pair:
        for direction in ("input", "output"):
            assert (
                metrics.registry.get_sample_value(
                    "gateway7_provider_tokens_total",
                    {
                        "provider": "openai",
                        "direction": direction,
                    },
                )
                is None
            )
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="complete") == 0
    assert all(context.state == {} for context in contexts)


@pytest.mark.parametrize("interruption", ["synchronous", "callback_error", "callback_cancel"])
async def test_early_callback_cannot_forward_late_or_replace_interruption(interruption):
    entered = asyncio.Event()

    async def on_text(text):
        entered.set()
        if interruption == "synchronous":
            time.sleep(0.03)
            raise RuntimeError("synthetic")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError("synthetic") from None

    metrics = Metrics()
    pipeline, provider = runner(
        Native(),
        metrics=metrics,
        limits=LimitsConfig(
            request_timeout_seconds=1 if interruption == "callback_cancel" else 0.01
        ),
    )
    task = asyncio.create_task(pipeline.run_responses_early(request(), on_text=on_text))
    await entered.wait()
    if interruption == "callback_cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    assert len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="cancelled") == 1
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == 1


@pytest.mark.parametrize("phase", ["request", "response"])
async def test_synchronous_native_hook_deadline_is_terminal(phase):
    class Slow(Native):
        async def prepare_responses(self, request, context):
            if phase == "request":
                time.sleep(0.03)
            return request

        async def check_responses(self, response, context):
            time.sleep(0.03)
            return response

    pipeline, provider = runner(Slow(), limits=LimitsConfig(hook_timeout_seconds=0.01))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "timeout" and len(provider.calls) == int(phase == "response")


async def test_early_total_timer_expiry_precedes_provider_failure(monkeypatch):
    timeout_at = asyncio.timeout_at

    class EarlyExpiry:
        def __init__(self, when):
            self.inner = timeout_at(when)

        async def __aenter__(self):
            return await self.inner.__aenter__()

        async def __aexit__(self, *args):
            return await self.inner.__aexit__(*args)

        def expired(self):
            return True

    monkeypatch.setattr(asyncio, "timeout_at", EarlyExpiry)
    pipeline, provider = runner()
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "timeout" and provider.calls == []


async def test_failed_hosted_search_with_completed_fallback_is_preserved():
    consent = ResponsesConsent(allow_hosted=True)
    answer = response(
        output=[
            {"type": "web_search_call", "id": "web_new", "status": "failed"},
            {
                "type": "message",
                "id": "msg_new",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "fallback"}],
            },
        ]
    )
    pipeline, _ = runner(Native(), provider=Provider(answer))
    result = await pipeline.run_responses(
        request(consent=consent, tools=[{"type": "web_search"}]), consent=consent
    )
    assert result.wire_dict() == answer.wire_dict()


@pytest.mark.parametrize("phase", ["request", "response"])
@pytest.mark.parametrize(
    "failure",
    [None, "wrong_type", "exception", "gateway_error", "extra", "hidden_control", "nested_extra"],
)
async def test_untrusted_native_hook_edits_fail_closed_without_serializer_disclosure(
    phase, failure, recwarn
):
    contexts = []
    sentinel = "synthetic-private-native-sentinel"

    class Invalid(Native):
        def alter(self, value):
            if failure is None:
                return None
            if failure == "wrong_type":
                return request() if phase == "response" else response()
            if failure == "exception":
                raise RuntimeError(sentinel)
            if failure == "gateway_error":
                raise GatewayError("provider_error")
            if failure == "extra":
                value = value.model_copy(update={"unexpected": sentinel})
                value.__pydantic_fields_set__.discard("unexpected")
            elif failure == "hidden_control":
                field = "store" if phase == "request" else "background"
                value = value.model_copy(update={field: True})
                value.__pydantic_fields_set__.discard(field)
            elif failure == "nested_extra":
                if phase == "request":
                    value.tools[0].__dict__["unexpected"] = sentinel
                else:
                    value.output[0].content[0].__dict__["unexpected"] = sentinel
            return value

        async def prepare_responses(self, request, context):
            contexts.append(context)
            context.state["secret"] = sentinel
            return self.alter(request) if phase == "request" else request

        async def check_responses(self, response, context):
            return self.alter(response)

    pipeline, provider = runner(Invalid())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(
            request(tools=[{"type": "function", "name": "read", "parameters": {}}])
        )
    assert caught.value.code == "plugin_error" and sentinel not in str(caught.value)
    assert len(provider.calls) == int(phase == "response")
    assert all(context.state == {} for context in contexts)
    assert not recwarn.list


@pytest.mark.parametrize(
    "forgery",
    [
        "usage_type",
        "nested_extra",
        "hidden_extra",
        "hidden_control",
        "negative_count",
        "inconsistent_total",
    ],
)
async def test_rejected_provider_dto_usage_is_never_read_or_serialized(
    monkeypatch, recwarn, forgery
):
    raw = response()
    if forgery == "usage_type":
        raw = raw.model_copy(update={"usage": "synthetic-private-native-sentinel"})
    elif forgery == "nested_extra":
        raw.output[0].content[0].__dict__["private"] = "synthetic-private-native-sentinel"
    elif forgery == "hidden_extra":
        raw = raw.model_copy(update={"private": "synthetic-private-native-sentinel"})
        raw.__pydantic_fields_set__.discard("private")
    elif forgery == "hidden_control":
        raw = raw.model_copy(update={"background": True})
        raw.__pydantic_fields_set__.discard("background")
    else:
        field, value = ("input_tokens", -1) if forgery == "negative_count" else ("total_tokens", 99)
        raw.usage.__dict__[field] = value
        raw.usage.__pydantic_fields_set__.discard(field)

    def unsafe_usage(self):
        pytest.fail("Rejected DTO accounting must not be read before strict validation")

    monkeypatch.setattr(ResponsesResponse, "accounting_usage", unsafe_usage)
    metrics = Metrics()
    pipeline, provider = runner(Native(), provider=Provider(raw), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "provider_error" and len(provider.calls) == 1
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 1
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == 0
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="output") == 0
    assert not recwarn.list


async def test_contract_rejection_after_deadline_does_not_count_snapshotted_usage(monkeypatch):
    import gateway7.pipeline as pipeline_module

    def late_rejection(*args, **kwargs):
        time.sleep(0.03)
        raise ValueError("synthetic final contract rejection")

    monkeypatch.setattr(pipeline_module, "validate_response", late_rejection)
    metrics = Metrics()
    pipeline, provider = runner(
        Native(), metrics=metrics, limits=LimitsConfig(request_timeout_seconds=0.01)
    )
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "timeout" and len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="cancelled") == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 0
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == 1
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == 0


@pytest.mark.parametrize("usage", [None, {"input_tokens": 8, "output_tokens": 2}])
async def test_provider_errors_preserve_only_actual_sanitized_accounting_once(usage):
    class Failing(Provider):
        async def complete_responses(self, request, **options):
            self.calls.append(request)
            raise ProviderError(ProviderErrorReason.INVALID_RESPONSE, usage=usage)

    metrics = Metrics()
    pipeline, provider = runner(Native(), provider=Failing(), metrics=metrics)
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request())
    assert caught.value.code == "provider_error" and len(provider.calls) == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 1
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == int(usage is None)
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == (
        8 if usage else 0
    )


async def test_native_consent_snapshot_cannot_be_changed_through_original_reference():
    consent = ResponsesConsent()

    class Escalate(Native):
        async def prepare_responses(self, request, context):
            object.__setattr__(consent, "allow_opaque", True)
            assert not hasattr(context, "consent")
            return request

    raw = response(output=[{"type": "reasoning", "id": "rs_new", "encrypted_content": "SYNTHETIC"}])
    pipeline, provider = runner(Escalate(), provider=Provider(raw))
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses(request(), consent=consent)
    assert caught.value.code == "provider_error" and len(provider.calls) == 1
    assert provider.calls[0][3].allow_opaque is False


@pytest.mark.parametrize(
    "on_text,stream,expected",
    [(None, True, GatewayError), (discard_text, False, ResponsesUnsupported)],
)
async def test_early_runner_never_silently_switches_to_buffered_mode(on_text, stream, expected):
    pipeline, provider = runner(Native())
    with pytest.raises(expected):
        await pipeline.run_responses_early(request(), on_text=on_text, stream=stream)
    assert provider.calls == []


@pytest.mark.parametrize(
    "callbacks",
    [
        {},
        {"on_text": None},
        {"on_text_delta": None},
        {"on_text": discard_text, "on_text_delta": discard_text},
        {"on_text": "invalid"},
        {"on_text_delta": "invalid"},
    ],
)
async def test_native_early_requires_exactly_one_callable_sink_before_provider(callbacks):
    pipeline, provider = runner(Native())
    with pytest.raises(GatewayError) as caught:
        await pipeline.run_responses_early(request(), **callbacks)
    assert caught.value.code == "invalid_request" and provider.calls == []


async def test_structured_sink_does_not_bypass_native_early_hook_preflight():
    plugin = Native()
    plugin.prepare_early_responses = None
    pipeline, provider = runner(plugin)

    async def on_text_delta(record):
        pytest.fail("Incompatible middleware must not emit a record")

    with pytest.raises(ResponsesUnsupported):
        await pipeline.run_responses_early(request(), on_text_delta=on_text_delta)
    assert provider.calls == []


def text_record(text="answer", sequence=1):
    return ResponsesTextDelta(
        head=ResponsesStreamHead(
            id="resp_synthetic",
            created_at=1800000000,
            model="synthetic-model",
            parallel_tool_calls=True,
        ),
        sequence_number=sequence,
        item_id="msg_new",
        output_index=0,
        content_index=0,
        phase="final_answer",
        delta=text,
        leading_prefix=True,
    )


@pytest.mark.parametrize("structured", [False, True])
async def test_native_early_sinks_preserve_record_identity_and_apply_backpressure(structured):
    entered, release = asyncio.Event(), asyncio.Event()
    events, received, contexts = [], [], []
    records = [text_record("ans", 1), text_record("wer", 2)]
    before = [record.model_dump() for record in records]

    class Prepared(Native):
        async def prepare_early_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            events.append(context.instance_name)
            return request

        async def check_responses(self, response, context):
            pytest.fail("Early text cannot silently invoke response processing")

    class Streaming(Provider):
        async def complete_responses_early(self, request, **options):
            assert set(options) == {
                "model",
                "consent",
                "on_text_delta" if structured else "on_text",
            }
            assert options["model"] == "pinned-model"
            self.calls.append((request, options))
            sink = options["on_text_delta" if structured else "on_text"]
            events.append("provider")
            await sink(records[0] if structured else records[0].delta)
            events.append("read-next")
            await sink(records[1] if structured else records[1].delta)
            return self.result

    metrics = Metrics()
    pipeline, provider = runner(
        Prepared(),
        Prepared(),
        provider=Streaming(),
        metrics=metrics,
        limits=LimitsConfig(hook_timeout_seconds=0.01),
    )

    async def sink(value):
        received.append(value)
        if len(received) == 1:
            entered.set()
            await release.wait()

    callbacks = {"on_text_delta" if structured else "on_text": sink}
    task = asyncio.create_task(
        pipeline.run_responses_early(request(), provider_model="pinned-model", **callbacks)
    )
    await asyncio.wait_for(entered.wait(), 1)
    assert events == ["p0", "p1", "provider"] and not task.done()
    release.set()
    result = await task
    assert events == ["p0", "p1", "provider", "read-next"]
    if structured:
        assert all(actual is original for actual, original in zip(received, records, strict=True))
    else:
        assert received == ["ans", "wer"]
    assert [record.model_dump() for record in records] == before
    assert len(provider.calls) == 1 and all(context.state == {} for context in contexts)
    assert result.wire_dict() == provider.result.wire_dict()
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="complete") == 1
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == 8
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="output") == 2


@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("error_type", [RuntimeError, ProviderError, asyncio.CancelledError])
async def test_sink_exception_identity_reaches_provider_with_existing_pipeline_mapping(
    structured, error_type
):
    original = (
        ProviderError(
            ProviderErrorReason.INVALID_RESPONSE, usage={"input_tokens": 8, "output_tokens": 2}
        )
        if error_type is ProviderError
        else error_type("synthetic sink failure")
    )
    seen, contexts = [], []

    class Prepared(Native):
        async def prepare_early_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return request

    class Streaming(Provider):
        async def complete_responses_early(self, request, **options):
            self.calls.append(request)
            try:
                await options["on_text_delta" if structured else "on_text"](
                    text_record() if structured else "answer"
                )
            except BaseException as error:
                seen.append(error)
                raise

    async def sink(value):
        raise original

    metrics = Metrics()
    pipeline, provider = runner(Prepared(), provider=Streaming(), metrics=metrics)
    with pytest.raises(
        asyncio.CancelledError if error_type is asyncio.CancelledError else GatewayError
    ) as caught:
        await pipeline.run_responses_early(
            request(), **{"on_text_delta" if structured else "on_text": sink}
        )
    assert seen == [original] and seen[0] is original
    if error_type is asyncio.CancelledError:
        assert caught.value is original
    else:
        assert caught.value.code == "provider_error"
    assert len(provider.calls) == 1 and all(context.state == {} for context in contexts)
    outcome = "cancelled" if error_type is asyncio.CancelledError else "provider_error"
    assert metric(metrics, "provider_calls_total", provider="openai", outcome=outcome) == 1
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == int(
        error_type is not ProviderError
    )
    assert metric(metrics, "provider_tokens_total", provider="openai", direction="input") == (
        8 if error_type is ProviderError else 0
    )


@pytest.mark.parametrize("interruption", ["deadline", "synchronous", "cancel"])
async def test_structured_sink_error_cannot_replace_cancellation_or_deadline(interruption):
    entered, contexts, seen = asyncio.Event(), [], []
    original = RuntimeError("synthetic sink failure")

    class Prepared(Native):
        async def prepare_early_responses(self, request, context):
            contexts.append(context)
            context.state["synthetic"] = True
            return request

    class Streaming(Provider):
        async def complete_responses_early(self, request, *, on_text_delta, **options):
            self.calls.append(request)
            try:
                await on_text_delta(text_record())
            except RuntimeError as error:
                seen.append(error)
                raise

    async def sink(record):
        entered.set()
        if interruption == "synchronous":
            time.sleep(0.03)
        else:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        raise original

    metrics = Metrics()
    pipeline, provider = runner(
        Prepared(),
        provider=Streaming(),
        metrics=metrics,
        limits=LimitsConfig(request_timeout_seconds=1 if interruption == "cancel" else 0.01),
    )
    task = asyncio.create_task(pipeline.run_responses_early(request(), on_text_delta=sink))
    await asyncio.wait_for(entered.wait(), 1)
    if interruption == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    assert seen == [original] and seen[0] is original
    assert len(provider.calls) == 1 and all(context.state == {} for context in contexts)
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="cancelled") == 1
    assert metric(metrics, "provider_calls_total", provider="openai", outcome="provider_error") == 0
    assert metric(metrics, "provider_usage_unknown_total", provider="openai") == 1


def _protected_schema_http_provider(sent):
    import json

    import httpx

    from gateway7.config import ProviderConfig
    from gateway7.providers import HTTPProvider

    def handle(http_request):
        body = json.loads(http_request.content)
        sent.append(body)
        part = {"type": "output_text", "text": "answer", "annotations": []}
        item = {
            "type": "message",
            "id": "msg_schema",
            "role": "assistant",
            "phase": "final_answer",
            "status": "completed",
            "content": [part],
        }
        final = {
            "id": "resp_schema",
            "object": "response",
            "created_at": 1800000000.0,
            "model": "synthetic-model",
            "status": "completed",
            "output": [item],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": body["tools"],
            "usage": {"input_tokens": 8, "output_tokens": 2},
            "error": None,
            "incomplete_details": None,
        }
        if not body["stream"]:
            return httpx.Response(200, json=final)
        initial = {**final, "status": "in_progress", "output": [], "usage": None}
        refs = {"output_index": 0, "item_id": "msg_schema", "content_index": 0}
        events = [
            {"type": "response.created", "response": initial},
            {"type": "response.in_progress", "response": initial},
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {**item, "status": "in_progress", "content": []},
            },
            {"type": "response.content_part.added", **refs, "part": {**part, "text": ""}},
            {"type": "response.output_text.delta", **refs, "delta": "answer", "logprobs": []},
            {"type": "response.output_text.done", **refs, "text": "answer", "logprobs": []},
            {"type": "response.content_part.done", **refs, "part": part},
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": final},
        ]
        encoded = b"".join(
            (
                "event: "
                + event["type"]
                + "\ndata: "
                + json.dumps({**event, "sequence_number": index})
                + "\n\n"
            ).encode()
            for index, event in enumerate(events)
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=encoded)

    return HTTPProvider(
        ProviderConfig(kind="openai", model="synthetic-model"),
        "gateway7-synthetic-schema-test",
        transport=httpx.MockTransport(handle),
    )


@pytest.mark.parametrize("early", [False, True], ids=["buffered", "typed-early"])
@pytest.mark.parametrize(
    "before,after",
    [(True, 1), (False, 0), (1, 1.0)],
    ids=["true-to-one", "false-to-zero", "integer-to-float"],
)
@pytest.mark.parametrize("nested_list", [False, True], ids=["nested-object", "nested-array"])
async def test_protected_json_primitive_types_rejected_before_http(
    early, before, after, nested_list
):
    field = {"type": "boolean" if type(before) is bool else "integer"}
    field.update({"allOf": [{"const": before}]} if nested_list else {"const": before})
    schema = {"type": "object", "properties": {"flag": field}}

    class Change(Native):
        async def prepare_responses(self, incoming, context):
            target = incoming.tools[0].parameters["properties"]["flag"]
            if nested_list:
                target = target["allOf"][0]
            target["const"] = after
            return incoming

    sent = []
    provider = _protected_schema_http_provider(sent)
    pipeline = Pipeline(loaded(Change()), provider, LimitsConfig(), provider_name="openai")
    incoming = request(tools=[{"type": "function", "name": "read", "parameters": schema}])

    async def sink(record):
        pytest.fail("Protected schema edits must be rejected before any early text")

    try:
        with pytest.raises(GatewayError) as caught:
            if early:
                await pipeline.run_responses_early(incoming, on_text_delta=sink)
            else:
                await pipeline.run_responses(incoming)
        assert caught.value.code == "plugin_error"
        assert sent == []
    finally:
        await provider.aclose()


@pytest.mark.parametrize("early", [False, True], ids=["buffered", "typed-early"])
@pytest.mark.parametrize("edit", ["free-text", "key-order", "both"])
async def test_protected_json_allows_free_text_and_object_key_order(early, edit):
    schema = {
        "type": "object",
        "properties": {"flag": {"type": "boolean", "const": True}},
        "required": ["flag"],
        "additionalProperties": False,
    }

    def reordered(value):
        if isinstance(value, dict):
            return {key: reordered(child) for key, child in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reordered(child) for child in value]
        return value

    class Change(Native):
        async def prepare_responses(self, incoming, context):
            changes = {}
            if edit in ("free-text", "both"):
                changes["input"] = "sanitized"
            if edit in ("key-order", "both"):
                tool = incoming.tools[0]
                changes["tools"] = [
                    tool.model_copy(update={"parameters": reordered(tool.parameters)})
                ]
            return incoming.model_copy(update=changes)

    sent, records = [], []
    provider = _protected_schema_http_provider(sent)
    pipeline = Pipeline(loaded(Change()), provider, LimitsConfig(), provider_name="openai")
    incoming = request(tools=[{"type": "function", "name": "read", "parameters": schema}])

    async def sink(record):
        assert type(record) is ResponsesTextDelta
        records.append(record)

    try:
        result = (
            await pipeline.run_responses_early(incoming, on_text_delta=sink)
            if early
            else await pipeline.run_responses(incoming)
        )
        assert len(sent) == 1
        assert sent[0]["input"] == ("sanitized" if edit in ("free-text", "both") else "hello")
        assert sent[0]["tools"][0]["parameters"] == schema
        assert sent[0]["tools"][0]["parameters"]["properties"]["flag"]["const"] is True
        assert sent[0]["tools"][0]["parameters"]["additionalProperties"] is False
        assert result.output_text == "answer"
        assert result.accounting_usage() == {"input_tokens": 8, "output_tokens": 2}
        assert "".join(record.delta for record in records) == ("answer" if early else "")
    finally:
        await provider.aclose()

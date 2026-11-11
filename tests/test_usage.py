"""Operator capability and client accounting use synthetic identities and data."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway7.app import create_app
from gateway7.auth import AccessControl
from gateway7.config import GatewayConfig, LimitsConfig, ProviderConfig
from gateway7.errors import (
    GatewayError,
    ProviderError,
    ProviderErrorReason,
    StartupError,
    retain_observed_usage,
)
from gateway7.loader import load_plugins
from gateway7.metrics import Metrics
from gateway7.models import ChatRequest, ChatResponse, Message
from gateway7.pipeline import Pipeline
from gateway7.providers import build_provider
from gateway7.responses_models import ResponsesRequest, ResponsesResponse, ResponsesUsage
from gateway7.responses_provider import ResponsesProviderError
from gateway7.usage import OperatorAccess, UsageLedger

OPERATOR = "synthetic-operator-usage-credential"
CLIENT_A = "synthetic-usage-client-a-credential"
CLIENT_B = "synthetic-usage-client-b-credential"
KEY = "synthetic-provider-usage-credential"
TEXT = "synthetic-private-conversation-usage"
MODES = ("chat", "early_chat", "responses", "early_responses")
CHAT = ChatRequest(messages=[Message(role="user", content=TEXT)])
NATIVE = ResponsesRequest(input=TEXT)


def configuration(*, operator=True, plugins=None, middleware=None):
    return GatewayConfig.model_validate(
        {
            "provider": {"kind": "fake", "model": "fake"},
            "auth": {
                "enabled": True,
                **({"operator_token_env": "TEST_USAGE_OPERATOR"} if operator else {}),
                "clients": {
                    "usage_client_a": {"token_env": "TEST_USAGE_A", "models": ["fake"]},
                    "usage_client_b": {"token_env": "TEST_USAGE_B", "models": ["fake"]},
                },
            },
            "plugins": plugins or {},
            "middleware": middleware or [],
        }
    )


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", KEY)
    monkeypatch.setenv("TEST_USAGE_A", CLIENT_A)
    monkeypatch.setenv("TEST_USAGE_B", CLIENT_B)
    monkeypatch.setenv("TEST_USAGE_OPERATOR", OPERATOR)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "short",
        "contains whitespace",
        "x" * 513,
        "non-ascii-ключ",
        CLIENT_A,
        CLIENT_B,
        KEY,
    ],
)
def test_invalid_or_reused_operator_credentials_fail_without_echoing_values(
    credentials, monkeypatch, value
):
    if value is None:
        monkeypatch.delenv("TEST_USAGE_OPERATOR")
    else:
        monkeypatch.setenv("TEST_USAGE_OPERATOR", value)
    with pytest.raises(StartupError) as caught:
        OperatorAccess(configuration())
    if value:
        assert value not in str(caught.value)


def test_operator_access_requires_authenticated_clients_and_stores_only_a_digest(credentials):
    with pytest.raises(ValidationError):
        GatewayConfig.model_validate({"auth": {"operator_token_env": "TEST_USAGE_OPERATOR"}})
    config = configuration()
    operator = OperatorAccess(config)
    assert operator.enabled
    assert all(value not in repr(vars(operator)) for value in (OPERATOR, CLIENT_A, CLIENT_B, KEY))
    operator.authenticate([(b"authorization", ("bEaReR " + OPERATOR).encode())])
    with pytest.raises(GatewayError, match="Missing or invalid"):
        AccessControl(config).authenticate([(b"authorization", ("Bearer " + OPERATOR).encode())])


def test_ledger_is_bounded_detached_and_counts_each_known_direction_independently():
    ledger = UsageLedger(["usage_client_a", "usage_client_b"])
    observe = ledger.observer("usage_client_a")
    observe("complete", {"input_tokens": 4, "output_tokens": 2})
    observe("provider_error", {"input_tokens": 3})
    observe("cancelled", {"input_tokens": True, "output_tokens": 5, TEXT: 999})
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row == {
        "provider_attempts": 3,
        "outcomes": {"complete": 1, "provider_error": 1, "cancelled": 1},
        "known_input_tokens": 7,
        "known_output_tokens": 7,
        "input_usage_unknown_attempts": 1,
        "output_usage_unknown_attempts": 1,
    }
    row["outcomes"]["complete"] = 999
    assert ledger.snapshot()["clients"]["usage_client_a"]["outcomes"]["complete"] == 1
    with pytest.raises(ValueError):
        ledger.observer(TEXT)
    assert set(ledger.snapshot()["clients"]) == {"usage_client_a", "usage_client_b"}
    assert TEXT not in json.dumps(ledger.snapshot())
    assert (
        UsageLedger(["usage_client_a"]).snapshot()["clients"]["usage_client_a"]["provider_attempts"]
        == 0
    )
    with pytest.raises(ValueError):
        UsageLedger([f"client_{index}" for index in range(129)])


def test_concurrent_observations_are_counted_once_without_registering_events():
    ledger = UsageLedger(["usage_client_a"])
    observe = ledger.observer("usage_client_a")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: observe("complete", {"input_tokens": 1, "output_tokens": 2}), range(200)
            )
        )
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row["provider_attempts"] == row["outcomes"]["complete"] == 200
    assert row["known_input_tokens"] == 200 and row["known_output_tokens"] == 400


def native_response(usage, text=TEXT):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_usage_fixture",
            "created_at": 1,
            "model": "fake",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_usage_fixture",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": usage,
        }
    )


class AccountingProvider:
    def __init__(self, *, outcome="complete", usage=None, text=TEXT):
        self.outcome = outcome
        self.usage = usage
        self.text = text
        self.calls = 0

    def result(self, *, native=False):
        self.calls += 1
        if self.outcome == "cancelled":
            error = asyncio.CancelledError("synthetic provider cancellation")
            if native:
                error.responses_usage = (
                    ResponsesUsage.model_validate(self.usage) if self.usage is not None else None
                )
            else:
                retain_observed_usage(error, self.usage)
            raise error
        if self.outcome == "provider_error":
            if native:
                raise ResponsesProviderError(
                    ProviderErrorReason.TRANSPORT,
                    usage=ResponsesUsage.model_validate(self.usage)
                    if self.usage is not None
                    else None,
                )
            raise ProviderError(ProviderErrorReason.TRANSPORT, usage=self.usage)
        return (
            native_response(self.usage, self.text)
            if native
            else ChatResponse(text=self.text, usage=self.usage)
        )

    async def complete(self, request, **options):
        return self.result()

    async def complete_early(self, request, *, on_text, **options):
        return self.result()

    async def complete_responses(self, request, **options):
        return self.result(native=True)

    async def complete_responses_early(
        self, request, *, on_text=None, on_text_delta=None, **options
    ):
        return self.result(native=True)

    async def aclose(self):
        pass


async def run_mode(pipeline, mode):
    async def discard(_):
        pass

    if mode == "chat":
        return await pipeline.run(CHAT, "synthetic-usage-request")
    if mode == "early_chat":
        return await pipeline.run_early(CHAT, "synthetic-usage-request", on_text=discard)
    if mode == "responses":
        return await pipeline.run_responses(NATIVE, "synthetic-usage-request")
    return await pipeline.run_responses_early(NATIVE, "synthetic-usage-request", on_text=discard)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("outcome", ["complete", "provider_error", "cancelled"])
async def test_all_pipeline_modes_record_one_provider_attempt_even_without_metrics(mode, outcome):
    ledger = UsageLedger(["usage_client_a"])
    provider = AccountingProvider(outcome=outcome, usage={"input_tokens": 7, "output_tokens": 3})
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError, match="synthetic provider cancellation"):
            await run_mode(pipeline, mode)
    elif outcome == "provider_error":
        with pytest.raises(GatewayError):
            await run_mode(pipeline, mode)
    else:
        await run_mode(pipeline, mode)
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert provider.calls == row["provider_attempts"] == row["outcomes"][outcome] == 1
    assert sum(row["outcomes"].values()) == 1
    assert row["known_input_tokens"] == 7 and row["known_output_tokens"] == 3
    assert row["input_usage_unknown_attempts"] == row["output_usage_unknown_attempts"] == 0


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("usage", [None, {"input_tokens": 7}, {"output_tokens": 3}])
async def test_pipeline_preserves_independent_known_and_unknown_directions(mode, usage):
    ledger = UsageLedger(["usage_client_a"])
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        AccountingProvider(usage=usage),
        LimitsConfig(),
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    await run_mode(pipeline, mode)
    row = ledger.snapshot()["clients"]["usage_client_a"]
    for direction, expected in (("input", 7), ("output", 3)):
        known = usage is not None and direction + "_tokens" in usage
        assert row["known_" + direction + "_tokens"] == (expected if known else 0)
        assert row[direction + "_usage_unknown_attempts"] == (0 if known else 1)


@pytest.mark.parametrize("mode", ["chat", "responses"])
@pytest.mark.parametrize("phase", ["request", "response"])
async def test_policy_denials_record_only_started_provider_attempts(mode, phase):
    config = configuration(
        plugins={
            "policy": {
                "module": "gateway7.plugins.content_policy",
                "settings": {"terms": [TEXT], "phase": phase, "action": "block"},
            }
        },
        middleware=["policy"],
    )
    ledger = UsageLedger(config.auth.clients)
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    pipeline = Pipeline(
        load_plugins(config),
        provider,
        config.limits,
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    with pytest.raises(GatewayError) as caught:
        await run_mode(pipeline, mode)
    assert caught.value.code == "policy_denied"
    row = ledger.snapshot()["clients"]["usage_client_a"]
    expected = 0 if phase == "request" else 1
    assert provider.calls == row["provider_attempts"] == expected
    assert row["known_input_tokens"] == 7 * expected
    assert row["known_output_tokens"] == 3 * expected


@pytest.mark.parametrize("enabled", [False, True])
def test_operator_http_access_is_separate_from_clients_and_not_cached(
    credentials, monkeypatch, enabled
):
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: AccountingProvider()
    )
    app = create_app(config=configuration(operator=enabled))
    with TestClient(app) as client:
        for token in (None, CLIENT_A, CLIENT_B, KEY, "synthetic-wrong-operator-token"):
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            response = client.get("/operator/usage", headers=headers)
            assert response.status_code == (401 if enabled else 404)
            assert "usage_client_a" not in response.text and OPERATOR not in response.text
        response = client.get("/operator/usage", headers={"Authorization": "Bearer " + OPERATOR})
        assert response.status_code == (200 if enabled else 404)
        if enabled:
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["scope"] == "process_lifetime"
            assert response.json()["reset_on_restart"] is True
            assert set(response.json()["clients"]) == {"usage_client_a", "usage_client_b"}
        denied = client.post(
            "/chat",
            headers={"Authorization": "Bearer " + OPERATOR},
            json={"messages": [{"role": "user", "content": TEXT}]},
        )
        assert denied.status_code == 401


async def test_real_chat_transport_retains_source_usage_when_early_callback_is_cancelled():
    entered = asyncio.Event()
    attempts = []
    events = [
        {"choices": [{"index": 0, "delta": {"content": TEXT}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
    ]
    body = (
        "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
    ).encode()

    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield body

        async def aclose(self):
            self.closed = True

    stream = Stream()

    def handle(request):
        attempts.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    provider = build_provider(
        ProviderConfig(kind="openai", model="synthetic-usage-model"),
        KEY,
        transport=httpx.MockTransport(handle),
    )
    ledger = UsageLedger(["usage_client_a"])
    metrics = Metrics()
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        metrics=metrics,
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )

    async def sink(_):
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        pipeline.run_early(CHAT, "synthetic-cancel-accounting", on_text=sink)
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel("synthetic caller cancellation")
        with pytest.raises(asyncio.CancelledError, match="synthetic caller cancellation"):
            await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await provider.aclose()
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row["provider_attempts"] == row["outcomes"]["cancelled"] == len(attempts) == 1
    assert row["known_input_tokens"] == 7 and row["known_output_tokens"] == 3
    assert row["input_usage_unknown_attempts"] == row["output_usage_unknown_attempts"] == 0
    assert stream.closed


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"authorization", ("Basic " + OPERATOR).encode())],
        [(b"authorization", ("Bearer\t" + OPERATOR).encode())],
        [(b"authorization", ("Bearer " + OPERATOR + " ").encode())],
        [(b"authorization", b"Bearer \xff")],
        [(b"authorization", b"Bearer")],
        [
            (b"authorization", ("Bearer " + OPERATOR).encode()),
            (b"Authorization", ("Bearer " + OPERATOR).encode()),
        ],
    ],
)
def test_operator_bearer_parser_rejects_ambiguous_headers(credentials, headers):
    with pytest.raises(GatewayError) as caught:
        OperatorAccess(configuration()).authenticate(headers)
    assert caught.value.code == "unauthorized"


def test_suspended_clients_do_not_require_secrets_for_operator_initialization(
    credentials, monkeypatch
):
    data = configuration().model_dump()
    data["auth"]["clients"]["usage_client_b"]["enabled"] = False
    monkeypatch.delenv("TEST_USAGE_B")
    access = OperatorAccess(GatewayConfig.model_validate(data))
    access.authenticate([(b"authorization", ("Bearer " + OPERATOR).encode())])


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("style", ["missing", "client", "duplicated", "cookie", "query"])
async def test_operator_auth_rejects_before_receiving_any_body(
    credentials, monkeypatch, enabled, style
):
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: AccountingProvider()
    )
    app = create_app(config=configuration(operator=enabled))
    headers = []
    if style == "client":
        headers = [(b"authorization", ("Bearer " + CLIENT_A).encode())]
    elif style == "duplicated":
        headers = [(b"authorization", ("Bearer " + OPERATOR).encode())] * 2
    elif style == "cookie":
        headers = [(b"cookie", ("operator_token=" + OPERATOR).encode())]
    sent = []

    async def receive():
        raise AssertionError("Operator authentication must precede body reads")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/operator/usage",
        "http_version": "1.1",
        "scheme": "http",
        "headers": headers,
        "query_string": ("token=" + OPERATOR).encode() if style == "query" else b"",
    }
    async with app.router.lifespan_context(app):
        await app(scope, receive, send)
    assert next(
        message["status"] for message in sent if message["type"] == "http.response.start"
    ) == (401 if enabled else 404)
    body = b"".join(message.get("body", b"") for message in sent)
    assert OPERATOR.encode() not in body and b"usage_client_a" not in body


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/chat"),
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/responses"),
        ("GET", "/v1/models"),
    ],
)
def test_operator_credential_grants_no_generation_or_model_access(
    credentials, monkeypatch, method, path
):
    provider = AccountingProvider()
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    with TestClient(create_app(config=configuration())) as client:
        response = client.request(
            method,
            path,
            headers={"Authorization": "Bearer " + OPERATOR},
            json={} if method == "POST" else None,
        )
    assert response.status_code == 401 and provider.calls == 0


@pytest.mark.parametrize("mode", ["responses", "early_responses"])
@pytest.mark.parametrize("corruption", ["partial-total", "boolean", "hidden-extra"])
async def test_invalid_native_error_metadata_cannot_bypass_usage_revalidation(mode, corruption):
    if corruption == "partial-total":
        native = ResponsesUsage.model_construct(input_tokens=20, total_tokens=1)
    elif corruption == "boolean":
        native = ResponsesUsage.model_construct(input_tokens=True, output_tokens=3)
    else:
        native = ResponsesUsage(input_tokens=7, output_tokens=3)
        native.__dict__["private_extra"] = TEXT
    error = ResponsesProviderError(ProviderErrorReason.TRANSPORT)
    error._responses_usage = native

    class InvalidAccountingProvider(AccountingProvider):
        def result(self, **options):
            self.calls += 1
            raise error

    ledger = UsageLedger(["usage_client_a"])
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        InvalidAccountingProvider(),
        LimitsConfig(),
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    with pytest.raises(GatewayError):
        await run_mode(pipeline, mode)
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row["provider_attempts"] == row["outcomes"]["provider_error"] == 1
    assert row["known_input_tokens"] == row["known_output_tokens"] == 0
    assert row["input_usage_unknown_attempts"] == row["output_usage_unknown_attempts"] == 1


@pytest.mark.parametrize("mode", ["responses", "early_responses"])
@pytest.mark.parametrize("outcome", ["provider_error", "cancelled"])
async def test_native_failure_keeps_valid_partial_source_usage_without_deriving_the_other_direction(
    mode, outcome
):
    ledger = UsageLedger(["usage_client_a"])
    provider = AccountingProvider(outcome=outcome, usage={"input_tokens": 7})
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else GatewayError):
        await run_mode(pipeline, mode)
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row["provider_attempts"] == row["outcomes"][outcome] == 1
    assert row["known_input_tokens"] == 7 and row["input_usage_unknown_attempts"] == 0
    assert row["known_output_tokens"] == 0 and row["output_usage_unknown_attempts"] == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("direction", ["input", "output"])
async def test_request_relative_contract_rejection_keeps_valid_partial_source_accounting(
    mode, direction
):
    usage = {direction + "_tokens": 7}

    class ContractViolationProvider(AccountingProvider):
        def result(self, *, native=False):
            self.calls += 1
            call = {
                "id": "call_usage_fixture",
                "type": "function",
                "function": {"name": "unadvertised", "arguments": "{}"},
            }
            if native:
                data = native_response(usage).model_dump()
                data["output"] = [
                    {
                        "type": "function_call",
                        "id": "fc_usage_fixture",
                        "call_id": "call_usage_fixture",
                        "name": "unadvertised",
                        "arguments": "{}",
                    }
                ]
                return ResponsesResponse.model_validate(data)
            return ChatResponse(text="", tool_calls=[call], finish_reason="tool_calls", usage=usage)

    ledger = UsageLedger(["usage_client_a"])
    provider = ContractViolationProvider()
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_observer=ledger.observer("usage_client_a"),
    )
    with pytest.raises(GatewayError) as caught:
        await run_mode(pipeline, mode)
    assert caught.value.code == "provider_error"
    row = ledger.snapshot()["clients"]["usage_client_a"]
    other = "output" if direction == "input" else "input"
    assert provider.calls == row["provider_attempts"] == row["outcomes"]["provider_error"] == 1
    assert row["known_" + direction + "_tokens"] == 7
    assert row[direction + "_usage_unknown_attempts"] == 0
    assert row["known_" + other + "_tokens"] == 0 and row[other + "_usage_unknown_attempts"] == 1


@pytest.mark.parametrize("behavior", ["source_error", "ordinary_error", "late_return"])
@pytest.mark.parametrize("interruption", ["cancel", "deadline"])
async def test_buffered_chat_interruption_cannot_bypass_the_client_observer(behavior, interruption):
    entered = asyncio.Event()

    class SuppressingProvider(AccountingProvider):
        async def complete(self, request, **options):
            self.calls += 1
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if behavior == "source_error":
                    raise ProviderError(
                        ProviderErrorReason.TRANSPORT, usage={"input_tokens": 7, "output_tokens": 3}
                    ) from None
                if behavior == "ordinary_error":
                    raise RuntimeError(TEXT) from None
                return ChatResponse(text=TEXT, usage={"input_tokens": 7, "output_tokens": 3})

    ledger = UsageLedger(["usage_client_a"])
    metrics = Metrics()
    provider = SuppressingProvider()
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(request_timeout_seconds=0.01 if interruption == "deadline" else 1),
        metrics=metrics,
        provider_observer=ledger.observer("usage_client_a"),
    )
    task = asyncio.create_task(pipeline.run(CHAT, "synthetic-interruption-usage"))
    await asyncio.wait_for(entered.wait(), 1)
    if interruption == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(GatewayError) as caught:
            await task
        assert caught.value.code == "timeout"
    row = ledger.snapshot()["clients"]["usage_client_a"]
    known = behavior != "ordinary_error"
    assert provider.calls == row["provider_attempts"] == row["outcomes"]["cancelled"] == 1
    assert sum(row["outcomes"].values()) == 1
    assert row["known_input_tokens"] == (7 if known else 0)
    assert row["known_output_tokens"] == (3 if known else 0)
    assert (
        row["input_usage_unknown_attempts"]
        == row["output_usage_unknown_attempts"]
        == (0 if known else 1)
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "fake", "outcome": "cancelled"}
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "gateway7_provider_calls_total", {"provider": "fake", "outcome": "complete"}
        )
        is None
    )


async def test_buffered_return_after_elapsed_deadline_keeps_known_usage_and_never_counts_success():
    class LateProvider(AccountingProvider):
        async def complete(self, request, **options):
            self.calls += 1
            time.sleep(0.03)
            return ChatResponse(text=TEXT, usage={"input_tokens": 7})

    ledger = UsageLedger(["usage_client_a"])
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        LateProvider(),
        LimitsConfig(request_timeout_seconds=0.01),
        provider_observer=ledger.observer("usage_client_a"),
    )
    with pytest.raises(GatewayError) as caught:
        await pipeline.run(CHAT, "synthetic-late-usage")
    assert caught.value.code == "timeout"
    row = ledger.snapshot()["clients"]["usage_client_a"]
    assert row["provider_attempts"] == row["outcomes"]["cancelled"] == 1
    assert row["outcomes"]["complete"] == 0
    assert row["known_input_tokens"] == 7 and row["input_usage_unknown_attempts"] == 0
    assert row["known_output_tokens"] == 0 and row["output_usage_unknown_attempts"] == 1


def test_http_usage_is_partitioned_by_authenticated_identity_and_contains_no_private_content(
    credentials, monkeypatch, caplog
):
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    caplog.set_level("INFO", logger="gateway7")
    body = {"messages": [{"role": "user", "content": TEXT}]}
    app = create_app(config=configuration())
    with TestClient(app) as client:
        for token in (CLIENT_A, CLIENT_B, CLIENT_A):
            response = client.post(
                "/chat",
                json=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Gateway7-Client-Id": "usage_client_b",
                },
            )
            assert response.status_code == 200
        provider.usage = None
        assert (
            client.post(
                "/chat", json=body, headers={"Authorization": "Bearer " + CLIENT_B}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/chat",
                json={**body, "model": "forbidden"},
                headers={"Authorization": "Bearer " + CLIENT_A},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/chat", json={"messages": []}, headers={"Authorization": "Bearer " + CLIENT_A}
            ).status_code
            == 422
        )
        assert client.post("/chat", json=body).status_code == 401
        snapshot = client.get(
            "/operator/usage", headers={"Authorization": "Bearer " + OPERATOR}
        ).json()
        first = snapshot["clients"]["usage_client_a"]
        second = snapshot["clients"]["usage_client_b"]
        assert provider.calls == first["provider_attempts"] + second["provider_attempts"] == 4
        assert first["provider_attempts"] == second["provider_attempts"] == 2
        assert first["known_input_tokens"] == 14 and first["known_output_tokens"] == 6
        assert first["input_usage_unknown_attempts"] == first["output_usage_unknown_attempts"] == 0
        assert second["known_input_tokens"] == 7 and second["known_output_tokens"] == 3
        assert (
            second["input_usage_unknown_attempts"] == second["output_usage_unknown_attempts"] == 1
        )
        metric_text = client.get("/metrics").text
    for value in (TEXT, OPERATOR, CLIENT_A, CLIENT_B, KEY):
        assert (
            value not in json.dumps(snapshot)
            and value not in caplog.text
            and value not in metric_text
        )
    assert "usage_client_a" not in caplog.text and "usage_client_b" not in caplog.text
    assert "usage_client_a" not in metric_text and "usage_client_b" not in metric_text


def test_application_restart_resets_usage_and_disabled_clients_stay_zero_without_a_secret(
    credentials, monkeypatch
):
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    data = configuration().model_dump()
    data["auth"]["clients"]["usage_client_b"]["enabled"] = False
    monkeypatch.delenv("TEST_USAGE_B")
    app = create_app(config=GatewayConfig.model_validate(data))
    operator_headers = {"Authorization": "Bearer " + OPERATOR}
    with TestClient(app) as client:
        assert (
            client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": TEXT}]},
                headers={"Authorization": "Bearer " + CLIENT_A},
            ).status_code
            == 200
        )
        snapshot = client.get("/operator/usage", headers=operator_headers).json()
        assert snapshot["clients"]["usage_client_a"]["provider_attempts"] == 1
        assert snapshot["clients"]["usage_client_b"]["provider_attempts"] == 0
    with TestClient(app) as client:
        snapshot = client.get("/operator/usage", headers=operator_headers).json()
        assert snapshot["scope"] == "process_lifetime" and snapshot["reset_on_restart"] is True
        assert all(row["provider_attempts"] == 0 for row in snapshot["clients"].values())


@pytest.mark.parametrize(
    "route,early",
    [
        ("/chat", False),
        ("/v1/chat/completions", False),
        ("/v1/chat/completions", True),
        ("/v1/responses", False),
        ("/v1/responses", True),
    ],
)
def test_effective_client_pipeline_observer_covers_every_http_execution_path(
    credentials, monkeypatch, route, early
):
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    data = configuration().model_dump()
    data["provider"]["kind"] = "openai"
    data["provider"]["base_url"] = "https://api.openai.com"
    data["provider"]["model"] = "synthetic-usage-model"
    for client in data["auth"]["clients"].values():
        client["models"] = ["synthetic-usage-model"]
    headers = {"Authorization": "Bearer " + CLIENT_A}
    if early:
        headers["X-Gateway7-Stream-Mode"] = "early"
    body = (
        {"model": "synthetic-usage-model", "input": TEXT, "store": False}
        if route.endswith("responses")
        else {"model": "synthetic-usage-model", "messages": [{"role": "user", "content": TEXT}]}
    )
    if early:
        body["stream"] = True
    with TestClient(create_app(config=GatewayConfig.model_validate(data))) as client:
        response = client.post(route, headers=headers, json=body)
        assert response.status_code == 200
        row = client.get("/operator/usage", headers={"Authorization": "Bearer " + OPERATOR}).json()[
            "clients"
        ]["usage_client_a"]
    assert provider.calls == row["provider_attempts"] == row["outcomes"]["complete"] == 1
    assert row["known_input_tokens"] == 7 and row["known_output_tokens"] == 3


def test_client_rate_rejection_adds_no_provider_usage_and_other_clients_remain_independent(
    credentials, monkeypatch
):
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    data = configuration().model_dump()
    data["auth"]["clients"]["usage_client_a"]["limits"]["requests_per_minute"] = 1
    body = {"messages": [{"role": "user", "content": TEXT}]}
    operator_headers = {"Authorization": "Bearer " + OPERATOR}
    with TestClient(create_app(config=GatewayConfig.model_validate(data))) as client:
        headers = {"Authorization": "Bearer " + CLIENT_A}
        assert client.post("/chat", headers=headers, json=body).status_code == 200
        rejected = client.post("/chat", headers=headers, json=body)
        assert rejected.status_code == 429 and rejected.json()["error"]["code"] == "rate_limited"
        assert (
            client.post(
                "/chat", headers={"Authorization": "Bearer " + CLIENT_B}, json=body
            ).status_code
            == 200
        )
        for _ in range(2):
            snapshot = client.get("/operator/usage", headers=operator_headers).json()
            assert sum(row["provider_attempts"] for row in snapshot["clients"].values()) == 2
            assert all(row["provider_attempts"] == 1 for row in snapshot["clients"].values())
    assert provider.calls == 2

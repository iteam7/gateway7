"""A live smoke makes one bounded chat attempt and emits no arbitrary remote data."""

import asyncio
import importlib
import json
import logging

import httpx
import pytest

from gateway7 import smoke
from gateway7.app import create_app
from gateway7.cli import main
from gateway7.config import GatewayConfig
from gateway7.models import ChatResponse

TOKEN = "gateway7-synthetic-live-client-token"
CANARY = "synthetic-private-response-canary"
REQUEST_ID = "1" * 32
CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("GATEWAY7_TOKEN", TOKEN)
    logger = logging.getLogger("gateway7")
    previous = (logger.handlers[:], logger.level, logger.propagate)
    yield
    logger.handlers, logger.level, logger.propagate = previous


def response(request, *, usage=None):
    if request.url.path == "/health":
        data = {"status": "ok"}
    elif request.url.path == "/ready":
        data = {"status": "ready"}
    elif request.url.path == "/v1/models":
        if "authorization" not in request.headers:
            return httpx.Response(401, text=CANARY, headers={"x-request-id": REQUEST_ID})
        data = {"object": "list", "data": [{"id": "configured-model"}]}
    else:
        data = {
            "text": CANARY,
            "usage": {"input_tokens": 3, "output_tokens": 2} if usage is None else usage,
            "request_id": REQUEST_ID,
        }
    return httpx.Response(200, json=data, headers={"x-request-id": REQUEST_ID})


def transport(monkeypatch, handler):
    options = []

    def client(**kwargs):
        options.append(kwargs)
        return CLIENT(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(smoke.httpx, "AsyncClient", client)
    return options


async def test_one_live_chat_after_nonbillable_auth_checks(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return response(request)

    options = transport(monkeypatch, handler)
    code, report = await smoke.run_smoke(
        "http://localhost:8000/", model="configured-model", max_tokens=64
    )
    assert code == 0 and report["passed"] and report["chat_attempts"] == 1
    assert [request.method for request in requests] == ["GET"] * 4 + ["POST"]
    assert [request.url.path for request in requests] == [
        "/health",
        "/ready",
        "/v1/models",
        "/v1/models",
        "/chat",
    ]
    assert "authorization" not in requests[2].headers
    assert requests[3].headers["authorization"] == "Bearer " + TOKEN
    payload = json.loads(requests[4].content)
    assert payload == {
        "messages": [{"role": "user", "content": "Reply briefly: Gateway7 is working."}],
        "max_tokens": 64,
        "model": "configured-model",
    }
    assert options == [{"trust_env": False, "follow_redirects": False, "timeout": 90}]
    assert report["checks"][-1]["usage"] == {"input_tokens": 3, "output_tokens": 2}
    assert report["checks"][-1]["request_id"] == REQUEST_ID
    assert CANARY not in json.dumps(report) and TOKEN not in json.dumps(report)


@pytest.mark.parametrize(
    "options,env_value,error",
    [
        ({}, None, "missing_token"),
        ({}, "short", "invalid_token"),
        ({}, "x" * 16 + "\n", "invalid_token"),
        ({"token_env": "invalid name"}, TOKEN, "invalid_token_env"),
        ({"model": "secret/model"}, TOKEN, "invalid_model"),
        ({"url": "http://username:synthetic-secret@localhost"}, TOKEN, "invalid_url"),
        ({"url": "http://localhost:bad"}, TOKEN, "invalid_url"),
        ({"url": "http://localhost/path"}, TOKEN, "invalid_url"),
        ({"url": "http://localhost?secret=value"}, TOKEN, "invalid_url"),
        ({"url": "http://localhost#secret"}, TOKEN, "invalid_url"),
    ],
)
async def test_bad_local_options_never_contact_gateway(monkeypatch, options, env_value, error):
    if env_value is None:
        monkeypatch.delenv("GATEWAY7_TOKEN")
    else:
        monkeypatch.setenv("GATEWAY7_TOKEN", env_value)

    def unexpected(**kwargs):
        pytest.fail("Invalid smoke options must not create a client")

    monkeypatch.setattr(smoke.httpx, "AsyncClient", unexpected)
    code, report = await smoke.run_smoke(**{"url": "http://localhost", **options})
    assert code == 1 and report["chat_attempts"] == 0
    assert report["checks"][-1]["error"] == error
    assert "synthetic-secret" not in json.dumps(report)


@pytest.mark.parametrize("failure", ["health", "readiness", "auth_disabled", "models", "model"])
async def test_failed_prechecks_never_attempt_chat(monkeypatch, failure):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        path = request.url.path
        if failure == "health" and path == "/health":
            return httpx.Response(200, json={"status": CANARY})
        if failure == "readiness" and path == "/ready":
            return httpx.Response(503, text=CANARY)
        if failure == "auth_disabled" and path == "/v1/models":
            return httpx.Response(200, text=CANARY)
        if failure == "models" and path == "/v1/models" and "authorization" in request.headers:
            return httpx.Response(200, json={"object": "list", "data": [{"id": CANARY + "/bad"}]})
        return response(request)

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke(
        "http://localhost", model="other-model" if failure == "model" else None
    )
    assert code == 1 and report["chat_attempts"] == 0
    assert CANARY not in json.dumps(report)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 502, 504])
async def test_failed_chat_safe_status_without_retry_or_body(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                status,
                text=CANARY,
                headers={
                    "x-request-id": REQUEST_ID,
                    "location": "https://secret.invalid/" + CANARY,
                },
            )
        return response(request)

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and report["chat_attempts"] == 1
    assert sum(request.method == "POST" for request in calls) == 1
    assert report["checks"][-1] == {
        "check": "chat",
        "passed": False,
        "http_status": status,
        "request_id": REQUEST_ID,
        "error": "unexpected_status",
    }
    assert CANARY not in json.dumps(report)


@pytest.mark.parametrize(
    "change",
    [
        {"text": ""},
        {"text": []},
        {"request_id": CANARY},
        {"usage": True},
        {"usage": {"input_tokens": True, "output_tokens": 2}},
        {"usage": {"input_tokens": -1, "output_tokens": 2}},
        {"usage": {"input_tokens": 2**63, "output_tokens": 2}},
        {"usage": {"input_tokens": 1, "output_tokens": 2, "secret": CANARY}},
    ],
)
async def test_invalid_native_contract_is_not_success(monkeypatch, change):
    def handler(request):
        if request.method != "POST":
            return response(request)
        return httpx.Response(
            200,
            json={"text": CANARY, "usage": None, "request_id": REQUEST_ID, **change},
            headers={"x-request-id": REQUEST_ID},
        )

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and report["checks"][-1]["error"] == "invalid_response"
    assert CANARY not in json.dumps(report)


async def test_unknown_usage_is_null_and_untrusted_request_header_is_discarded(monkeypatch):
    def handler(request):
        if request.method != "POST":
            return response(request)
        return httpx.Response(
            200,
            json={"text": CANARY, "usage": None, "request_id": REQUEST_ID},
            headers={"x-request-id": CANARY},
        )

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and CANARY not in json.dumps(report)
    assert "request_id" not in report["checks"][-1]


async def test_unknown_usage_can_succeed(monkeypatch):
    def handler(request):
        if request.method != "POST":
            return response(request)
        return httpx.Response(
            200,
            json={"text": CANARY, "usage": None, "request_id": REQUEST_ID},
            headers={"x-request-id": REQUEST_ID},
        )

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 0 and report["checks"][-1]["usage"] is None


@pytest.mark.parametrize("body", [b"{invalid-json", b"[]", b"null"])
async def test_malformed_or_nonobject_json_is_not_success(monkeypatch, body):
    transport(monkeypatch, lambda request: httpx.Response(200, content=body))
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and report["checks"][-1]["error"] == "invalid_response"
    assert report["chat_attempts"] == 0


async def test_client_close_failure_cannot_duplicate_or_pass_last_check(monkeypatch):
    class ClosingTransport(httpx.MockTransport):
        async def aclose(self):
            await super().aclose()
            raise RuntimeError(CANARY)

    clients = []

    def client(**kwargs):
        instance = CLIENT(**kwargs, transport=ClosingTransport(response))
        clients.append(instance)
        return instance

    monkeypatch.setattr(smoke.httpx, "AsyncClient", client)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and not report["passed"] and report["chat_attempts"] == 1
    assert [check["check"] for check in report["checks"]] == [
        "health",
        "readiness",
        "anonymous_models",
        "models",
        "chat",
    ]
    assert not report["checks"][-1]["passed"]
    assert report["checks"][-1]["error"] == "check_failed"
    assert clients[0].is_closed and CANARY not in json.dumps(report)


class Stream(httpx.AsyncByteStream):
    def __init__(self, *, oversized=False):
        self.oversized = oversized
        self.tail_read = False
        self.closed = False

    async def __aiter__(self):
        if self.oversized:
            yield b"x" * (smoke._BODY_LIMIT + 1)
            self.tail_read = True
            raise AssertionError("An oversized stream must be closed before its tail")
        while True:
            yield b" "
            await asyncio.sleep(0.05)

    async def aclose(self):
        self.closed = True


async def test_oversized_stream_is_closed_without_waiting_for_tail(monkeypatch):
    stream = Stream(oversized=True)

    def handler(request):
        return httpx.Response(200, stream=stream)

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and report["checks"][-1]["error"] == "response_too_large"
    assert stream.closed and not stream.tail_read and report["chat_attempts"] == 0


async def test_whole_deadline_stops_dribbling_body_and_closes_stream(monkeypatch):
    stream = Stream()
    transport(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    code, report = await smoke.run_smoke("http://localhost", timeout=1)
    assert code == 1 and report["checks"][-1]["error"] == "timeout"
    assert report["duration_ms"] < 2500 and stream.closed


async def test_external_cancellation_propagates_and_closes_stream(monkeypatch):
    stream = Stream()
    started = asyncio.Event()

    def handler(request):
        started.set()
        return httpx.Response(200, stream=stream)

    transport(monkeypatch, handler)
    task = asyncio.create_task(smoke.run_smoke("http://localhost"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed


async def test_network_exception_is_sanitized(monkeypatch):
    def handler(request):
        raise httpx.ConnectError(CANARY, request=request)

    transport(monkeypatch, handler)
    code, report = await smoke.run_smoke("http://localhost")
    assert code == 1 and report["checks"][-1]["error"] == "network_error"
    assert CANARY not in json.dumps(report)


async def test_smoke_uses_actual_gateway_auth_and_response_contract(monkeypatch):
    class Provider:
        calls = 0

        async def complete(self, request, *, model=None):
            self.calls += 1
            return ChatResponse(text=CANARY, usage={"input_tokens": 3, "output_tokens": 2})

        async def aclose(self):
            pass

    provider = Provider()
    monkeypatch.setenv("FAKE_LLM_API_KEY", "gateway7-synthetic-provider-key")
    monkeypatch.setattr(
        importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
    )
    config = GatewayConfig.model_validate(
        {
            "auth": {
                "enabled": True,
                "clients": {"test": {"token_env": "GATEWAY7_TOKEN", "models": ["fake"]}},
            }
        }
    )
    app = create_app(config=config)
    monkeypatch.setattr(
        smoke.httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(**kwargs, transport=httpx.ASGITransport(app)),
    )
    async with app.router.lifespan_context(app):
        code, report = await smoke.run_smoke("http://gateway.test", model="fake")
    assert code == 0 and provider.calls == 1 and report["chat_attempts"] == 1
    assert CANARY not in json.dumps(report)


def test_cli_emits_safe_json_and_help_discloses_live_call(monkeypatch, capsys):
    transport(monkeypatch, response)
    assert main(["smoke", "--model", "configured-model"]) == 0
    result = capsys.readouterr()
    assert json.loads(result.out)["passed"] and result.err == ""
    assert CANARY not in result.out and TOKEN not in result.out
    with pytest.raises(SystemExit) as error:
        main(["smoke", "--help"])
    assert error.value.code == 0
    assert "paid provider tokens" in capsys.readouterr().out


@pytest.mark.parametrize("args", [["--max-tokens", "0"], ["--timeout", "0"], ["--timeout", "nan"]])
def test_cli_rejects_invalid_limits_before_call(args):
    with pytest.raises(SystemExit) as error:
        main(["smoke", *args])
    assert error.value.code == 2


def test_cli_interrupt_returns_130(monkeypatch):
    async def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("gateway7.cli.run_smoke", interrupted)
    assert main(["smoke"]) == 130

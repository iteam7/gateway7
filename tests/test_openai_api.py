"""The guarded OpenAI subset works through JSON, SSE and the real Python SDK."""

import importlib
import json
import socket
import threading
import time

import httpx
import httpx2
from openai import AuthenticationError, OpenAI, PermissionDeniedError
import pytest
import uvicorn
from fastapi.testclient import TestClient

from gateway7.app import create_app
from gateway7.config import GatewayConfig
from gateway7.models import ChatResponse, ToolCall

TOKEN = "gateway7-synthetic-openai-client"
HEADERS = {"Authorization": "Bearer " + TOKEN}
BODY = {"model": "model-a", "messages": [{"role": "user", "content": "hello"}]}


class Provider:
    def __init__(self, *, usage=None, finish_reason="stop", fail=False, text="answer", tool_calls=None):
        self.usage = usage
        self.finish_reason = finish_reason
        self.calls = []
        self.fail = fail
        self.text = text
        self.tool_calls = tool_calls or []
        self.streams = []

    async def complete(self, request, *, model=None, stream=False):
        self.calls.append((request, model))
        self.streams.append(stream)
        if self.fail:
            raise RuntimeError("private-upstream-details")
        return ChatResponse(text=self.text, usage=self.usage, finish_reason=self.finish_reason, tool_calls=self.tool_calls)

    async def aclose(self):
        pass


def sse_events(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = response.text.split("\n\n")
    assert frames[-2] == "data: [DONE]" and frames[-1] == ""
    return [json.loads(frame.removeprefix("data: ")) for frame in frames[:-2]]


@pytest.fixture
def setup_app(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_API_KEY", "gateway7-synthetic-private-provider-key")
    monkeypatch.setenv("OPENAI_API_KEY", "gateway7-synthetic-private-provider-key")
    monkeypatch.setenv("GATEWAY7_OPENAI_TOKEN", TOKEN)

    def create(provider=None, *, provider_config=None, **extra):
        provider = Provider() if provider is None else provider
        app_module = importlib.import_module("gateway7.app")
        monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
        config = GatewayConfig.model_validate({
            "provider": provider_config or {"kind": "openai", "model": "model-a"},
            "auth": {"enabled": True, "clients": {"client": {
                "token_env": "GATEWAY7_OPENAI_TOKEN", "models": ["model-a", "model-b"],
            }}}, **extra,
        })
        return create_app(config=config), provider

    return create


@pytest.mark.parametrize("limit", [{}, {"max_tokens": 32}, {"max_completion_tokens": 64}])
def test_openai_message_mapping_response_shape_and_token_limits(setup_app, limit):
    app, provider = setup_app(Provider(usage={"input_tokens": 7, "output_tokens": 4}))
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={
            **BODY, **limit, "stream": False, "store": False, "n": 1,
            "messages": [{"role": "developer", "content": "instruction"},
                         {"role": "user", "content": "hello"},
                         {"role": "assistant", "content": "history"}],
        })
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "chatcmpl-" + response.headers["x-request-id"]
    assert data["object"] == "chat.completion" and data["model"] == "model-a"
    assert type(data["created"]) is int and abs(data["created"] - time.time()) < 5
    assert data["choices"] == [{"index": 0, "message": {"role": "assistant", "content": "answer"},
                                "finish_reason": "stop", "logprobs": None}]
    assert data["usage"] == {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}
    assert provider.calls[0][0].messages[0].role == "system"
    assert provider.calls[0][0].max_tokens == next(iter(limit.values()), 256)
    assert not hasattr(provider.calls[0][0], "model")


@pytest.mark.parametrize("changes", [
    {"stream": 0}, {"stream": None}, {"store": True}, {"store": 0},
    {"store": None}, {"n": 2}, {"n": True}, {"n": 1.0}, {"n": None},
    {"max_tokens": 0}, {"max_tokens": 4097}, {"max_tokens": True}, {"max_tokens": None},
    {"max_completion_tokens": None}, {"max_tokens": 10, "max_completion_tokens": 10},
    {"max_tokens": None, "max_completion_tokens": 10},
    {"temperature": 2.1}, {"parallel_tool_calls": True}, {"parallel_tool_calls": 0}, {"tools": [{}]},
    {"stream_options": {"include_usage": True}},
    {"stream": True, "stream_options": {"include_usage": 1}},
    {"tool_choice": "required"}, {"response_format": {"type": "json_object"}},
    {"messages": [{"role": "user", "content": [{"type": "text", "text": "private"}]}]},
    {"messages": [{"role": "user", "content": None}]},
    {"messages": [{"role": "tool", "content": "private"}]},
    {"messages": []}, {"model": None}, {"model": "../unsafe"},
    {"unknown-sensitive-field-value": "private-sensitive-input"},
])
def test_unsupported_controls_and_nontext_are_rejected_without_forwarding(setup_app, changes):
    app, provider = setup_app()
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, **changes})
    assert response.status_code == 400
    error = response.json()["error"]
    assert set(error) == {"message", "type", "param", "code"}
    assert error["type"] == "invalid_request_error" and error["code"] == "invalid_request"
    assert error["param"] in {None, "model", "messages", "max_tokens", "max_completion_tokens", "stream", "store", "n", "temperature", "tools", "tool_choice", "response_format", "parallel_tool_calls", "stream_options"}
    assert "unknown-sensitive-field-value" not in response.text
    assert "private-sensitive-input" not in response.text
    assert not provider.calls


@pytest.mark.parametrize("option", [
    "tools", "tool_choice", "temperature", "response_format", "parallel_tool_calls",
    "stream_options", "functions", "function_call", "top_p", "stop", "reasoning_effort",
])
def test_known_invalid_or_unsupported_option_reports_only_its_static_name(setup_app, option):
    app, provider = setup_app()
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS,
                               json={**BODY, option: ({"private": "private-sensitive-option-value"} if option == "stop" else "private-sensitive-option-value")})
    assert response.status_code == 400
    assert response.json()["error"]["param"] == option
    assert response.json()["error"]["code"] == "invalid_request"
    assert "private-sensitive-option-value" not in response.text
    assert not provider.calls


@pytest.mark.parametrize("usage", [None, {"input_tokens": 2}])
def test_unknown_usage_is_null_and_truncation_is_preserved(setup_app, usage):
    app, _ = setup_app(Provider(usage=usage, finish_reason="length"))
    with TestClient(app) as client:
        result = client.post("/v1/chat/completions", headers=HEADERS, json=BODY).json()
    assert result["usage"] is None
    assert result["choices"][0]["finish_reason"] == "length"


def test_provider_failures_and_model_denials_have_openai_error_shape(setup_app, caplog):
    app, provider = setup_app(Provider(fail=True))
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        denied = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, "model": "not-allowed"})
        assert denied.status_code == 403 and not provider.calls
        assert denied.json()["error"]["type"] == "permission_error"
        response = client.post("/v1/chat/completions", headers=HEADERS, json=BODY)
        assert response.status_code == 502
        assert response.json()["error"]["type"] == "api_error"
        assert response.json()["error"]["code"] == "provider_error"
        assert len(provider.calls) == 1
        metrics = client.get("/metrics").text
        assert TOKEN not in response.text + caplog.text + metrics
        assert "private-upstream-details" not in response.text + caplog.text + metrics


def test_boundary_failures_use_openai_format(setup_app):
    app, provider = setup_app(limits={"max_body_bytes": 128})
    with TestClient(app) as client:
        too_large = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY,
            "messages": [{"role": "user", "content": "sensitive" * 100}]})
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "body_too_large"
        malformed = client.post("/v1/chat/completions", headers={**HEADERS, "content-type": "application/json"}, content="{bad")
        assert malformed.status_code == 400
        assert malformed.json()["error"]["type"] == "invalid_request_error"
        missing = client.get("/v1/not-implemented", headers=HEADERS)
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
        wrong_method = client.get("/v1/chat/completions", headers=HEADERS)
        assert wrong_method.status_code == 405 and wrong_method.json()["error"]["code"] == "method_not_allowed"
        assert not provider.calls
    before_start = TestClient(create_app()).post("/v1/chat/completions", json=BODY)
    assert before_start.status_code == 503 and before_start.json()["error"]["code"] == "unavailable"


@pytest.mark.parametrize("stream", [False, True])
def test_openai_calls_use_same_request_and_response_middleware(setup_app, stream):
    app, provider = setup_app(Provider(text="SECRET-TEST"), plugins={
        "guard": {"module": "gateway7.plugins.content_policy", "settings": {"terms": ["BLOCK-ME-TEST"], "phase": "request"}},
        "email": {"module": "gateway7.plugins.email_mask"},
        "redact": {"module": "gateway7.plugins.content_policy", "settings": {"terms": ["SECRET-TEST"], "action": "redact", "phase": "response"}},
    }, middleware=["guard", "email", "redact"])
    with TestClient(app) as client:
        blocked = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, "stream": stream,
            "messages": [{"role": "user", "content": "BLOCK-ME-TEST"}]})
        assert blocked.status_code == 403 and not provider.calls
        response = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, "stream": stream,
            "messages": [{"role": "user", "content": "user@example.com"}]})
        if stream:
            events = sse_events(response)
            text = "".join(event["choices"][0]["delta"].get("content", "") for event in events)
            assert text == "[removed]" and "SECRET-TEST" not in response.text
        else:
            assert response.json()["choices"][0]["message"]["content"] == "[removed]"
        assert provider.streams == [stream]
        assert provider.calls[-1][0].messages[0].content == "[EMAIL]"


def test_actual_openai_python_sdk_chat_models_and_errors_over_http(setup_app):
    app, provider = setup_app(Provider(usage={"input_tokens": 4, "output_tokens": 2}, finish_reason="length"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          access_log=False, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(trust_env=False, timeout=0.5) as probe:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    if probe.get(base_url + "/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
            else:
                pytest.fail("SDK test server failed to become ready")
        with OpenAI(api_key=TOKEN, base_url=base_url + "/v1", max_retries=0,
                    http_client=httpx2.Client(trust_env=False, timeout=2),
                    _strict_response_validation=True) as sdk:
            completion = sdk.chat.completions.create(model="model-b", messages=[{"role": "user", "content": "SDK hello"}], max_completion_tokens=64)
            assert completion.model == "model-b"
            assert completion.choices[0].message.content == "answer"
            assert completion.choices[0].finish_reason == "length"
            assert completion.usage.total_tokens == 6
            assert provider.calls[-1][1] == "model-b"
            assert provider.calls[-1][0].max_tokens == 64
            assert [item.id for item in sdk.models.list()] == ["model-a", "model-b"]
            with pytest.raises(PermissionDeniedError):
                sdk.chat.completions.create(model="forbidden", messages=[{"role": "user", "content": "blocked"}])
            with sdk.chat.completions.create(
                model="model-a", messages=[{"role": "user", "content": "stream hello"}],
                stream=True, stream_options={"include_usage": True},
            ) as stream:
                chunks = list(stream)
            assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices) == "answer"
            assert chunks[-2].choices[0].finish_reason == "length"
            assert chunks[-1].choices == [] and chunks[-1].usage.total_tokens == 6
            assert len({chunk.id for chunk in chunks}) == 1
            assert provider.streams == [False, True]
        with OpenAI(api_key="gateway7-synthetic-wrong-token", base_url=base_url + "/v1", max_retries=0,
                    http_client=httpx2.Client(trust_env=False, timeout=2)) as sdk:
            with pytest.raises(AuthenticationError):
                sdk.models.list()
        assert len(provider.calls) == 2
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()


TOOL = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read the synthetic fixture",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        "strict": False,
    },
}
CALL = {"id": "call_fixture", "type": "function", "function": {"name": "read", "arguments": '{"path":"agent-fixture.txt"}'}}


@pytest.mark.parametrize("include_usage", [False, True])
@pytest.mark.parametrize("usage", [None, {"input_tokens": 3, "output_tokens": 2}])
def test_checked_sse_has_stable_identity_escaped_text_terminal_and_optional_usage(setup_app, include_usage, usage):
    text = 'Answer\n"quoted" — 😀\ud800'
    app, provider = setup_app(Provider(text=text, usage=usage))
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={
            **BODY, "stream": True, "stream_options": {"include_usage": include_usage},
        })
    events = sse_events(response)
    assert len({(event["id"], event["created"], event["model"]) for event in events}) == 1
    assert all(event["object"] == "chat.completion.chunk" for event in events)
    assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    assert events[1]["choices"][0]["delta"]["content"] == text
    assert events[-2 if include_usage else -1]["choices"][0]["finish_reason"] == "stop"
    if include_usage:
        assert events[-1]["choices"] == []
        assert events[-1]["usage"] == (None if usage is None else {
            "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
        })
    else:
        assert all(event["choices"] for event in events)
    assert provider.streams == [True]


@pytest.mark.parametrize("stream", [False, True])
def test_function_tool_round_trip_preserves_nullable_assistant_and_result_id(setup_app, stream):
    provider = Provider(text="", finish_reason="tool_calls", tool_calls=[ToolCall.model_validate(CALL)])
    app, provider = setup_app(provider)
    with TestClient(app) as client:
        first = client.post("/v1/chat/completions", headers=HEADERS, json={
            **BODY, "stream": stream, "tools": [TOOL], "tool_choice": "auto", "parallel_tool_calls": False,
        })
        assert first.status_code == 200
        if stream:
            events = sse_events(first)
            deltas = [event["choices"][0]["delta"] for event in events]
            assert deltas[1] == {"tool_calls": [{"index": 0, **CALL}]}
            assert events[-1]["choices"][0]["finish_reason"] == "tool_calls"
        else:
            message = first.json()["choices"][0]["message"]
            assert message == {"role": "assistant", "content": None, "tool_calls": [CALL]}
        assert provider.calls[0][0].tools[0].function.name == "read"
        assert provider.calls[0][0].parallel_tool_calls is False
        provider.text, provider.finish_reason, provider.tool_calls = "GATEWAY7_AGENT_OK", "stop", []
        second = client.post("/v1/chat/completions", headers=HEADERS, json={
            **BODY, "stream": stream, "tools": [TOOL], "parallel_tool_calls": False,
            "messages": [*BODY["messages"],
                {"role": "assistant", "content": None, "tool_calls": [CALL]},
                {"role": "tool", "tool_call_id": "call_fixture", "content": "GATEWAY7_AGENT_OK"}],
        })
        assert second.status_code == 200
        assert "GATEWAY7_AGENT_OK" in second.text
        request = provider.calls[1][0]
        assert request.messages[-2].content is None
        assert request.messages[-2].tool_calls[0].id == request.messages[-1].tool_call_id
        assert request.messages[-1].role == "tool"
        assert provider.streams == [stream, stream]


def test_stream_tool_argument_denial_happens_before_sse_headers_and_delivery(setup_app):
    call = {**CALL, "function": {"name": "read", "arguments": '{"path":"PRIVATE-TEST"}'}}
    app, provider = setup_app(Provider(text="", finish_reason="tool_calls", tool_calls=[ToolCall.model_validate(call)]),
        plugins={"guard": {"module": "gateway7.plugins.content_policy", "settings": {
            "terms": ["PRIVATE-TEST"], "phase": "response", "action": "block"}}}, middleware=["guard"])
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, "stream": True, "tools": [TOOL]})
        metrics = client.get("/metrics").text
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "policy_denied"
    assert "PRIVATE-TEST" not in response.text + metrics
    assert "data:" not in response.text and len(provider.calls) == 1


@pytest.mark.parametrize("kind", ["fake", "claude", "gemini"])
@pytest.mark.parametrize("controls", [{"stream": True}, {"tools": [TOOL]}, {"temperature": 0.5}])
def test_non_openai_provider_rejects_new_capabilities_before_forwarding(setup_app, monkeypatch, kind, controls):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "gateway7-synthetic-private-provider-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gateway7-synthetic-private-provider-key")
    app, provider = setup_app(provider_config={"kind": kind, "model": "model-a"})
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, **controls})
    assert response.status_code == 400 and not provider.calls
    assert response.json()["error"]["code"] == "invalid_request"


def test_openai_generation_controls_are_validated_and_forwarded_to_core(setup_app):
    app, provider = setup_app()
    controls = {"temperature": 0.2, "top_p": 0.8, "frequency_penalty": -0.5,
                "presence_penalty": 1.0, "seed": 7, "stop": ["END"]}
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=HEADERS, json={**BODY, **controls})
        native = client.post("/chat", headers=HEADERS, json={"messages": BODY["messages"], "temperature": 0.2})
    assert response.status_code == 200
    assert native.status_code == 422
    assert len(provider.calls) == 1
    assert {name: getattr(provider.calls[0][0], name) for name in controls} == controls


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_checked_sse_send_is_bounded_by_the_remaining_request_deadline(expired):
    import asyncio

    from gateway7.app import _CheckedSSE

    sent = []
    body_attempted = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.body":
            body_attempted.set()
            await asyncio.Event().wait()
        sent.append(message)

    async def receive():
        return {"type": "http.disconnect"}

    response = _CheckedSSE(b"data: [DONE]\n\n", asyncio.get_running_loop().time() + (-0.02 if expired else 0.02))
    with pytest.raises(TimeoutError):
        await response({"type": "http"}, receive, send)
    assert body_attempted.is_set() is not expired
    assert [message["type"] for message in sent] == ([] if expired else ["http.response.start"])

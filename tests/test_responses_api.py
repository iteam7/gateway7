"""Offline acceptance tests for the guarded native Responses HTTP boundary.

These tests exercise create_app and the actual native pipeline, not an added test
route. Checked playback must finish response policies before sending SSE headers.
Early delivery has a separate metadata contract and is intentionally not assumed.
"""

import asyncio
import importlib
import json
import sys
from copy import deepcopy
from types import ModuleType

import httpx
import httpx2
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from openai.types.responses import Response, ResponseStreamEvent
from pydantic import BaseModel, ConfigDict, TypeAdapter
import pytest

from gateway7.app import create_app
from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.plugin_api import PluginDescriptor
from gateway7.providers import build_provider
from gateway7.responses_models import (
    ResponsesConsent,
    ResponsesCreateRequest,
    ResponsesRequest,
    ResponsesResponse,
)

TOKEN = "gateway7-synthetic-responses-client"
PROVIDER_KEY = "gateway7-synthetic-responses-provider"
MODEL = "gpt-4.1-mini"
SOURCE_MODEL = "synthetic-native-source-model"
PATH = "/v1/responses"
HEADERS = {"Authorization": "Bearer " + TOKEN}
BODY = {
    "model": MODEL,
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
    "store": False,
}
USAGE = {
    "input_tokens": 7,
    "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 1},
    "output_tokens": 4,
    "output_tokens_details": {"reasoning_tokens": 1},
    "total_tokens": 11,
}
FUNCTION = {
    "type": "function",
    "name": "read",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
    "strict": True,
}
CUSTOM = {"type": "custom", "name": "apply_patch", "format": {"type": "text"}}
RAW_PATCH = "*** Begin Patch\n*** Add File: synthetic.txt\n+Synthetic — 🌍\n*** End Patch\n"
OPAQUE = "SYNTHETIC_NOT_REAL_ENCRYPTED_HISTORY=="
SDK_RESPONSE = TypeAdapter(Response)
SDK_EVENT = TypeAdapter(ResponseStreamEvent)


def message(text="Synthetic answer", *, item_id="msg_synthetic"):
    return {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def function_call(suffix="a", *, namespace=None, arguments=' {"path": "fixture.txt"} '):
    item = {
        "type": "function_call",
        "id": "fc_item_" + suffix,
        "call_id": "call_" + suffix,
        "name": "read",
        "arguments": arguments,
        "status": "completed",
    }
    if namespace is not None:
        item["namespace"] = namespace
    return item


def native_response(*output, **changes):
    return ResponsesResponse.model_validate(
        {
            "id": "resp_synthetic",
            "object": "response",
            "created_at": 1800000000.0,
            "model": SOURCE_MODEL,
            "status": "completed",
            "output": deepcopy(list(output) if output else [message()]),
            "usage": deepcopy(USAGE),
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            **changes,
        }
    )


class RecordingNativeProvider:
    """Only the native provider contract may be used by the Responses route."""

    def __init__(self, result=None, *, fail=False):
        self.result = native_response() if result is None else result
        self.fail = fail
        self.calls = []
        self.closed = False

    async def complete_responses(
        self, request, *, model=None, stream=False, consent=ResponsesConsent()
    ):
        assert type(request) is ResponsesRequest
        assert type(stream) is bool and type(consent) is ResponsesConsent
        self.calls.append((request.model_copy(deep=True), model, stream, consent))
        if self.fail:
            raise RuntimeError("SYNTHETIC_PRIVATE_PROVIDER_FAILURE")
        return self.result.model_copy(deep=True)

    async def complete(self, *args, **kwargs):
        pytest.fail("Responses must not be flattened into Chat Completions")

    async def aclose(self):
        self.closed = True


@pytest.fixture
def responses_app(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", PROVIDER_KEY)
    monkeypatch.setenv("GATEWAY7_RESPONSES_TOKEN", TOKEN)

    def create(provider=None, **extra):
        provider = RecordingNativeProvider() if provider is None else provider
        app_module = importlib.import_module("gateway7.app")
        monkeypatch.setattr(app_module, "build_provider", lambda *_: provider)
        config = GatewayConfig.model_validate(
            {
                "provider": {"kind": "openai", "model": MODEL},
                "auth": {
                    "enabled": True,
                    "clients": {
                        "synthetic": {
                            "token_env": "GATEWAY7_RESPONSES_TOKEN",
                            "models": [MODEL, "gpt-4.1"],
                        }
                    },
                },
                **extra,
            }
        )
        return create_app(config=config), provider

    return create


def policy(term, *, phase="response", action="block"):
    return {
        "module": "gateway7.plugins.content_policy",
        "settings": {"terms": [term], "phase": phase, "action": action},
    }


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()["error"]) == {"message", "type", "param", "code"}
    assert response.json()["error"]["code"] == code
    assert "data:" not in response.text and "response.output_item.done" not in response.text
    assert "SYNTHETIC_PRIVATE" not in response.text


def native_events(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "[DONE]" not in response.text
    assert response.text.endswith("\n\n")
    parsed = []
    for frame in response.text.split("\n\n")[:-1]:
        lines = frame.splitlines()
        names = [line[7:] for line in lines if line.startswith("event: ")]
        data = [line[6:] for line in lines if line.startswith("data: ")]
        assert len(names) == len(data) == 1
        event = json.loads(data[0])
        assert names == [event["type"]]
        parsed.append(event)
    assert [event["sequence_number"] for event in parsed] == list(range(len(parsed)))
    assert parsed[0]["type"] == "response.created"
    assert parsed[-1]["type"] == "response.completed"
    assert sum(event["type"] == "response.completed" for event in parsed) == 1
    return parsed


async def asgi_post(app, *, chunks, headers=(), query=b""):
    """Capture actual ASGI sends and body reads, without a socket or JSON client."""
    sent, reads = [], []
    pending = iter(chunks)

    async def receive():
        try:
            body, more = next(pending)
        except StopIteration:
            await asyncio.Event().wait()
        reads.append(body)
        return {"type": "http.request", "body": body, "more_body": more}

    async def send(event):
        sent.append(dict(event))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "root_path": "",
        "query_string": query,
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "client": ("127.0.0.1", 12345),
        "server": ("synthetic.invalid", 80),
    }
    async with asyncio.timeout(2):
        await app(scope, receive, send)
    starts = [event for event in sent if event["type"] == "http.response.start"]
    assert len(starts) == 1
    response = httpx.Response(
        starts[0]["status"],
        headers=starts[0]["headers"],
        content=b"".join(event.get("body", b"") for event in sent),
    )
    return response, reads, sent


async def test_native_fixtures_are_sdk_valid_and_do_not_own_transport_authority():
    consent = ResponsesConsent()
    dto = ResponsesCreateRequest.model_validate(BODY, context={"consent": consent})
    core = dto.core_request(consent=consent)
    provider = RecordingNativeProvider()
    answer = await provider.complete_responses(core, model=MODEL, stream=True, consent=consent)
    SDK_RESPONSE.validate_python(answer.wire_dict(), strict=True)
    assert answer.output_text == "Synthetic answer" and answer.accounting_usage() == {
        "input_tokens": 7,
        "output_tokens": 4,
    }
    assert (
        not {"model", "stream", "consent", "allow_opaque", "allow_hosted"} & core.wire_dict().keys()
    )
    assert provider.calls[0][1:] == (MODEL, True, consent)
    assert answer is not provider.result
    await provider.aclose()
    assert provider.closed


def test_minimal_json_preserves_native_identity_and_output_token_bounds(responses_app):
    app, provider = responses_app()
    with TestClient(app) as client:
        for limit in (None, 1, 4096):
            body = {**BODY, **({} if limit is None else {"max_output_tokens": limit})}
            result = client.post(PATH, headers=HEADERS, json=body)
            assert result.status_code == 200, result.text
            assert result.headers["content-type"].startswith("application/json")
            data = result.json()
            SDK_RESPONSE.validate_python(data, strict=True)
            assert data["object"] == "response" and data["id"] == "resp_synthetic"
            assert data["model"] == SOURCE_MODEL and data["output"] == [message()]
            assert data["created_at"] == 1800000000.0 and data["usage"] == USAGE
            assert "choices" not in data and result.headers["x-request-id"]
            request, model, stream, consent = provider.calls[-1]
            assert request.max_output_tokens == (1024 if limit is None else limit)
            assert request.wire_dict()["input"] == BODY["input"] and request.store is False
            assert model in (None, MODEL) and stream is False and consent == ResponsesConsent()
            assert not hasattr(request, "model") and not hasattr(request, "stream")
    assert len(provider.calls) == 3 and provider.closed


@pytest.mark.parametrize(
    "headers,query",
    [
        pytest.param([], b"", id="missing"),
        pytest.param([("authorization", "Bearer gateway7-synthetic-wrong")], b"", id="wrong"),
        pytest.param(list(HEADERS.items()) * 2, b"", id="duplicate"),
        pytest.param([("authorization", "Basic " + TOKEN)], b"", id="basic"),
        pytest.param([], ("api_key=" + TOKEN).encode(), id="query"),
        pytest.param([("x-api-key", TOKEN)], b"", id="x-api-key"),
    ],
)
async def test_authentication_precedes_body_read_and_capacity(
    responses_app, caplog, headers, query
):
    app, provider = responses_app()
    with caplog.at_level("INFO", logger="gateway7"):
        async with app.router.lifespan_context(app):
            app.state.admission.limit = 0
            response, reads, _ = await asgi_post(
                app,
                chunks=[(b"{SYNTHETIC_PRIVATE_INVALID_JSON", False)],
                headers=headers,
                query=query,
            )
    assert_error(response, 401, "unauthorized")
    assert response.headers["www-authenticate"] == "Bearer"
    assert reads == [] and provider.calls == []
    assert TOKEN not in response.text + caplog.text
    assert PROVIDER_KEY not in response.text + caplog.text


def test_forbidden_model_is_rejected_before_full_pipeline_admission(responses_app):
    app, provider = responses_app()
    with TestClient(app) as client:
        app.state.admission.limit = 0
        response = client.post(PATH, headers=HEADERS, json={**BODY, "model": "forbidden-model"})
    assert_error(response, 403, "model_forbidden")
    assert provider.calls == [] and app.state.admission.active == 0


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param('{"SYNTHETIC_PRIVATE_MALFORMED":', id="malformed"),
        pytest.param(
            '{"model":"gpt-4.1-mini","input":"SYNTHETIC_PRIVATE_FIRST",'
            '"input":"SYNTHETIC_PRIVATE_SECOND"}',
            id="duplicate-top-level",
        ),
        pytest.param(
            '{"model":"gpt-4.1-mini","input":[{"role":"user",'
            '"content":"SYNTHETIC_PRIVATE_FIRST","content":"SYNTHETIC_PRIVATE_SECOND"}]}',
            id="duplicate-nested",
        ),
        pytest.param(json.dumps({**BODY, "store": True}), id="storage"),
        pytest.param(
            json.dumps({**BODY, "SYNTHETIC_PRIVATE_FIELD": "SYNTHETIC_PRIVATE_VALUE"}),
            id="unknown-field",
        ),
        pytest.param(json.dumps({**BODY, "max_output_tokens": 0}), id="zero-output-tokens"),
        pytest.param(json.dumps({**BODY, "max_output_tokens": 4097}), id="excess-output-tokens"),
    ],
)
def test_invalid_json_and_unsupported_controls_are_sanitized_without_attempts(
    responses_app, caplog, raw
):
    app, provider = responses_app()
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        response = client.post(
            PATH, headers={**HEADERS, "content-type": "application/json"}, content=raw
        )
        metrics = client.get("/metrics").text
    assert_error(response, 400, "invalid_request")
    assert "SYNTHETIC_PRIVATE" not in response.text + caplog.text + metrics
    assert provider.calls == []


@pytest.mark.parametrize("declared_length", [False, True], ids=["chunked", "content-length"])
async def test_body_limit_covers_declared_and_chunked_bodies(responses_app, declared_length):
    app, provider = responses_app(limits={"max_body_bytes": 128})
    headers = [*HEADERS.items(), ("content-type", "application/json")]
    if declared_length:
        headers.append(("content-length", "256"))
    else:
        headers.append(("transfer-encoding", "chunked"))
    async with app.router.lifespan_context(app):
        response, reads, _ = await asgi_post(
            app, chunks=[(b"x" * 80, True), (b"x" * 80, False)], headers=headers
        )
    assert_error(response, 413, "body_too_large")
    assert len(reads) == (0 if declared_length else 2) and provider.calls == []


@pytest.mark.parametrize(
    "consent_headers",
    [
        pytest.param([("X-Gateway7-Allow-Opaque", "True")], id="case-sensitive"),
        pytest.param([("X-Gateway7-Allow-Hosted-Tools", " true")], id="no-trimming"),
        pytest.param([("X-Gateway7-Allow-Opaque", "false")] * 2, id="duplicate-opaque"),
        pytest.param([("X-Gateway7-Allow-Hosted-Tools", "true")] * 2, id="duplicate-hosted"),
    ],
)
def test_consent_headers_are_strict_even_for_plaintext(responses_app, consent_headers):
    app, provider = responses_app()
    with TestClient(app) as client:
        response = client.post(PATH, headers=[*HEADERS.items(), *consent_headers], json=BODY)
    assert_error(response, 400, "invalid_request")
    assert provider.calls == []


def test_checked_native_sse_is_sdk_valid_and_snapshots_match_text(responses_app):
    text = 'Synthetic\n"quoted" — 🌍\ud800\nevent: injected\ndata: not-an-event'
    app, provider = responses_app(RecordingNativeProvider(native_response(message(text))))
    with TestClient(app) as client:
        response = client.post(PATH, headers=HEADERS, json={**BODY, "stream": True})
    events = native_events(response)
    for event in events:
        SDK_EVENT.validate_python(event, strict=True)
    terminal = events[-1]["response"]
    SDK_RESPONSE.validate_python(terminal, strict=True)
    assert (
        "".join(event["delta"] for event in events if event["type"] == "response.output_text.delta")
        == text
    )
    assert terminal["output"] == [message(text)] and terminal["usage"] == USAGE
    assert [
        event["item"] for event in events if event["type"] == "response.output_item.done"
    ] == terminal["output"]
    assert len({event["response"]["id"] for event in events if "response" in event}) == 1
    assert len(provider.calls) == 1 and provider.calls[0][2] is True


async def test_actual_sdk_responses_and_events_use_only_in_process_asgi(responses_app):
    app, provider = responses_app()
    async with app.router.lifespan_context(app):
        async with AsyncOpenAI(
            api_key=TOKEN,
            base_url="http://synthetic.invalid/v1",
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), trust_env=False, timeout=2
            ),
            _strict_response_validation=True,
        ) as sdk:
            response = await sdk.responses.create(model=MODEL, input=BODY["input"], store=False)
            assert isinstance(response, Response)
            assert response.output_text == "Synthetic answer" and response.usage.total_tokens == 11
            stream = await sdk.responses.create(
                model=MODEL, input="hello", store=False, stream=True
            )
            async with stream:
                events = [event async for event in stream]
            assert events[0].type == "response.created" and events[-1].type == "response.completed"
            assert (
                "".join(
                    event.delta for event in events if event.type == "response.output_text.delta"
                )
                == "Synthetic answer"
            )
            assert events[-1].response.output == response.output
    assert len(provider.calls) == 2 and [call[2] for call in provider.calls] == [False, True]


def test_provider_failure_is_sanitized_before_any_checked_sse_delivery(responses_app, caplog):
    app, provider = responses_app(RecordingNativeProvider(fail=True))
    with caplog.at_level("INFO", logger="gateway7"), TestClient(app) as client:
        response = client.post(PATH, headers=HEADERS, json={**BODY, "stream": True})
        metrics = client.get("/metrics").text
    assert_error(response, 502, "provider_error")
    assert "SYNTHETIC_PRIVATE_PROVIDER_FAILURE" not in response.text + caplog.text + metrics
    assert TOKEN not in response.text + caplog.text + metrics
    assert PROVIDER_KEY not in response.text + caplog.text + metrics
    assert len(provider.calls) == 1


def test_unknown_and_partial_usage_remain_source_reported(responses_app):
    app, provider = responses_app()
    with TestClient(app) as client:
        for usage, stream in ((None, False), ({"input_tokens": 7}, True)):
            provider.result = native_response(usage=usage)
            response = client.post(PATH, headers=HEADERS, json={**BODY, "stream": stream})
            if stream:
                actual = native_events(response)[-1]["response"]
            else:
                assert response.status_code == 200, response.text
                actual = response.json()
            assert actual["usage"] == usage
    assert len(provider.calls) == 2


def test_request_policy_denies_before_attempt_and_mask_reaches_native_provider(responses_app):
    app, provider = responses_app(
        plugins={
            "guard": policy("SYNTHETIC_PRIVATE_BLOCK", phase="request"),
            "mask": {"module": "gateway7.plugins.email_mask", "settings": {"phase": "request"}},
        },
        middleware=["guard", "mask"],
    )
    with TestClient(app) as client:
        blocked = client.post(
            PATH, headers=HEADERS, json={**BODY, "input": "SYNTHETIC_PRIVATE_BLOCK"}
        )
        assert_error(blocked, 403, "policy_denied")
        assert provider.calls == []
        allowed = client.post(PATH, headers=HEADERS, json={**BODY, "input": "user@example.com"})
    assert allowed.status_code == 200, allowed.text
    assert len(provider.calls) == 1 and provider.calls[0][0].input == "[EMAIL]"


async def test_default_whole_response_block_sends_only_json_denial(responses_app, caplog):
    term = "SYNTHETIC_PRIVATE_OUTPUT"
    app, provider = responses_app(
        RecordingNativeProvider(native_response(message(term))),
        plugins={"guard": policy(term)},
        middleware=["guard"],
    )
    with caplog.at_level("INFO", logger="gateway7"):
        async with app.router.lifespan_context(app):
            response, _, sent = await asgi_post(
                app,
                chunks=[(json.dumps({**BODY, "stream": True}).encode(), False)],
                headers=[*HEADERS.items(), ("content-type", "application/json")],
            )
    assert_error(response, 403, "policy_denied")
    assert [event["status"] for event in sent if event["type"] == "http.response.start"] == [403]
    assert term not in response.text + caplog.text and len(provider.calls) == 1


def test_response_redaction_is_consistent_across_all_native_snapshots(responses_app):
    app, provider = responses_app(
        RecordingNativeProvider(native_response(message("SYNTHETIC_PRIVATE_REDACT"))),
        plugins={"redact": policy("SYNTHETIC_PRIVATE_REDACT", action="redact")},
        middleware=["redact"],
    )
    with TestClient(app) as client:
        response = client.post(PATH, headers=HEADERS, json={**BODY, "stream": True})
    events = native_events(response)
    assert "SYNTHETIC_PRIVATE_REDACT" not in response.text
    assert (
        "".join(event["delta"] for event in events if event["type"] == "response.output_text.delta")
        == "[removed]"
    )
    assert [event["text"] for event in events if event["type"] == "response.output_text.done"] == [
        "[removed]"
    ]
    assert [
        event["part"]["text"] for event in events if event["type"] == "response.content_part.done"
    ] == ["[removed]"]
    assert events[-1]["response"]["output"] == [message("[removed]")]
    assert [event["item"] for event in events if event["type"] == "response.output_item.done"] == [
        message("[removed]")
    ]
    assert len(provider.calls) == 1


def test_forbidden_structured_arguments_never_release_an_executable_done(responses_app):
    call = function_call(arguments='{"path":"SYNTHETIC_PRIVATE_ARGUMENT"}')
    app, provider = responses_app(
        RecordingNativeProvider(native_response(call)),
        plugins={"guard": policy("SYNTHETIC_PRIVATE_ARGUMENT", action="redact")},
        middleware=["guard"],
    )
    with TestClient(app) as client:
        response = client.post(
            PATH, headers=HEADERS, json={**BODY, "stream": True, "tools": [FUNCTION]}
        )
    assert_error(response, 403, "policy_denied")
    assert "fc_item_a" not in response.text and len(provider.calls) == 1


def test_ordered_parallel_namespace_functions_and_custom_raw_input_survive_http(responses_app):
    tools = [
        {"type": "namespace", "name": name, "description": "Synthetic tools", "tools": [FUNCTION]}
        for name in ("alpha", "beta")
    ] + [CUSTOM]
    calls = [function_call("a", namespace="alpha"), function_call("b", namespace="beta")]
    custom = {
        "type": "custom_tool_call",
        "id": "ctc_item_patch",
        "call_id": "call_patch",
        "name": "apply_patch",
        "input": RAW_PATCH,
        "status": "completed",
    }
    output = [calls[0], message("Between calls"), calls[1], custom]
    app, provider = responses_app(RecordingNativeProvider(native_response(*output)))
    with TestClient(app) as client:
        response = client.post(
            PATH,
            headers=HEADERS,
            json={**BODY, "stream": True, "tools": tools, "parallel_tool_calls": True},
        )
        events = native_events(response)
        assert events[-1]["response"]["output"] == output
        assert [
            event["item"] for event in events if event["type"] == "response.output_item.done"
        ] == output
        for index, call in ((0, calls[0]), (2, calls[1]), (3, custom)):
            family = (
                "response.custom_tool_call_input"
                if index == 3
                else "response.function_call_arguments"
            )
            deltas = [
                event
                for event in events
                if event["type"] == family + ".delta" and event["output_index"] == index
            ]
            assert all(event["item_id"] == call["id"] for event in deltas)
            assert (
                "".join(event["delta"] for event in deltas)
                == call["input" if index == 3 else "arguments"]
            )
            assert call["call_id"] != call["id"]
        for event in events:
            SDK_EVENT.validate_python(event, strict=True)
        provider.result = native_response(message("After results"))
        history = [
            *calls,
            {"type": "function_call_output", "call_id": "call_b", "output": "beta result"},
            {"type": "function_call_output", "call_id": "call_a", "output": "alpha result"},
            custom,
            {"type": "custom_tool_call_output", "call_id": "call_patch", "output": "Applied"},
            *BODY["input"],
        ]
        continuation = client.post(
            PATH, headers=HEADERS, json={**BODY, "input": history, "tools": tools}
        )
    assert continuation.status_code == 200, continuation.text
    assert provider.calls[-1][0].wire_dict()["input"] == history
    assert provider.calls[0][0].wire_dict()["tools"] == tools and len(provider.calls) == 2


def test_opaque_history_and_include_need_explicit_consent_but_plaintext_is_checked(responses_app):
    old = {"type": "reasoning", "id": "rs_old", "summary": [], "encrypted_content": OPAQUE}
    new = {**old, "id": "rs_new", "status": "completed"}
    app, provider = responses_app(
        RecordingNativeProvider(native_response(new, message())),
        plugins={"guard": policy("SYNTHETIC_PRIVATE_PLAINTEXT", phase="request")},
        middleware=["guard"],
    )
    body = {**BODY, "input": [old, *BODY["input"]]}
    with TestClient(app) as client:
        for denied in (body, {**BODY, "include": ["reasoning.encrypted_content"]}):
            response = client.post(PATH, headers=HEADERS, json=denied)
            assert_error(response, 400, "invalid_request")
            assert provider.calls == []
        false = client.post(
            PATH, headers={**HEADERS, "X-Gateway7-Allow-Opaque": "false"}, json=body
        )
        assert_error(false, 400, "invalid_request")
        assert provider.calls == []
        headers = {**HEADERS, "X-Gateway7-Allow-Opaque": "true"}
        allowed = client.post(
            PATH,
            headers=headers,
            json={**body, "stream": True, "include": ["reasoning.encrypted_content"]},
        )
        events = native_events(allowed)
        assert events[-1]["response"]["output"][0]["encrypted_content"] == OPAQUE
        assert provider.calls[0][0].wire_dict()["input"] == body["input"]
        assert provider.calls[0][0].include == ["reasoning.encrypted_content"]
        assert provider.calls[0][3] == ResponsesConsent(allow_opaque=True)
        assert (
            not {"consent", "allow_opaque", "allow_hosted"}
            & provider.calls[0][0].wire_dict().keys()
        )
        blocked = client.post(
            PATH,
            headers=headers,
            json={
                **body,
                "input": [old, {"role": "user", "content": "SYNTHETIC_PRIVATE_PLAINTEXT"}],
            },
        )
        assert_error(blocked, 403, "policy_denied")
    assert len(provider.calls) == 1


def test_hosted_web_search_has_independent_default_denied_consent(responses_app):
    search = {
        "type": "web_search_call",
        "id": "ws_synthetic",
        "status": "completed",
        "action": {"type": "search", "query": "Synthetic"},
    }
    app, provider = responses_app(RecordingNativeProvider(native_response(search, message())))
    body = {**BODY, "tools": [{"type": "web_search", "external_web_access": False}]}
    with TestClient(app) as client:
        for headers in (
            HEADERS,
            {**HEADERS, "X-Gateway7-Allow-Opaque": "true"},
            {**HEADERS, "X-Gateway7-Allow-Hosted-Tools": "false"},
        ):
            denied = client.post(PATH, headers=headers, json=body)
            assert_error(denied, 400, "invalid_request")
            assert provider.calls == []
        allowed = client.post(
            PATH, headers={**HEADERS, "X-Gateway7-Allow-Hosted-Tools": "true"}, json=body
        )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["output"][0] == search
    assert len(provider.calls) == 1 and provider.calls[0][3] == ResponsesConsent(allow_hosted=True)


def test_third_party_chat_plugin_without_native_hooks_is_rejected_before_any_hook(
    responses_app, monkeypatch
):
    calls = []

    class Settings(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    class Legacy:
        async def handle(self, request, context, call_next):
            calls.append("chat")
            return await call_next(request)

    module = ModuleType("synthetic_responses_api_legacy_plugin")
    module.PLUGIN = PluginDescriptor("synthetic-legacy", 2, Settings, lambda _: Legacy())
    monkeypatch.setitem(sys.modules, module.__name__, module)
    app, provider = responses_app(
        plugins={"legacy": {"module": module.__name__}}, middleware=["legacy"]
    )
    with TestClient(app) as client:
        response = client.post(PATH, headers=HEADERS, json=BODY)
    assert_error(response, 400, "invalid_request")
    assert provider.calls == [] and calls == []


def test_http_provider_uses_native_path_pinned_model_and_no_gateway_consent_headers(responses_app):
    attempts = []

    def handle(wire):
        attempts.append(wire)
        assert str(wire.url) == "https://api.openai.com/v1/responses"
        assert wire.headers["authorization"] == "Bearer " + PROVIDER_KEY
        assert not any(name.startswith("x-gateway7-") for name in wire.headers)
        payload = json.loads(wire.content)
        assert payload["model"] == "gpt-4.1" and payload["stream"] is False
        assert payload["store"] is False and payload["max_output_tokens"] == 1024
        assert payload["input"] == BODY["input"]
        assert not {"allow_opaque", "allow_hosted", "consent", "messages"} & payload.keys()
        return httpx.Response(200, json=native_response().wire_dict())

    provider = build_provider(
        ProviderConfig(kind="openai", model=MODEL),
        PROVIDER_KEY,
        transport=httpx.MockTransport(handle),
    )
    app, _ = responses_app(provider)
    with TestClient(app) as client:
        response = client.post(
            PATH,
            headers={
                **HEADERS,
                "X-Gateway7-Allow-Opaque": "true",
                "X-Gateway7-Allow-Hosted-Tools": "true",
            },
            json={**BODY, "model": "gpt-4.1"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["model"] == SOURCE_MODEL and response.json()["usage"] == USAGE
    assert len(attempts) == 1 and provider._client.is_closed

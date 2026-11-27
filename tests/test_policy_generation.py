"""The generation endpoints return validated suggestions without modifying live policies."""

import json

import httpx
import pytest

from test_admin_operations import managed as managed_fixture, read, write

managed = managed_fixture
DRAFT = "/operator/policy-draft/generate"
CASES = "/operator/policy-draft/generate-cases"
SPEC = {"id": "mask", "label": "Phone", "template": "phone_mask", "phase": "request"}
PLAN = {"positive": "repeated", "negative": "ordinary", "boundary": "adjacent"}


def fake_ollama(monkeypatch, result, requests):
    client = httpx.AsyncClient

    def respond(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert "authorization" not in request.headers
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(result)}})

    monkeypatch.setenv("GATEWAY7_DRAFT_OLLAMA_MODEL", "test-fixture")
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(respond), **kw)
    )


@pytest.mark.parametrize(
    "path,body,result",
    [
        (DRAFT, {"description": "Mask a synthetic phone"}, SPEC),
        (CASES, {"template": "phone_mask"}, PLAN),
    ],
)
def test_generation_endpoints(managed, monkeypatch, path, body, result):
    _, client, provider = managed
    requests = []
    fake_ollama(monkeypatch, result, requests)
    before = read(client, "/operator/policies")
    assert client.post(path, json=body).status_code == 401
    response = write(client, path, body)
    assert response.status_code == 200, response.text
    assert len(requests) == 1 and requests[0]["format"]["additionalProperties"] is False
    assert provider.calls == 0 and read(client, "/operator/policies") == before
    if path == DRAFT:
        assert response.json()["spec"]["template"] == "phone_mask"
    else:
        assert [item["kind"] for item in response.json()["cases"]] == [
            "positive",
            "negative",
            "boundary",
        ]
        assert "+7 000 000-00-00" in response.json()["cases"][0]["text"]


def test_generation_fails_closed(managed, monkeypatch):
    _, client, _ = managed
    monkeypatch.delenv("GATEWAY7_DRAFT_OLLAMA_MODEL", raising=False)
    assert write(client, DRAFT, {"description": "Mask a phone"}).status_code == 503
    fake_ollama(monkeypatch, {**SPEC, "python": "synthetic-unsafe-output"}, [])
    response = write(client, DRAFT, {"description": "Mask a phone"})
    assert response.status_code == 502
    assert "synthetic-unsafe-output" not in response.text

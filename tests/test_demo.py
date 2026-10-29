"""Fixture checks; `python -m demo.run` separately exercises real processes."""

from fastapi.testclient import TestClient
import pytest

from demo.fault_tolerance import run as fault_tolerance
from demo.upstream import ANSWER, MAX_BODY_BYTES, USAGE, app


KEY = "gateway7-synthetic-fixture-test"


def test_fake_requires_key_and_inspection_never_retains_headers(monkeypatch):
    monkeypatch.setenv("DEMO_PROVIDER_KEY", KEY)
    body = {"messages": [{"role": "user", "content": "synthetic ping"}], "max_tokens": 32}
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/chat", json=body).status_code == 401
        assert client.post("/chat", json=body, headers={"authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/requests").json() == {"requests": []}
        result = client.post("/chat", json=body, headers={"authorization": "Bearer " + KEY})
        assert result.json() == {"text": ANSWER, "usage": USAGE}
        inspection = client.get("/requests")
        assert inspection.json() == {"requests": [{"body": body, "key_accepted": True}]}
        assert KEY not in result.text + inspection.text


def test_fake_rejects_oversized_or_invalid_body_without_retaining_it(monkeypatch):
    monkeypatch.setenv("DEMO_PROVIDER_KEY", KEY)
    with TestClient(app) as client:
        headers = {"authorization": "Bearer " + KEY}
        assert client.post("/chat", content=b"x" * (MAX_BODY_BYTES + 1), headers=headers).status_code == 413
        result = client.post("/chat", content=KEY, headers=headers)
        assert result.status_code == 400
        assert KEY not in result.text
        assert client.get("/requests").json() == {"requests": []}


@pytest.mark.parametrize("key", [None, "not-an-explicit-synthetic-key"])
def test_fake_does_not_start_without_explicit_synthetic_key(monkeypatch, key):
    monkeypatch.delenv("DEMO_PROVIDER_KEY", raising=False)
    if key:
        monkeypatch.setenv("DEMO_PROVIDER_KEY", key)
    with pytest.raises(RuntimeError, match="explicitly synthetic"):
        with TestClient(app):
            pass


def test_fault_tolerance_check_passes_every_case_without_upstream_requests(capsys):
    assert fault_tolerance(2)
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines[1:]] == [
        "PASS raise", "PASS deny", "PASS overrun", "PASS late", "PASS QR-01",
    ]

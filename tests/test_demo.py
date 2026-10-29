"""Fixture checks; `python -m demo.run` separately exercises real processes."""

from fastapi.testclient import TestClient
import pytest

from demo.fault_tolerance import run as fault_tolerance
from demo.run import SYNTHETIC_KEY, _failure_diagnosis, _trace_events
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


REQUEST_ID = "a" * 32


def _failure_log(*, phase="request", calls=0):
    rows = [
        ("start", "mask", "request"),
        ("continue", "mask", "request"),
        ("start", "fault", "request"),
    ]
    if calls:
        rows.extend(
            [
                ("continue", "fault", "request"),
                ("start", "provider", "provider"),
                ("complete", "provider", "provider"),
                ("start", "fault", "response"),
            ]
        )
    rows.extend(
        [
            ("plugin_error", "fault", phase),
            ("plugin_error", "mask", "response"),
            ("http_500", "http", None),
        ]
    )
    return "\n".join(
        f"request_id={REQUEST_ID} outcome={outcome} component={component} "
        + (f"phase={event_phase} " if event_phase else "")
        + "duration_ms=1.250"
        for outcome, component, event_phase in rows
    )


def _diagnose(output, *, phase="request", calls=0):
    return _failure_diagnosis(
        output,
        REQUEST_ID,
        {"mask", "fault", "sample"},
        component="fault",
        phase=phase,
        code="plugin_error",
        status=500,
        calls=calls,
    )


@pytest.mark.parametrize("phase,calls", [("request", 0), ("response", 1)])
def test_failure_diagnosis_correlates_origin_http_and_observed_upstream_calls(phase, calls):
    output = _failure_log(phase=phase, calls=calls)
    unrelated = output.replace(REQUEST_ID, "b" * 32)
    diagnosis = _diagnose(
        "INFO: startup complete\n" + unrelated + "\n" + output, phase=phase, calls=calls
    )
    assert diagnosis == (
        f"reason=plugin_error component=fault phase={phase} duration_ms=1.250 "
        f"request_id={REQUEST_ID}; "
        f"terminal=http_500; upstream_calls={calls}"
    )


@pytest.mark.parametrize(
    "old,new",
    [
        (REQUEST_ID, "b" * 32),
        ("component=fault", "component=sample"),
        ("phase=request", "phase=response"),
        ("outcome=plugin_error", "outcome=timeout"),
        ("outcome=http_500", "outcome=http_504"),
    ],
)
def test_failure_diagnosis_rejects_wrong_correlated_fields(old, new):
    with pytest.raises(AssertionError):
        _diagnose(_failure_log().replace(old, new))


@pytest.mark.parametrize("missing", ["all", "origin", "http", "provider-completion"])
def test_failure_diagnosis_rejects_missing_events(missing):
    lines = _failure_log(phase="response", calls=1).splitlines()
    if missing == "all":
        lines = []
    elif missing == "origin":
        lines = [line for line in lines if "outcome=plugin_error component=fault " not in line]
    elif missing == "http":
        lines = lines[:-1]
    else:
        lines = [line for line in lines if "outcome=complete component=provider " not in line]
    with pytest.raises(AssertionError):
        _diagnose("\n".join(lines), phase="response", calls=1)


def test_failure_diagnosis_does_not_mistake_propagated_outer_failure_for_origin():
    with pytest.raises(AssertionError, match="Wrong originating failure"):
        _failure_diagnosis(
            _failure_log(),
            REQUEST_ID,
            {"mask", "fault"},
            component="mask",
            phase="response",
            code="plugin_error",
            status=500,
            calls=0,
        )


@pytest.mark.parametrize("calls", [0, 2])
def test_failure_diagnosis_rejects_wrong_number_of_upstream_calls(calls):
    with pytest.raises(AssertionError):
        _diagnose(_failure_log(phase="response", calls=1), phase="response", calls=calls)


@pytest.mark.parametrize(
    "change",
    [
        lambda line: line + " detail=private-request-text",
        lambda line: line + " " + SYNTHETIC_KEY,
        lambda line: line + " RuntimeError: arbitrary-private-exception",
        lambda line: line.replace("component=fault", "component=private-component"),
        lambda line: line.replace("duration_ms=1.250", "duration_ms=NaN"),
        lambda line: line.replace("duration_ms=1.250", "duration_ms=" + "1" * 300),
        lambda line: line.replace(REQUEST_ID, REQUEST_ID + "0"),
    ],
)
def test_trace_parser_rejects_unbounded_or_untrusted_correlated_fields(change):
    line = _failure_log().splitlines()[2]
    with pytest.raises(AssertionError) as error:
        _trace_events(change(line), REQUEST_ID, {"mask", "fault"})
    assert SYNTHETIC_KEY not in str(error.value)
    assert all(
        value not in str(error.value)
        for value in (
            "private-request-text",
            "arbitrary-private-exception",
            "private-component",
        )
    )


@pytest.mark.parametrize(
    "raw",
    [
        "synthetic-demo-exception-must-not-be-exposed",
        "RuntimeError: arbitrary-private-exception",
        "Traceback (most recent call last):",
        "synthetic raw request text",
    ],
)
def test_trace_parser_rejects_raw_exception_or_request_text_outside_structured_events(raw):
    with pytest.raises(AssertionError):
        _trace_events(
            _failure_log() + "\n" + raw,
            REQUEST_ID,
            {"mask", "fault"},
            forbidden=("synthetic raw request text",),
        )


def test_fault_tolerance_check_passes_every_case_without_upstream_requests(capsys):
    assert fault_tolerance(2)
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines[1:]] == [
        "PASS raise", "PASS deny", "PASS overrun", "PASS late", "PASS QR-01",
    ]

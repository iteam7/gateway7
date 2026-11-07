"""Protocol tests for the deployed check; these are not a staging QRT execution."""

import base64
import json
import re
from pathlib import Path

import httpx
import pytest

from scripts.check_sli import (
    COUNT_QUERY,
    SLI_QUERY,
    CheckFailure,
    Probe,
    Settings,
    main,
)

REQUEST_ID = "e58cc159e1bd402d89b26da912f68001"
COMMIT = "a" * 40
USER, SECRET, TOKEN = "synthetic-reader", "synthetic-reader-secret", "synthetic-client-token"
AUTH = "Basic " + base64.b64encode(f"{USER}:{SECRET}".encode()).decode()
SETTINGS = Settings("http://staging.test", "http://observe.test", AUTH, COMMIT, TOKEN)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def wall_time(self):
        return 1_790_000_000 + self.now

    async def sleep(self, seconds):
        self.now += seconds


class Backend:
    """A typed HTTP fixture that implements only the protocol the check reads."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.log_ready_at = 1.0
        self.metric_ready_at = 10.0
        self.log_changes = {}
        self.p95 = "2.5"
        self.p95_labels = {"route": "openai_chat", "outcome": "client_error"}
        self.stale_count = False
        self.slow_log = False

    def __call__(self, request):
        self.calls.append(request)
        if request.url.host == "staging.test":
            if request.url.path == "/ready":
                assert "authorization" not in request.headers
                return httpx.Response(200, json={"status": "ready"})
            if request.url.path == "/v1/models":
                if "authorization" not in request.headers:
                    return httpx.Response(401, json={"error": {"code": "unauthorized"}})
                assert request.headers["authorization"] == "Bearer " + TOKEN
                return httpx.Response(200, json={"data": [{"id": "allowed-model"}]})
            assert request.url.path == "/v1/chat/completions" and request.method == "POST"
            assert request.headers["authorization"] == "Bearer " + TOKEN
            assert json.loads(request.content) == {
                "model": "gateway7-qr05-forbidden-model",
                "messages": [{"role": "user", "content": "analysability check"}],
            }
            return httpx.Response(
                403,
                headers={"X-Request-ID": REQUEST_ID},
                json={"request_id": REQUEST_ID, "error": {"code": "model_forbidden"}},
            )
        assert request.url.host == "observe.test"
        assert request.headers["Authorization"] == SETTINGS.authorization
        if request.url.path == "/api/staging/_search":
            body = json.loads(request.content)
            assert f"WHERE request_id = '{REQUEST_ID}'" in body["query"]["sql"]
            assert body["query"]["start_time"] < body["query"]["end_time"]
            if self.slow_log:
                self.clock.now += 5.001
            log = {
                "request_id": REQUEST_ID,
                "route": "openai_chat",
                "outcome": "client_error",
                "status": 403,
                "error_code": "model_forbidden",
                "duration_ms": 1.7,
                **self.log_changes,
            }
            return httpx.Response(
                200, json={"hits": [log] if self.clock.now >= self.log_ready_at else []}
            )
        assert request.url.path == "/api/staging/prometheus/api/v1/query"
        query = request.url.params["query"]
        assert "time" in request.url.params
        if query == COUNT_QUERY:
            count = "3" if self.stale_count or self.clock.now < self.metric_ready_at else "4"
            result = [{"metric": {}, "value": [self.clock.wall_time(), count]}]
        else:
            assert query == SLI_QUERY
            result = [{"metric": self.p95_labels, "value": [self.clock.wall_time(), self.p95]}]
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "vector", "result": result}}
        )


async def run_fixture(backend, clock):
    async with httpx.AsyncClient(transport=httpx.MockTransport(backend), trust_env=False) as client:
        return await Probe(
            client, monotonic=clock.monotonic, wall_time=clock.wall_time, sleep=clock.sleep
        ).run(SETTINGS)


async def test_request_and_export_lag_are_checked_against_the_response():
    clock = Clock()
    backend = Backend(clock)
    result = await run_fixture(backend, clock)
    assert result["result"] == "PASS"
    assert result["log_queryable_seconds"] == 1.0
    assert result["p95_queryable_seconds"] == 10.0
    assert result["p95_duration_ms"] == 2.5
    assert result["request_id"] == REQUEST_ID
    assert result["histogram_count_increase"] == 1
    assert result["target_confirmation"] == result["commit_source"] == "operator assertion"
    assert SETTINGS.gateway not in json.dumps(result)
    assert SETTINGS.backend not in json.dumps(result)
    assert SETTINGS.authorization not in json.dumps(result)


@pytest.mark.parametrize("log_delay,metric_delay", [(5.01, 10), (1, 60.01)])
async def test_delayed_points_fail_without_extending_the_allowed_windows(log_delay, metric_delay):
    clock = Clock()
    backend = Backend(clock)
    backend.log_ready_at, backend.metric_ready_at = log_delay, metric_delay
    with pytest.raises(CheckFailure, match="deadline|within the required window"):
        await run_fixture(backend, clock)
    assert clock.now in (5.0, 60.0)


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": "a" * 32},
        {"route": "models"},
        {"outcome": "ok"},
        {"status": "403"},
        {"error_code": "none"},
        {"duration_ms": "NaN"},
        {"duration_ms": -1},
        {"duration_ms": True},
    ],
)
async def test_log_must_match_the_tested_request_and_failure(changes):
    clock = Clock()
    backend = Backend(clock)
    backend.log_changes = changes
    with pytest.raises(CheckFailure):
        await run_fixture(backend, clock)
    assert clock.now == 5.0


async def test_old_p95_cannot_pass_without_a_new_histogram_observation():
    clock = Clock()
    backend = Backend(clock)
    backend.stale_count = True
    with pytest.raises(CheckFailure):
        await run_fixture(backend, clock)
    assert not any(request.url.params.get("query") == SLI_QUERY for request in backend.calls)


@pytest.mark.parametrize("p95", ["NaN", "+Inf", "-Inf", "-0.1", None, True])
async def test_p95_must_be_a_finite_nonnegative_number(p95):
    clock = Clock()
    backend = Backend(clock)
    backend.p95 = p95
    with pytest.raises(CheckFailure):
        await run_fixture(backend, clock)
    assert clock.now == 60.0


async def test_numeric_p95_for_a_different_series_is_not_evidence():
    clock = Clock()
    backend = Backend(clock)
    backend.p95_labels = {"route": "openai_chat", "outcome": "ok"}
    with pytest.raises(CheckFailure):
        await run_fixture(backend, clock)


async def test_slow_successful_log_query_cannot_hide_a_missed_deadline():
    clock = Clock()
    backend = Backend(clock)
    backend.slow_log = True
    with pytest.raises(CheckFailure, match="deadline"):
        await run_fixture(backend, clock)


async def test_slow_successful_p95_query_cannot_hide_a_missed_deadline():
    clock = Clock()
    backend = Backend(clock)

    def handler(request):
        response = backend(request)
        if request.url.params.get("query") == SLI_QUERY:
            clock.now = 60.001
        return response

    with pytest.raises(CheckFailure, match="deadline"):
        await run_fixture(handler, clock)


async def test_a_slow_response_body_is_included_in_the_query_deadline():
    clock = Clock()
    backend = Backend(clock)

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            clock.now += 5.001
            yield b'{"hits": []}'

    def handler(request):
        if request.url.path == "/api/staging/_search":
            return httpx.Response(200, stream=SlowBody())
        return backend(request)

    with pytest.raises(CheckFailure, match="deadline"):
        await run_fixture(handler, clock)


@pytest.mark.parametrize("log_delay,metric_delay", [(6, 10), (3, 61)])
async def test_response_cleanup_cannot_extend_the_five_or_sixty_second_window(
    log_delay, metric_delay
):
    clock = Clock()
    backend = Backend(clock)
    backend.log_ready_at, backend.metric_ready_at = log_delay, metric_delay

    class SlowCloseBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(
                {"request_id": REQUEST_ID, "error": {"code": "model_forbidden"}}
            ).encode()

        async def aclose(self):
            clock.now += 2

    def handler(request):
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(403, headers={"X-Request-ID": REQUEST_ID}, stream=SlowCloseBody())
        return backend(request)

    with pytest.raises(CheckFailure, match="deadline|within the required window"):
        await run_fixture(handler, clock)
    assert clock.now in (5, 60)


@pytest.mark.parametrize("unsafe", ["auth-disabled", "model-allowed"])
async def test_gateway_preflight_prevents_any_chat_when_policy_cannot_reject(unsafe):
    clock = Clock()
    backend = Backend(clock)

    def handler(request):
        if request.url.path == "/v1/models" and (
            unsafe == "auth-disabled" or "authorization" in request.headers
        ):
            return httpx.Response(200, json={"data": [{"id": "gateway7-qr05-forbidden-model"}]})
        return backend(request)

    with pytest.raises(CheckFailure):
        await run_fixture(handler, clock)
    assert not any(request.method == "POST" for request in backend.calls)


async def test_bad_query_is_not_treated_as_a_zero_baseline():
    clock = Clock()
    backend = Backend(clock)

    def handler(request):
        if request.url.host == "observe.test":
            return httpx.Response(400, json={"error": "private query error"})
        return backend(request)

    with pytest.raises(CheckFailure, match="HTTP query failed"):
        await run_fixture(handler, clock)
    assert not any(request.method == "POST" for request in backend.calls)


@pytest.mark.parametrize("content", [b"private malformed response", b"x" * 65_537])
async def test_invalid_or_oversized_responses_fail_without_echoing_them(content):
    clock = Clock()
    backend = Backend(clock)

    def handler(request):
        if request.url.path == "/api/staging/_search":
            return httpx.Response(200, content=content)
        return backend(request)

    with pytest.raises(CheckFailure) as error:
        await run_fixture(handler, clock)
    assert "private" not in str(error.value)
    assert "response" not in str(error.value) or "size limit" in str(error.value)


async def test_untrusted_response_identifier_is_not_interpolated_into_sql():
    clock = Clock()
    backend = Backend(clock)
    sent_search = False

    def handler(request):
        nonlocal sent_search
        if request.url.path == "/api/staging/_search":
            sent_search = True
        if request.url.path == "/v1/chat/completions":
            request_id = "id' OR true--"
            return httpx.Response(
                403,
                headers={"X-Request-ID": request_id},
                json={"request_id": request_id, "error": {"code": "model_forbidden"}},
            )
        return backend(request)

    with pytest.raises(CheckFailure, match="identifier"):
        await run_fixture(handler, clock)
    assert not sent_search


@pytest.mark.parametrize("status", [302, 401, 403, 500])
async def test_backend_http_errors_are_sanitized_and_redirects_not_followed(status):
    def handler(request):
        if request.url.host == "staging.test":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(
            status, text="secret at http://private.test", headers={"Location": "http://other.test"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CheckFailure) as error:
            await Probe(client).run(SETTINGS)
    assert "private.test" not in str(error.value) and "secret" not in str(error.value)


def test_staging_and_full_commit_are_explicit_operator_assertions():
    env = {
        "GATEWAY7_ENVIRONMENT": "staging",
        "OPENOBSERVE_ORG": "staging",
        "STAGING_URL": SETTINGS.gateway,
        "OPENOBSERVE_URL": SETTINGS.backend,
        "OPENOBSERVE_USER": USER,
        "OPENOBSERVE_TOKEN": SECRET,
        "GATEWAY7_CLIENT_TOKEN": TOKEN,
    }
    assert Settings.load(env, COMMIT, True) == SETTINGS
    for changed in (
        {"GATEWAY7_ENVIRONMENT": "production"},
        {"OPENOBSERVE_ORG": "production"},
        {"STAGING_URL": "https://person:secret@private.test"},
        {"OPENOBSERVE_URL": "https://private.test/?credential=secret"},
        {"OPENOBSERVE_USER": "user:password"},
    ):
        with pytest.raises(CheckFailure):
            Settings.load({**env, **changed}, COMMIT, True)
    with pytest.raises(CheckFailure):
        Settings.load(env, COMMIT, False)
    with pytest.raises(CheckFailure):
        Settings.load(env, "main", True)


def test_cli_configuration_failure_exits_cleanly_without_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv("GATEWAY7_ENVIRONMENT", "production")
    assert main(["--confirm-staging", "--commit", COMMIT]) == 1
    output = capsys.readouterr()
    assert output.out.startswith("FAIL QR-05 QRT-01:")
    assert output.err == ""


def test_runner_query_matches_the_plan_owned_query():
    root = Path(__file__).resolve().parents[1]
    plan = (root / "docs" / "observability.md").read_text()
    recorded = re.search(r"^- \*\*Query:\*\* `(.+)`$", plan.split("### SLI-01", 1)[1], re.M)
    assert recorded.group(1) == SLI_QUERY


def test_success_warmups_are_rejected_before_contacting_any_target(monkeypatch, capsys):
    assert main(["--confirm-staging", "--commit", COMMIT, "--successes", "1"]) == 1
    assert "--successes must be zero" in capsys.readouterr().out

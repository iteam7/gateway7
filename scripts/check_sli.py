"""QR-05 QRT-01: fail one staging chat request and read its log point and SLI-01 from OpenObserve.

The script sends successful chat requests and one chat request for a model the client may not
use, then queries the staging organization for that request's log point and for the SLI-01
five-minute P95 series. It prints the evidence without any address or credential.

Variables: STAGING_URL, GATEWAY7_CLIENT_TOKEN, OPENOBSERVE_URL, OPENOBSERVE_USER and
OPENOBSERVE_TOKEN (a query credential for the organization).
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# The SLI-01 query and the per-request log query, as recorded in docs/observability.md#sli-01.
SLI_QUERY = (
    "histogram_quantile(0.95, sum by (le, route, outcome) "
    '(sum_over_time(gateway7_request_duration_ms_bucket{route=~"chat|openai_chat"}[5m])))'
)
LOG_QUERY = (
    "SELECT request_id, route, outcome, status, error_code, duration_ms "
    "FROM \"{stream}\" WHERE request_id = '{request_id}'"
)
FORBIDDEN_MODEL = "gateway7-qr05-forbidden-model"
LOG_LIMIT_SECONDS = 5.0
SLI_LIMIT_SECONDS = 60.0
REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def call(
    method: str, url: str, headers: dict[str, str], body: Any = None, timeout: float = 30
) -> tuple[int, dict[str, str], Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data, {**headers, "Content-Type": "application/json"},
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, response_headers, raw = response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        status, response_headers, raw = error.code, error.headers, error.read()
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        payload = None
    return status, {key.lower(): value for key, value in response_headers.items()}, payload


def chat(gateway: str, token: str, model: str, run: str) -> tuple[int, str, Any]:
    status, headers, payload = call(
        "POST",
        gateway + "/v1/chat/completions",
        {"Authorization": "Bearer " + token},
        {
            "model": model,
            "max_tokens": 16,
            "messages": [{"role": "user", "content": f"Reply with OK. Check {run}."}],
        },
    )
    return status, headers.get("x-request-id", ""), payload


def find_log_point(
    observe: str, org: str, auth: dict[str, str], stream: str, request_id: str, window_start: float
) -> dict[str, Any] | None:
    now = time.time()
    status, _, payload = call(
        "POST",
        f"{observe}/api/{org}/_search",
        auth,
        {
            "query": {
                "sql": LOG_QUERY.format(stream=stream, request_id=request_id),
                "start_time": int((window_start - 60) * 1_000_000),
                "end_time": int((now + 60) * 1_000_000),
            }
        },
        timeout=5,
    )
    if status != 200 or not isinstance(payload, dict) or not payload.get("hits"):
        return None
    hit = payload["hits"][0]
    return {key: hit.get(key) for key in ("request_id", "route", "outcome", "status",
                                          "error_code", "duration_ms")}


def read_failure_series(observe: str, org: str, auth: dict[str, str]) -> tuple[str, float] | None:
    url = f"{observe}/api/{org}/prometheus/api/v1/query?" + urllib.parse.urlencode(
        {"query": SLI_QUERY, "time": f"{time.time():.3f}"}
    )
    status, _, payload = call("GET", url, auth, timeout=10)
    if status != 200 or not isinstance(payload, dict):
        return None
    for series in payload.get("data", {}).get("result", []):
        labels = series.get("metric", {})
        if labels.get("route") == "openai_chat" and labels.get("outcome") == "client_error":
            value = float(series["value"][1])
            if math.isfinite(value):
                return json.dumps(labels, sort_keys=True), value
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", default=os.environ.get("STAGING_URL", ""),
                        help="Staging gateway URL; defaults to $STAGING_URL")
    parser.add_argument("--observe", default=os.environ.get("OPENOBSERVE_URL", ""),
                        help="OpenObserve URL; defaults to $OPENOBSERVE_URL")
    parser.add_argument("--org", default="staging", help="OpenObserve organization")
    parser.add_argument("--stream", default="gateway7_requests", help="Log stream name")
    parser.add_argument("--token-env", default="GATEWAY7_CLIENT_TOKEN",
                        help="Variable holding a staging client token")
    parser.add_argument("--successes", type=int, default=2,
                        help="Successful chat requests to send before the failure")
    parser.add_argument("--commit", default="", help="The commit deployed to staging, for the record")
    arguments = parser.parse_args(argv)
    token = os.environ.get(arguments.token_env, "")
    user = os.environ.get("OPENOBSERVE_USER", "")
    secret = os.environ.get("OPENOBSERVE_TOKEN", "")
    if not arguments.gateway or not arguments.observe:
        parser.error("set STAGING_URL and OPENOBSERVE_URL, or pass --gateway and --observe")
    if not token or not user or not secret:
        parser.error(f"set {arguments.token_env}, OPENOBSERVE_USER and OPENOBSERVE_TOKEN")
    gateway = arguments.gateway.rstrip("/")
    observe = arguments.observe.rstrip("/")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()}
    run = os.urandom(6).hex()
    print(f"environment: {arguments.org}")
    print(f"commit: {arguments.commit or 'not given'}")

    status, _, payload = call("GET", gateway + "/v1/models", {"Authorization": "Bearer " + token})
    models = [item.get("id") for item in (payload or {}).get("data", []) if isinstance(item, dict)]
    if status != 200 or not models:
        print(f"FAIL QR-05 QRT-01: /v1/models returned HTTP {status} without an allowed model")
        return 1
    started = time.time()
    for _ in range(arguments.successes):
        status, request_id, _ = chat(gateway, token, models[0], run)
        print(f"core task: /v1/chat/completions -> HTTP {status} request_id={request_id}")
        if status != 200:
            print("FAIL QR-05 QRT-01: the core task did not succeed before the failure")
            return 1

    status, request_id, payload = chat(gateway, token, FORBIDDEN_MODEL, run)
    failed_at = time.monotonic()
    code = ((payload or {}).get("error") or {}).get("code")
    print(f"failure: /v1/chat/completions -> HTTP {status} error={code} request_id={request_id}")
    if status != 403 or code != "model_forbidden" or not REQUEST_ID.fullmatch(request_id):
        print("FAIL QR-05 QRT-01: the failing request did not return model_forbidden")
        return 1

    point = find_log_point(observe, arguments.org, auth, arguments.stream, request_id, started)
    while point is None and time.monotonic() - failed_at < LOG_LIMIT_SECONDS:
        time.sleep(0.5)
        point = find_log_point(observe, arguments.org, auth, arguments.stream, request_id, started)
    log_seconds = time.monotonic() - failed_at
    if point is None:
        print(f"log point: not found within {LOG_LIMIT_SECONDS:.0f} s")
    else:
        print(f"log point after {log_seconds:.2f} s: {json.dumps(point, sort_keys=True)}")
    log_ok = (
        point is not None
        and log_seconds <= LOG_LIMIT_SECONDS
        and point["request_id"] == request_id
        and point["route"] == "openai_chat"
        and point["outcome"] == "client_error"
        and point["error_code"] == "model_forbidden"
    )

    series = read_failure_series(observe, arguments.org, auth)
    while series is None and time.monotonic() - failed_at < SLI_LIMIT_SECONDS:
        time.sleep(5)
        series = read_failure_series(observe, arguments.org, auth)
    sli_seconds = time.monotonic() - failed_at
    print(f"SLI-01 query: {SLI_QUERY}")
    if series is None:
        print(f"SLI-01 failure series: no numeric P95 within {SLI_LIMIT_SECONDS:.0f} s")
    else:
        print(f"SLI-01 failure series after {sli_seconds:.2f} s: {series[0]} p95_ms={series[1]:.3f}")
    sli_ok = series is not None and sli_seconds <= SLI_LIMIT_SECONDS

    if log_ok and sli_ok:
        print("PASS QR-05 QRT-01")
        return 0
    print("FAIL QR-05 QRT-01")
    return 1


if __name__ == "__main__":
    sys.exit(main())

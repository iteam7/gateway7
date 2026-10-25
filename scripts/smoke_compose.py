"""Exercise the running no-key Compose stack, including monitoring provisioning."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

GATEWAY = "http://127.0.0.1:8000"
PROMETHEUS = "http://127.0.0.1:9090"
GRAFANA = "http://127.0.0.1:3000"


def request(url: str, payload: object | None = None) -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read(2_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(2_000_000)


def get_json(url: str) -> dict[str, Any]:
    status, body = request(url)
    assert status == 200, f"Endpoint returned HTTP {status}"
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


def wait_for(description: str, check: Callable[[], None], timeout: float = 90) -> None:
    print(f"Checking {description}...", flush=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            check()
            return
        except (AssertionError, OSError, ValueError, KeyError):
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out checking {description}") from None
            time.sleep(1)


def metrics() -> str:
    status, body = request(GATEWAY + "/metrics")
    assert status == 200
    return body.decode()


def counter_total(body: str, name: str) -> float:
    values = re.findall(rf"^{re.escape(name)}(?:\{{[^\n]*\}})? ([0-9.eE+\-]+)$", body, re.M)
    return sum(float(value) for value in values)


def query(url: str, expression: str) -> list[dict[str, Any]]:
    data = get_json(url + "/api/v1/query?" + urllib.parse.urlencode({"query": expression}))
    assert data["status"] == "success"
    result = data["data"]["result"]
    assert isinstance(result, list)
    return result


def assert_scraping() -> None:
    result = query(PROMETHEUS, 'up{job="gateway7"}')
    assert result and all(float(item["value"][1]) == 1 for item in result)
    result = query(PROMETHEUS, 'gateway7_http_requests_total{route="chat",status="200"}')
    assert result and sum(float(item["value"][1]) for item in result) >= 1


def assert_dashboard() -> None:
    dashboard = get_json(GRAFANA + "/api/dashboards/uid/gateway7-overview")["dashboard"]
    assert dashboard["title"] == "Gateway7 overview" and len(dashboard["panels"]) >= 8
    expressions = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    assert any("gateway7_middleware_duration_seconds_bucket" in expr for expr in expressions)
    assert any("gateway7_provider_usage_unknown_total" in expr for expr in expressions)
    source = get_json(GRAFANA + "/api/datasources/uid/gateway7-prometheus")
    assert source["type"] == "prometheus" and source["url"] == "http://prometheus:9090"
    result = query(GRAFANA + "/api/datasources/proxy/uid/gateway7-prometheus", 'up{job="gateway7"}')
    assert result and float(result[0]["value"][1]) == 1


def check_gateway() -> None:
    wait_for("gateway readiness", lambda: get_json(GATEWAY + "/ready"))
    before = counter_total(metrics(), "gateway7_provider_calls_total")
    email, phone = "synthetic@example.com", "+7 999 123-45-67"
    status, body = request(
        GATEWAY + "/chat",
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"Synthetic contact {email} {phone}. Reply pong.",
                }
            ]
        },
    )
    assert status == 200, f"Chat failed with HTTP {status}"
    answer = json.loads(body)
    assert isinstance(answer["text"], str) and answer["text"]
    assert email not in answer["text"] and phone not in answer["text"]
    assert "[EMAIL]" in answer["text"] and "[PHONE]" in answer["text"]
    assert type(answer["usage"]["input_tokens"]) is int
    assert type(answer["usage"]["output_tokens"]) is int
    after = counter_total(metrics(), "gateway7_provider_calls_total")
    assert after == before + 1, "Successful chat must call the provider exactly once"

    status, body = request(
        GATEWAY + "/chat",
        {
            "messages": [
                {
                    "role": "user",
                    "content": "SECRET-TEST",
                }
            ]
        },
    )
    assert status == 200
    assert "SECRET-TEST" not in json.loads(body)["text"]
    assert "[removed]" in json.loads(body)["text"]
    after = counter_total(metrics(), "gateway7_provider_calls_total")
    assert after == before + 2, "Response redaction must retain the one provider attempt"

    status, body = request(
        GATEWAY + "/chat",
        {
            "messages": [
                {
                    "role": "user",
                    "content": "BLOCK-ME-TEST",
                }
            ]
        },
    )
    assert status == 403 and json.loads(body)["error"]["code"] == "policy_denied"
    observed = metrics()
    assert counter_total(observed, "gateway7_provider_calls_total") == after
    for name in (
        "gateway7_http_request_duration_seconds_bucket",
        "gateway7_provider_duration_seconds_bucket",
        "gateway7_provider_tokens_total",
        "gateway7_middleware_steps_total",
        "gateway7_middleware_duration_seconds_bucket",
    ):
        assert name in observed, f"Missing metric family: {name}"
    assert counter_total(observed, "gateway7_provider_tokens_total") > 0
    for sensitive in (email, phone, "BLOCK-ME-TEST", "SECRET-TEST", answer["request_id"]):
        assert sensitive not in observed, "Request data leaked into metrics"
    print("Chat, policy denial, usage, and privacy-safe metrics passed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway-only", action="store_true", help="Skip Prometheus/Grafana for wheel smoke"
    )
    args = parser.parse_args()
    check_gateway()
    if args.gateway_only:
        return
    wait_for("Prometheus scrape and chat series", assert_scraping)
    wait_for("Grafana dashboard, datasource, and proxied query", assert_dashboard)
    print("Compose smoke passed", flush=True)


if __name__ == "__main__":
    main()

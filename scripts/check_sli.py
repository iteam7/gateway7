"""QR-05 QRT-01: query a staging failure's log and five-minute P95 in OpenObserve.

Run with ``uv run --locked python scripts/check_sli.py --help``.
Addresses and credentials come only from environment variables and are never printed.
The staging confirmation and commit are operator assertions, not remote attestation.
"""

from __future__ import annotations

import argparse
import base64
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import re
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

SLI_QUERY = (
    "histogram_quantile(0.95, sum by (le, route, outcome) "
    '(sum_over_time(gateway7_request_duration_ms_bucket{route=~"chat|openai_chat"}[5m])))'
)
COUNT_QUERY = (
    "sum(sum_over_time(gateway7_request_duration_ms_count"
    '{route="openai_chat",outcome="client_error"}[5m]))'
)
MAX_RESPONSE_BYTES = 65_536
LOG_LIMIT_SECONDS = 5.0
SLI_LIMIT_SECONDS = 60.0
POLL_SECONDS = 0.25


FORBIDDEN_MODEL = "gateway7-qr05-forbidden-model"


class CheckFailure(Exception):
    """A fixed, safe diagnostic; never wrap a backend exception or response body."""


@dataclass(frozen=True)
class Settings:
    gateway: str
    backend: str
    authorization: str
    commit: str
    gateway_token: str

    @classmethod
    def load(
        cls,
        environ: Mapping[str, str],
        commit: str,
        confirmed: bool,
        *,
        gateway: str | None = None,
        observe: str | None = None,
        org: str = "staging",
        stream: str = "gateway7_requests",
        token_env: str = "GATEWAY7_CLIENT_TOKEN",
    ) -> Settings:
        if not confirmed or environ.get("GATEWAY7_ENVIRONMENT") != "staging":
            raise CheckFailure("Confirm the staging target and set GATEWAY7_ENVIRONMENT=staging")
        if org != "staging" or environ.get("OPENOBSERVE_ORG", "staging") != "staging":
            raise CheckFailure("OPENOBSERVE_ORG must be staging")
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise CheckFailure("Commit must be the full lowercase SHA of the staging deployment")
        if stream != "gateway7_requests":
            raise CheckFailure("The staging SLI log stream must be gateway7_requests")
        user, secret = environ.get("OPENOBSERVE_USER", ""), environ.get("OPENOBSERVE_TOKEN", "")
        if not user or not secret or ":" in user:
            raise CheckFailure("Set OPENOBSERVE_USER and OPENOBSERVE_TOKEN to a query credential")
        token = environ.get(token_env, "")
        if not (
            16 <= len(token) <= 512 and token.isascii() and all(33 <= ord(c) <= 126 for c in token)
        ):
            raise CheckFailure("Set the staging gateway client token")
        authorization = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()
        return cls(
            _base_url(gateway if gateway is not None else environ.get("STAGING_URL", "")),
            _base_url(observe if observe is not None else environ.get("OPENOBSERVE_URL", "")),
            authorization,
            commit,
            token,
        )


def _base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and not any(character.isspace() for character in value)
            and parsed.port != 0
        )
    except ValueError:
        valid = False
    if not valid:
        raise CheckFailure("Set STAGING_URL and OPENOBSERVE_URL to base HTTP(S) addresses")
    return value.rstrip("/")


class Probe:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.client = client
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.sleep = sleep
        self.last_response_completed_at = self.monotonic()

    async def json_request(
        self,
        method: str,
        url: str,
        *,
        deadline: float,
        allow_missing: bool = False,
        expected_status: int | None = None,
        **kwargs: Any,
    ) -> tuple[int, httpx.Headers, Any]:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise CheckFailure("Query deadline exceeded")
        try:
            async with asyncio.timeout(remaining):
                async with self.client.stream(
                    method, url, timeout=min(remaining, 2.0), **kwargs
                ) as response:
                    if allow_missing and response.status_code == 404:
                        return response.status_code, response.headers, None
                    if not (
                        response.status_code == expected_status
                        if expected_status is not None
                        else 200 <= response.status_code < 300
                    ):
                        raise CheckFailure(
                            "HTTP query failed; check target, credential and backend"
                        )
                    content = bytearray()
                    body_completed_at = self.monotonic()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise CheckFailure("Query response exceeded the size limit")
                        content.extend(chunk)
                        # httpx may close the stream while its iterator finishes.
                        # Keep the last byte's timestamp, before close or parsing.
                        body_completed_at = self.monotonic()
                    self.last_response_completed_at = body_completed_at
                    payload = json.loads(content)
            if self.monotonic() > deadline:
                raise CheckFailure("Query deadline exceeded")
            return response.status_code, response.headers, payload
        except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError):
            raise CheckFailure("Query failed or exceeded its deadline") from None

    async def metric(self, settings: Settings, query: str, deadline: float) -> Any:
        _, _, payload = await self.json_request(
            "GET",
            settings.backend + "/api/staging/prometheus/api/v1/query",
            deadline=deadline,
            allow_missing=True,
            headers={"Authorization": settings.authorization},
            params={"query": query, "time": self.wall_time()},
        )
        if payload is None:
            return []
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise CheckFailure("Metrics API did not return a successful query")
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("resultType") != "vector":
            raise CheckFailure("Metrics API did not return an instant vector")
        result = data.get("result")
        if not isinstance(result, list):
            raise CheckFailure("Metrics API returned an invalid result")
        return result

    async def run(self, settings: Settings) -> dict[str, Any]:
        _, _, readiness = await self.json_request(
            "GET", settings.gateway + "/ready", deadline=self.monotonic() + 5
        )
        if not isinstance(readiness, dict) or readiness.get("status") != "ready":
            raise CheckFailure("The selected staging gateway is not ready")
        # Authentication and the fixed allowlist are checked without invoking a provider.
        await self.json_request(
            "GET",
            settings.gateway + "/v1/models",
            expected_status=401,
            deadline=self.monotonic() + 5,
        )
        _, _, models = await self.json_request(
            "GET",
            settings.gateway + "/v1/models",
            deadline=self.monotonic() + 5,
            headers={"Authorization": "Bearer " + settings.gateway_token},
        )
        entries = models.get("data") if isinstance(models, dict) else None
        if (
            not isinstance(entries, list)
            or not entries
            or not all(
                isinstance(item, dict) and isinstance(item.get("id"), str) for item in entries
            )
        ):
            raise CheckFailure("The staging client did not return a model allowlist")
        if FORBIDDEN_MODEL in [item["id"] for item in entries]:
            raise CheckFailure("The check model is allowed; use a restricted staging client")
        baseline = _count(await self.metric(settings, COUNT_QUERY, self.monotonic() + 5))
        request_wall_time = self.wall_time()
        # The selected client cannot use this model. The gateway rejects it before
        # the pipeline or provider: no successful or paid requests are generated.
        _, headers, body = await self.json_request(
            "POST",
            settings.gateway + "/v1/chat/completions",
            expected_status=403,
            deadline=self.monotonic() + 5,
            headers={"Authorization": "Bearer " + settings.gateway_token},
            json={
                "model": FORBIDDEN_MODEL,
                "messages": [{"role": "user", "content": "analysability check"}],
            },
        )
        response_at = self.last_response_completed_at
        request_id = headers.get("X-Request-ID", "")
        if (
            re.fullmatch(r"[0-9a-f]{32}", request_id) is None
            or not isinstance(body, dict)
            or body.get("request_id") != request_id
            or not isinstance(body.get("error"), dict)
            or body["error"].get("code") != "model_forbidden"
        ):
            raise CheckFailure("The failure did not carry the expected request identifier")

        log_deadline = response_at + LOG_LIMIT_SECONDS
        while True:
            _, _, payload = await self.json_request(
                "POST",
                settings.backend + "/api/staging/_search",
                deadline=log_deadline,
                allow_missing=True,
                headers={"Authorization": settings.authorization},
                json={
                    "query": {
                        "sql": (
                            "SELECT request_id, route, outcome, status, error_code, duration_ms "
                            'FROM "gateway7_requests" '
                            f"WHERE request_id = '{request_id}'"
                        ),
                        "start_time": int((request_wall_time - 60) * 1_000_000),
                        "end_time": int(self.wall_time() * 1_000_000),
                        "from": 0,
                        "size": 10,
                    }
                },
            )
            if _matching_log(payload, request_id):
                log_delay = self.monotonic() - response_at
                break
            await self.pause(log_deadline)

        metric_deadline = response_at + SLI_LIMIT_SECONDS
        while True:
            count = _count(await self.metric(settings, COUNT_QUERY, metric_deadline))
            if count >= baseline + 1:
                result = await self.metric(settings, SLI_QUERY, metric_deadline)
                p95 = _p95(result)
                if p95 is not None:
                    metric_delay = self.monotonic() - response_at
                    break
            await self.pause(metric_deadline)
        return {
            "result": "PASS",
            "test": "QR-05 QRT-01",
            "environment": "staging",
            "target_confirmation": "operator assertion",
            "commit": settings.commit,
            "commit_source": "operator assertion",
            "checked_at": datetime.fromtimestamp(self.wall_time(), timezone.utc).isoformat(),
            "request_id": request_id,
            "route": "openai_chat",
            "outcome": "client_error",
            "status": 403,
            "error_code": "model_forbidden",
            "log_queryable_seconds": round(log_delay, 3),
            "p95_queryable_seconds": round(metric_delay, 3),
            "p95_duration_ms": p95,
            "histogram_count_increase": count - baseline,
            "p95_window_seconds": 300,
        }

    async def pause(self, deadline: float) -> None:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise CheckFailure("Signal was not queryable within the required window")
        await self.sleep(min(POLL_SECONDS, remaining))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _count(result: Any) -> float:
    if not result:
        return 0.0
    if len(result) != 1 or not isinstance(result[0], dict):
        raise CheckFailure("Histogram count query returned an invalid result")
    value = result[0].get("value")
    count = _number(value[1]) if isinstance(value, list) and len(value) == 2 else None
    if count is None:
        raise CheckFailure("Histogram count query returned an invalid number")
    return count


def _matching_log(payload: Any, request_id: str) -> bool:
    if payload is None:
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
        raise CheckFailure("Log query returned an invalid result")
    for hit in payload["hits"]:
        if (
            isinstance(hit, dict)
            and hit.get("request_id") == request_id
            and hit.get("route") == "openai_chat"
            and hit.get("outcome") == "client_error"
            and type(hit.get("status")) is int
            and hit["status"] == 403
            and hit.get("error_code") == "model_forbidden"
            and _number(hit.get("duration_ms")) is not None
        ):
            return True
    return False


def _p95(result: Any) -> float | None:
    for row in result:
        if not isinstance(row, dict):
            continue
        labels = row.get("metric")
        value = row.get("value")
        if (
            isinstance(labels, dict)
            and labels.get("route") == "openai_chat"
            and labels.get("outcome") == "client_error"
            and isinstance(value, list)
            and len(value) == 2
        ):
            number = _number(value[1])
            if number is not None:
                return number
    return None


async def check(settings: Settings) -> dict[str, Any]:
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        return await Probe(client).run(settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-staging", action="store_true", help="Assert that STAGING_URL is staging"
    )
    parser.add_argument(
        "--gateway", default=os.environ.get("STAGING_URL"), help="Staging gateway base URL"
    )
    parser.add_argument(
        "--observe", default=os.environ.get("OPENOBSERVE_URL"), help="OpenObserve base URL"
    )
    parser.add_argument("--org", default="staging", help="Only staging is accepted")
    parser.add_argument(
        "--stream", default="gateway7_requests", help="Only gateway7_requests is accepted"
    )
    parser.add_argument(
        "--token-env",
        default="GATEWAY7_CLIENT_TOKEN",
        help="Variable holding the staging client token",
    )
    parser.add_argument(
        "--successes", type=int, default=0, help="Compatibility option; only zero is accepted"
    )
    parser.add_argument("--commit", required=True, help="Full SHA verified on the staging VM")
    args = parser.parse_args(argv)
    try:
        if args.successes != 0:
            raise CheckFailure(
                "This check sends no successful provider requests; --successes must be zero"
            )
        settings = Settings.load(
            os.environ,
            args.commit,
            args.confirm_staging,
            gateway=args.gateway,
            observe=args.observe,
            org=args.org,
            stream=args.stream,
            token_env=args.token_env,
        )
        result = asyncio.run(check(settings))
    except CheckFailure as error:
        print(f"FAIL QR-05 QRT-01: {error}")
        print("FAIL QR-05 QRT-01")
        return 1
    print(json.dumps(result, sort_keys=True))
    print("PASS QR-05 QRT-01")
    return 0


if __name__ == "__main__":
    sys.exit(main())

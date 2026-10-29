"""Bounded, explicit live check of an authenticated Gateway7 HTTP deployment.

Invoking this check can consume paid tokens. GET probes run first, followed by
at most one chat attempt; no provider identity is inferred from the response.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

_BODY_LIMIT = 1_048_576
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_MESSAGE = "Reply briefly: Gateway7 is working."


class _CheckFailed(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _options(url: str, token_env: str, model: str | None) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise ValueError
    except ValueError:
        raise _CheckFailed("invalid_url") from None
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", token_env) is None:
        raise _CheckFailed("invalid_token_env")
    token = os.environ.get(token_env)
    if token is None:
        raise _CheckFailed("missing_token")
    if (
        not 16 <= len(token) <= 512
        or not token.isascii()
        or any(not 33 <= ord(character) <= 126 for character in token)
    ):
        raise _CheckFailed("invalid_token")
    if model is not None and _MODEL.fullmatch(model) is None:
        raise _CheckFailed("invalid_model")
    return token


def _models(data: dict[str, Any], model: str | None) -> None:
    entries = data.get("data")
    if data.get("object") != "list" or not isinstance(entries, list) or not entries:
        raise _CheckFailed("invalid_response")
    identifiers = []
    for item in entries:
        identifier = item.get("id") if isinstance(item, dict) else None
        if not isinstance(identifier, str) or _MODEL.fullmatch(identifier) is None:
            raise _CheckFailed("invalid_response")
        identifiers.append(identifier)
    if model is not None and model not in identifiers:
        raise _CheckFailed("model_not_allowed")


def _answer(data: dict[str, Any], request_id: str | None) -> dict[str, int] | None:
    text = data.get("text")
    if (
        not isinstance(text, str)
        or not text.strip()
        or request_id is None
        or data.get("request_id") != request_id
        or "usage" not in data
    ):
        raise _CheckFailed("invalid_response")
    usage = data["usage"]
    if usage is None:
        return None
    if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}:
        raise _CheckFailed("invalid_response")
    if any(type(value) is not int or not 0 <= value <= 2**63 - 1 for value in usage.values()):
        raise _CheckFailed("invalid_response")
    return {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]}


async def run_smoke(
    url: str,
    *,
    token_env: str = "GATEWAY7_TOKEN",
    model: str | None = None,
    max_tokens: int = 256,
    timeout: float = 90,
) -> tuple[int, dict[str, Any]]:
    """Return only allowlisted diagnostics; never expose response text or secrets."""
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": 1,
        "passed": False,
        "checks": checks,
        "chat_attempts": 0,
    }
    current: dict[str, Any] = {"check": "configuration", "passed": False}

    async def request(
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
        expected: int = 200,
    ) -> dict[str, Any]:
        headers = {} if token is None else {"authorization": "Bearer " + token}
        async with client.stream(
            method, url.rstrip("/") + path, headers=headers, json=payload
        ) as response:
            current["http_status"] = response.status_code
            identifier = response.headers.get("x-request-id", "")
            if _REQUEST_ID.fullmatch(identifier) is not None:
                current["request_id"] = identifier
            if response.status_code != expected:
                raise _CheckFailed("unexpected_status")
            # An expected auth denial needs no arbitrary error body.
            if expected == 401:
                return {}
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > _BODY_LIMIT:
                    raise _CheckFailed("response_too_large")
                body.extend(chunk)
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                raise _CheckFailed("invalid_response") from None
            if not isinstance(data, dict):
                raise _CheckFailed("invalid_response")
            return data

    try:
        token = _options(url, token_env, model)
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096 or not 1 <= timeout <= 300:
            raise _CheckFailed("invalid_limits")
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=timeout
            ) as client:
                for check, path, status in (
                    ("health", "/health", "ok"),
                    ("readiness", "/ready", "ready"),
                ):
                    current = {"check": check, "passed": False}
                    data = await request(client, "GET", path)
                    if data.get("status") != status:
                        raise _CheckFailed("invalid_response")
                    current["passed"] = True
                    checks.append(current)
                current = {"check": "anonymous_models", "passed": False}
                await request(client, "GET", "/v1/models", expected=401)
                current["passed"] = True
                checks.append(current)
                current = {"check": "models", "passed": False}
                data = await request(client, "GET", "/v1/models", token=token)
                _models(data, model)
                current["passed"] = True
                checks.append(current)
                current = {"check": "chat", "passed": False}
                payload: dict[str, Any] = {
                    "messages": [{"role": "user", "content": _MESSAGE}],
                    "max_tokens": max_tokens,
                }
                if model is not None:
                    payload["model"] = model
                report["chat_attempts"] = 1
                data = await request(client, "POST", "/chat", token=token, payload=payload)
                current["usage"] = _answer(data, current.get("request_id"))
        current["passed"] = True
        checks.append(current)
        report["passed"] = True
    except _CheckFailed as error:
        current["error"] = error.reason
        checks.append(current)
    except (TimeoutError, httpx.TimeoutException):
        current["error"] = "timeout"
        checks.append(current)
    except httpx.HTTPError:
        current["error"] = "network_error"
        checks.append(current)
    except Exception:
        current["error"] = "check_failed"
        checks.append(current)
    report["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    return (0 if report["passed"] else 1), report

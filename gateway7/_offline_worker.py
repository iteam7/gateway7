"""Internal worker: import and run trusted plugins with Python networking disabled."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import sys
from typing import Any

from gateway7.config import GatewayConfig, load_config
from gateway7.errors import GatewayError, ProviderError, StartupError
from gateway7.loader import load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest, ChatResponse
from gateway7.offline import Case, MAX_REPORT_BYTES, _failure, load_fixtures
from gateway7.pipeline import Pipeline


_BLOCKED_EVENTS = {
    "socket.connect",
    "socket.connect_ex",
    "socket.bind",
    "socket.sendto",
    "socket.sendmsg",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyaddr",
    "socket.getnameinfo",
    "subprocess.Popen",
    "os.system",
    "os.posix_spawn",
    "os.fork",
    "os.forkpty",
    "os.exec",
}


def _network_guard(event: str, _arguments: tuple[Any, ...]) -> None:
    if event in _BLOCKED_EVENTS:
        raise PermissionError("Network and subprocess access are disabled in offline fixtures")


class FixtureProvider:
    def __init__(self, case: Case) -> None:
        self.case = case
        self.calls = 0
        self.request: ChatRequest | None = None

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.request = ChatRequest.model_validate(request.model_dump(mode="python"), strict=True)
        if self.case.provider_error:
            raise ProviderError()
        return self.case.provider_response.model_copy(deep=True)


def _preview(value: Any) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) <= 8192:
        return value
    return {"truncated": True, "preview": encoded[:2048]}


def _check(field: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "field": field,
        "passed": expected == actual,
        "expected": _preview(expected),
        "actual": _preview(actual),
    }


async def _case(config: GatewayConfig, case: Case) -> dict[str, Any]:
    plugins = load_plugins(config)
    provider = FixtureProvider(case)
    answer = None
    error = None
    await start_plugins(plugins, config.limits.hook_timeout_seconds)
    try:
        try:
            answer = await Pipeline(plugins, provider, config.limits).run(
                case.request.model_copy(deep=True), "offline-fixture"
            )
        except GatewayError as caught:
            error = caught.code
    finally:
        await stop_plugins(plugins, config.limits.hook_timeout_seconds)
    checks = [_check("provider_calls", case.expected.provider_calls, provider.calls)]
    if case.expected.request is not None:
        checks.append(
            _check(
                "request",
                case.expected.request.model_dump(mode="json"),
                None if provider.request is None else provider.request.model_dump(mode="json"),
            )
        )
    checks.extend(
        [
            _check(
                "response",
                None
                if case.expected.response is None
                else case.expected.response.model_dump(mode="json"),
                None if answer is None else answer.model_dump(mode="json"),
            ),
            _check("error", case.expected.error, error),
        ]
    )
    return {"name": case.name, "passed": all(item["passed"] for item in checks), "checks": checks}


async def _run(config_path: str, fixtures_path: str) -> dict[str, Any]:
    config = load_config(config_path)
    suite = load_fixtures(fixtures_path)
    # Explicit authoring convention: modules beside the selected config are
    # importable only in this isolated worker. Serving uses installed packages.
    sys.path.insert(0, str(Path(config_path).parent))
    results = [await _case(config, case) for case in suite.cases]
    failed = sum(not case["passed"] for case in results)
    return {
        "schema_version": 1,
        "passed": failed == 0,
        "total": len(results),
        "failed": failed,
        "cases": results,
    }


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    # Initialize the event loop's internal wakeup socket before installing the
    # guard, including Windows' implementation. No plugin has been imported yet.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logging.disable(logging.CRITICAL)
    sys.addaudithook(_network_guard)
    try:
        try:
            report = loop.run_until_complete(_run(sys.argv[1], sys.argv[2]))
            code = 0 if report["passed"] else 1
        except StartupError as error:
            report = _failure(str(error))
            code = 2
        except Exception:
            report = _failure("Offline fixture execution failed")
            code = 2
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_REPORT_BYTES:
            encoded = json.dumps(_failure("Offline worker report exceeded its size limit")).encode()
            code = 2
        Path(sys.argv[3]).write_bytes(encoded)
        return code
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())

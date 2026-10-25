"""Bounded synthetic fixtures and an isolated, credential-free plugin test runner."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gateway7.errors import StartupError
from gateway7.models import ChatRequest, ChatResponse

MAX_FILE_BYTES = 1_048_576
MAX_REPORT_BYTES = 4_194_304


class StrictFixture(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Expected(StrictFixture):
    provider_calls: Literal[0, 1]
    request: ChatRequest | None = None
    response: ChatResponse | None = None
    error: (
        Literal["policy_denied", "plugin_error", "timeout", "provider_error", "invalid_request"]
        | None
    ) = None

    @field_validator("provider_calls", mode="before")
    @classmethod
    def integer_calls(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Call count must be an integer")
        return value

    @model_validator(mode="after")
    def expected_outcome(self) -> Expected:
        if (self.response is None) == (self.error is None):
            raise ValueError("Specify one expected response or error")
        if self.provider_calls == 0 and (self.request is not None or self.response is not None):
            raise ValueError("No provider call cannot have a request or successful response")
        return self


class Case(StrictFixture):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_. -]{0,79}$")
    request: ChatRequest
    provider_response: ChatResponse = Field(
        default_factory=lambda: ChatResponse(text="Fixture answer")
    )
    provider_error: bool = False
    expected: Expected


class FixtureSuite(StrictFixture):
    schema_version: Literal[1]
    cases: list[Case] = Field(min_length=1, max_length=64)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value

    @field_validator("cases")
    @classmethod
    def unique_names(cls, value: list[Case]) -> list[Case]:
        if len({case.name for case in value}) != len(value):
            raise ValueError("Case names must be unique")
        return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate fixture key")
        result[name] = value
    return result


def load_fixtures(path: str | Path) -> FixtureSuite:
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError
        data = json.loads(raw, object_pairs_hook=_unique_object)
        return FixtureSuite.model_validate(data, strict=True)
    except (OSError, ValueError, RecursionError):
        raise StartupError(
            "Invalid fixture file: use schema version 1, unique cases and bounded JSON"
        ) from None


def _failure(message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": False,
        "total": 0,
        "failed": 0,
        "cases": [],
        "error": message,
    }


def _terminate_worker(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


@dataclass
class _Cancellation:
    requested: bool = False


@contextmanager
def _cancellation_signals() -> Iterator[_Cancellation]:
    cancellation = _Cancellation()
    previous = {}

    def interrupt(_signal: int, _frame: object) -> None:
        # Never raise during Popen creation: it may already own a child before
        # returning its process handle. The bounded wait checks this flag next.
        cancellation.requested = True

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupt)
    try:
        yield cancellation
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def run_offline(
    config_path: str | Path, fixtures_path: str | Path, timeout: float = 30
) -> tuple[int, dict[str, Any]]:
    try:
        config = Path(config_path).resolve(strict=True)
        fixtures = Path(fixtures_path).resolve(strict=True)
        if not config.is_file() or not fixtures.is_file() or config.stat().st_size > MAX_FILE_BYTES:
            raise ValueError
        load_fixtures(fixtures)
    except StartupError as error:
        return 2, _failure(str(error))
    except (OSError, ValueError):
        return 2, _failure("Invalid config or fixture file")
    # No provider keys, client tokens, proxy settings, HOME, or PYTHONPATH are
    # inherited. -I also ignores Python startup environment and the caller cwd.
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
        if name in os.environ
    }
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    try:
        with _cancellation_signals() as cancellation:
            with tempfile.TemporaryDirectory(prefix="gateway7-offline-") as temporary:
                report_path = Path(temporary) / "report.json"
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-m",
                        "gateway7._offline_worker",
                        str(config),
                        str(fixtures),
                        str(report_path),
                    ],
                    cwd=temporary,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=os.name != "nt",
                )
                try:
                    deadline = time.monotonic() + timeout
                    while True:
                        if cancellation.requested:
                            return 2, _failure("Offline fixture execution interrupted")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 and process.poll() is None:
                            return 2, _failure("Offline worker exceeded the wall-clock limit")
                        try:
                            process.wait(timeout=min(0.1, max(remaining, 0)))
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    if cancellation.requested:
                        return 2, _failure("Offline fixture execution interrupted")
                    if process.returncode not in (0, 1, 2):
                        return 2, _failure("Offline worker failed")
                    with report_path.open("rb") as source:
                        raw = source.read(MAX_REPORT_BYTES + 1)
                    if len(raw) > MAX_REPORT_BYTES:
                        return 2, _failure("Offline worker report exceeded its size limit")
                    report = json.loads(raw)
                    if not isinstance(report, dict) or report.get("schema_version") != 1:
                        raise ValueError
                    if cancellation.requested:
                        return 2, _failure("Offline fixture execution interrupted")
                    return process.returncode, report
                except KeyboardInterrupt:
                    return 2, _failure("Offline fixture execution interrupted")
                finally:
                    if process.poll() is None:
                        _terminate_worker(process)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 2, _failure("Offline worker could not complete")


def print_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return
    if "error" in report:
        print(f"Offline test failed: {report['error']}")
        return
    for case in report["cases"]:
        print(f"{'PASS' if case['passed'] else 'FAIL'} {case['name']}")
        for check in case["checks"]:
            print(f"  {check['field']}: {'PASS' if check['passed'] else 'FAIL'}")
            print(
                "    expected: " + json.dumps(check["expected"], ensure_ascii=False, sort_keys=True)
            )
            print(
                "    actual:   " + json.dumps(check["actual"], ensure_ascii=False, sort_keys=True)
            )
    print(f"{report['total'] - report['failed']}/{report['total']} cases passed")

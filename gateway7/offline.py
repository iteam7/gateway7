"""Project-aware isolated contract suites and safe authoring reports."""

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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from gateway7.errors import StartupError
from gateway7.models import ChatRequest, ChatResponse
from gateway7.plugin_diagnostics import PluginDiagnosticError, diagnostic, issue, validation_issues
from gateway7.plugin_project import load_project
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_models import ResponsesConsent, ResponsesRequest, ResponsesResponse

MAX_FILE_BYTES = 1_048_576
MAX_REPORT_BYTES = 4_194_304
Profile = Literal["chat", "chat-tools", "chat-early", "responses", "responses-early"]


class StrictFixture(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Expected(StrictFixture):
    provider_calls: Literal[0, 1]
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    error: (
        Literal[
            "policy_denied",
            "plugin_error",
            "timeout",
            "provider_error",
            "invalid_request",
            "early_stream_unsupported",
            "responses_unsupported",
        ]
        | None
    ) = None
    deltas: list[str | dict[str, Any]] | None = None

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
            raise ValueError("No provider call cannot have a request or response")
        return self


class Case(StrictFixture):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_. -]*$")
    profile: Profile
    request: dict[str, Any]
    provider_response: dict[str, Any] | None = None
    provider_error: bool = False
    provider_deltas: list[str | dict[str, Any]] = Field(default_factory=list, max_length=128)
    consent: ResponsesConsent = Field(default_factory=ResponsesConsent)
    expected: Expected

    @property
    def native(self) -> bool:
        return self.profile.startswith("responses")

    def request_payload(
        self, value: dict[str, Any] | None = None
    ) -> ChatRequest | ResponsesRequest:
        value = self.request if value is None else value
        if self.native:
            # Shape validation grants no execution authority: negative consent
            # fixtures must be representable, and the actual case.consent is
            # still supplied unchanged to the production pipeline at execution.
            return ResponsesRequest.model_validate(
                value,
                strict=True,
                context={"consent": ResponsesConsent(allow_opaque=True, allow_hosted=True)},
            )
        return ChatRequest.model_validate(value, strict=True)

    def response_payload(
        self, value: dict[str, Any] | None = None
    ) -> ChatResponse | ResponsesResponse:
        value = self.provider_response if value is None else value
        if self.native:
            value = (
                value
                if value is not None
                else {
                    "id": "resp_fixture",
                    "created_at": 1,
                    "model": "fake",
                    "status": "completed",
                    "output": [],
                }
            )
            return ResponsesResponse.model_validate(
                value,
                strict=True,
                context={"consent": ResponsesConsent(allow_opaque=True, allow_hosted=True)},
            )
        return ChatResponse.model_validate(
            value if value is not None else {"text": "Fixture answer"}, strict=True
        )

    def deltas(self, values: list[str | dict[str, Any]]) -> list[Any]:
        if self.profile == "responses-early":
            return [ResponsesTextDelta.model_validate(value, strict=True) for value in values]
        if self.profile == "chat-early":
            if any(type(value) is not str or not value for value in values):
                raise ValueError("Chat early deltas must be nonempty strings")
            return list(values)
        if values:
            raise ValueError("Buffered fixtures cannot declare early deltas")
        return []

    @model_validator(mode="after")
    def profile_payload(self) -> Case:
        request = self.request_payload()
        response = self.response_payload()
        if self.expected.request is not None:
            self.request_payload(self.expected.request)
        if self.expected.response is not None:
            self.response_payload(self.expected.response)
        self.deltas(self.provider_deltas)
        if self.expected.deltas is not None:
            self.deltas(self.expected.deltas)
        if self.profile == "chat-tools":
            assert isinstance(request, ChatRequest) and isinstance(response, ChatResponse)
            if not request.tools and not request.requires_tools and not response.tool_calls:
                raise ValueError("Tool profile requires an actual tool payload")
        if (
            self.profile in ("chat-early", "responses-early")
            and self.expected.response is not None
            and self.expected.provider_calls == 1
        ):
            if self.expected.deltas is None:
                raise ValueError(
                    "Early fixtures must explicitly verify their emitted prefix, including an empty prefix"
                )
        return self


class FixtureSuite(StrictFixture):
    schema_version: Literal[2]
    concurrency: int = Field(default=1, ge=1, le=8)
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


def _invalid_constant(_value: str):
    raise ValueError("Nonfinite JSON numbers are not fixture values")


def _validate_json_tree(value: Any) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if count > 20000 or depth > 32:
            raise ValueError("Fixture JSON exceeds its nesting or node bound")
        if isinstance(current, str):
            current.encode("utf-8", errors="strict")
        elif isinstance(current, dict):
            pending.extend((child, depth + 1) for pair in current.items() for child in pair)
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def load_fixtures(path: str | Path) -> FixtureSuite:
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError
        data = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        _validate_json_tree(data)
        return FixtureSuite.model_validate(data, strict=True)
    except json.JSONDecodeError as error:
        raise diagnostic(
            "Invalid fixture JSON",
            "fixture_json_invalid",
            "fixtures",
            "Check JSON syntax at the reported line",
            line=error.lineno,
        ) from None
    except ValidationError as error:
        raise PluginDiagnosticError(
            "Invalid fixture file: use schema version 2, profile-specific payloads and bounded JSON",
            validation_issues(error, model=FixtureSuite, prefix="fixtures"),
        ) from None
    except (OSError, ValueError, RecursionError):
        raise diagnostic(
            "Invalid fixture file: use schema version 2, unique cases and bounded JSON",
            "fixture_invalid",
            "fixtures",
            "Use the current fixture schema and synthetic values only",
        ) from None


def _failure(message: str, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "passed": False,
        "total": 0,
        "failed": 0,
        "cases": [],
        "issues": issues
        or [
            issue(
                "authoring_failed",
                "project",
                message,
                "Check the project manifest and bounded synthetic fixtures",
            )
        ],
        "capabilities": {
            "declared_profiles": [],
            "hooks": {},
            "supports_tools": False,
            "tested_profiles": [],
        },
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
        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGBREAK"):
            signals.append(signal.SIGBREAK)
        for signum in signals:
            previous[signum] = signal.signal(signum, interrupt)
    try:
        yield cancellation
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _worker_environment() -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
        if name in os.environ
    }
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    return environment


def _run_project_worker(
    project_path: str | Path, operation: str, timeout: float
) -> tuple[int, dict[str, Any]]:
    if type(timeout) not in (int, float) or not 1 <= timeout <= 300:
        return 2, _failure("Authoring timeout must be between 1 and 300 seconds")
    project = None
    try:
        project = load_project(project_path)
        if operation == "test":
            load_fixtures(project.fixtures)
    except StartupError as error:
        report = _failure(str(error), getattr(error, "issues", None))
        if project is not None:
            report["capabilities"]["declared_profiles"] = list(project.profiles)
            for entry in report["issues"]:
                if entry.get("file") is None:
                    entry["file"] = project.fixtures.relative_to(project.root).as_posix()
        return 2, report
    try:
        with (
            _cancellation_signals() as cancellation,
            tempfile.TemporaryDirectory(prefix="gateway7-authoring-") as temporary,
        ):
            report_path = Path(temporary) / "report.json"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "gateway7._offline_worker",
                    str(project.root),
                    operation,
                    str(report_path),
                ],
                cwd=temporary,
                env=_worker_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
            )
            try:
                deadline = time.monotonic() + timeout
                while True:
                    if cancellation.requested:
                        return 2, _failure("Offline authoring execution interrupted")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 and process.poll() is None:
                        return 2, _failure("Offline worker exceeded the wall-clock limit")
                    try:
                        process.wait(timeout=min(0.1, max(remaining, 0)))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if cancellation.requested:
                    return 2, _failure("Offline authoring execution interrupted")
                if process.returncode not in (0, 1, 2):
                    return 2, _failure("Offline worker failed")
                with report_path.open("rb") as source:
                    raw = source.read(MAX_REPORT_BYTES + 1)
                if len(raw) > MAX_REPORT_BYTES:
                    return 2, _failure("Offline worker report exceeded its size limit")
                report = json.loads(raw)
                if (
                    not isinstance(report, dict)
                    or report.get("schema_version") != 2
                    or type(report.get("passed")) is not bool
                    or type(report.get("total")) is not int
                    or type(report.get("failed")) is not int
                    or not isinstance(report.get("cases"), list)
                    or not isinstance(report.get("issues"), list)
                    or not isinstance(report.get("capabilities"), dict)
                ):
                    raise ValueError
                if (process.returncode == 0) != report["passed"]:
                    raise ValueError
                return process.returncode, report
            except KeyboardInterrupt:
                return 2, _failure("Offline authoring execution interrupted")
            finally:
                if process.poll() is None:
                    _terminate_worker(process)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 2, _failure("Offline worker could not complete")


def run_project_tests(
    project_path: str | Path = ".", timeout: float = 30
) -> tuple[int, dict[str, Any]]:
    return _run_project_worker(project_path, "test", timeout)


def inspect_project(
    project_path: str | Path = ".", timeout: float = 30
) -> tuple[int, dict[str, Any]]:
    return _run_project_worker(project_path, "inspect", timeout)


def print_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return
    if "error" in report:
        print("Authoring failed: " + report["error"])
    for item in report.get("issues", []):
        location = item.get("file") or item.get("path", "project")
        if item.get("line") is not None:
            location += ":" + str(item["line"])
        print(f"  {item['code']} at {location}: {item['message']}")
        print("    " + item["hint"])
    for case in report.get("cases", []):
        print(f"{'PASS' if case['passed'] else 'FAIL'} {case['name']} [{case['profile']}]")
        for check in case["checks"]:
            if check["passed"]:
                continue
            print(f"  {check['field']}: {'PASS' if check['passed'] else 'FAIL'}")
            print(
                "    expected: " + json.dumps(check["expected"], ensure_ascii=True, sort_keys=True)
            )
            print("    actual:   " + json.dumps(check["actual"], ensure_ascii=True, sort_keys=True))
    capabilities = report.get("capabilities", {})
    plugin = report.get("plugin")
    if plugin is not None:
        print(f"Plugin: {plugin['id']} ({plugin['module']})")
        print(f"API: {plugin['api_version']}; gateway: {plugin['gateway_version']}")
        source = plugin["source"]
        print(f"Import source: {source['mode']} · {source['path']}")
        print("Settings fields: " + ", ".join(plugin["settings_schema"].get("properties", {})))
        print(
            "Present hooks: "
            + ", ".join(name for name, present in capabilities.get("hooks", {}).items() if present)
        )
    print("Declared profiles: " + ", ".join(capabilities.get("declared_profiles", [])))
    print("Tested positive profiles: " + ", ".join(capabilities.get("tested_profiles", [])))
    if "inspection" in report:
        print("Inspection complete; behavior was not tested.")
    else:
        print(
            f"{report.get('total', 0) - report.get('failed', 0)}/{report.get('total', 0)} cases passed"
        )

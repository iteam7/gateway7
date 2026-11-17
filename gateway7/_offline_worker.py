"""Bounded authoring worker: trusted Python, clean credentials, no OS sandbox."""

from __future__ import annotations

import asyncio
import importlib
from importlib import metadata
import json
import logging
from pathlib import Path
import sys
from typing import Any

import yaml

from gateway7 import __version__
from gateway7.config import GatewayConfig, load_config
from gateway7.errors import GatewayError, ProviderError, StartupError
from gateway7.loader import LoadedPlugins, load_plugins, start_plugins, stop_plugins
from gateway7.models import ChatRequest, ChatResponse
from gateway7.offline import Case, MAX_REPORT_BYTES, _failure, load_fixtures
from gateway7.pipeline import Pipeline
from gateway7.plugin_api import API_VERSION, EarlyStreamUnsupported, ResponsesUnsupported
from gateway7.plugin_diagnostics import diagnostic
from gateway7.plugin_project import PluginProject, PROFILES, load_project, validate_project_config
from gateway7.responses_events import ResponsesTextDelta
from gateway7.responses_models import (
    ResponseMessageItem,
    ResponseOutputTextPart,
    ResponsesConsent,
    ResponsesRequest,
    ResponsesResponse,
)

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
        self.request: ChatRequest | ResponsesRequest | None = None
        self.finished = False

    def _observe(self, request: ChatRequest | ResponsesRequest) -> None:
        self.calls += 1
        self.request = request.model_copy(deep=True)
        if self.case.provider_error:
            raise ProviderError()

    async def complete(self, request: ChatRequest, **_options: Any) -> ChatResponse:
        self._observe(request)
        response = self.case.response_payload()
        assert isinstance(response, ChatResponse)
        self.finished = True
        return response.model_copy(deep=True)

    async def complete_early(
        self, request: ChatRequest, *, on_text: Any, **_options: Any
    ) -> ChatResponse:
        self._observe(request)
        response = self.case.response_payload()
        assert isinstance(response, ChatResponse)
        deltas = self.case.deltas(self.case.provider_deltas)
        if deltas and "".join(deltas) != response.text:
            raise ProviderError()
        for delta in deltas:
            await on_text(delta)
            await asyncio.sleep(0)
        self.finished = True
        return response.model_copy(deep=True)

    async def complete_responses(
        self,
        request: ResponsesRequest,
        *,
        consent: ResponsesConsent = ResponsesConsent(),
        **_options: Any,
    ) -> ResponsesResponse:
        self._observe(request)
        response = self.case.response_payload()
        assert isinstance(response, ResponsesResponse)
        self.finished = True
        return response.model_copy(deep=True)

    async def complete_responses_early(
        self,
        request: ResponsesRequest,
        *,
        on_text_delta: Any,
        consent: ResponsesConsent = ResponsesConsent(),
        **_options: Any,
    ) -> ResponsesResponse:
        self._observe(request)
        response = self.case.response_payload()
        assert isinstance(response, ResponsesResponse)
        deltas = self.case.deltas(self.case.provider_deltas)
        _validate_native_deltas(deltas, response)
        for delta in deltas:
            await on_text_delta(delta.model_copy(deep=True))
            await asyncio.sleep(0)
        self.finished = True
        return response.model_copy(deep=True)


def _validate_native_deltas(records: list[ResponsesTextDelta], response: ResponsesResponse) -> None:
    seen: dict[tuple[int, int], str] = {}
    previous = -1
    for record in records:
        if (
            record.head.id != response.id
            or record.head.model != response.model
            or record.head.created_at != response.created_at
            or record.output_index != 0
            or record.content_index != 0
            or not record.leading_prefix
            or record.sequence_number <= previous
        ):
            raise ProviderError()
        previous = record.sequence_number
        for field in ("parallel_tool_calls", "tool_choice", "tools"):
            expected = getattr(record.head, field)
            if expected is not None:
                actual = getattr(response, field)
                if field == "tools":
                    expected = [tool.model_dump(mode="json") for tool in expected]
                    actual = (
                        [tool.model_dump(mode="json") for tool in actual]
                        if actual is not None
                        else None
                    )
                elif hasattr(expected, "model_dump"):
                    expected = expected.model_dump(mode="json")
                    actual = (
                        actual.model_dump(mode="json") if hasattr(actual, "model_dump") else actual
                    )
                if expected != actual:
                    raise ProviderError()
        try:
            item = response.output[record.output_index]
            if (
                not isinstance(item, ResponseMessageItem)
                or item.id != record.item_id
                or item.phase != record.phase
            ):
                raise ValueError
            content = item.content[record.content_index]
            if not isinstance(content, ResponseOutputTextPart) or content.annotations:
                raise ValueError
            position = (record.output_index, record.content_index)
            combined = seen.get(position, "") + record.delta
            if not content.text.startswith(combined):
                raise ValueError
            seen[position] = combined
        except (IndexError, TypeError, ValueError):
            raise ProviderError() from None


def _preview(value: Any) -> Any:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
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


async def _case(
    plugins: LoadedPlugins, config: GatewayConfig, case: Case, index: int
) -> dict[str, Any]:
    provider = FixtureProvider(case)
    answer: ChatResponse | ResponsesResponse | None = None
    error = None
    deltas: list[Any] = []
    before_finish = True

    async def text_sink(value: str) -> None:
        nonlocal before_finish
        before_finish = before_finish and not provider.finished
        deltas.append(value)

    async def native_sink(value: ResponsesTextDelta) -> None:
        nonlocal before_finish
        before_finish = before_finish and not provider.finished
        deltas.append(value.model_dump(mode="json"))

    pipeline = Pipeline(plugins, provider, config.limits, provider_name="openai")
    request = case.request_payload()
    try:
        if case.profile == "responses-early":
            assert isinstance(request, ResponsesRequest)
            answer = await pipeline.run_responses_early(
                request, f"fixture_{index}", consent=case.consent, on_text_delta=native_sink
            )
        elif case.profile == "responses":
            assert isinstance(request, ResponsesRequest)
            answer = await pipeline.run_responses(request, f"fixture_{index}", consent=case.consent)
        elif case.profile == "chat-early":
            assert isinstance(request, ChatRequest)
            answer = await pipeline.run_early(request, f"fixture_{index}", on_text=text_sink)
        else:
            assert isinstance(request, ChatRequest)
            answer = await pipeline.run(request, f"fixture_{index}")
    except EarlyStreamUnsupported:
        error = "early_stream_unsupported"
    except ResponsesUnsupported:
        error = "responses_unsupported"
    except GatewayError as caught:
        error = caught.code
    checks = [_check("provider_calls", case.expected.provider_calls, provider.calls)]
    if case.expected.request is not None:
        expected_request = case.request_payload(case.expected.request).model_dump(mode="json")
        checks.append(
            _check(
                "request",
                expected_request,
                None if provider.request is None else provider.request.model_dump(mode="json"),
            )
        )
    expected_response = (
        None
        if case.expected.response is None
        else case.response_payload(case.expected.response).model_dump(mode="json")
    )
    checks.extend(
        [
            _check(
                "response",
                expected_response,
                None if answer is None else answer.model_dump(mode="json"),
            ),
            _check("error", case.expected.error, error),
        ]
    )
    if case.expected.deltas is not None:
        expected_deltas = [
            value.model_dump(mode="json") if isinstance(value, ResponsesTextDelta) else value
            for value in case.deltas(case.expected.deltas)
        ]
        checks.append(_check("deltas", expected_deltas, deltas))
        if expected_deltas:
            checks.append(_check("deltas_before_completion", True, before_finish))
    return {
        "name": case.name,
        "profile": case.profile,
        "passed": all(check["passed"] for check in checks),
        "provider_calls": provider.calls,
        "negative": case.expected.error is not None,
        "early_emission": bool(deltas) and before_finish,
        "checks": checks,
    }


def _safe_schema(value: Any) -> Any:
    """Remove schema annotations without corrupting property names or literals."""
    if not isinstance(value, dict):
        return value
    maps = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
    schemas = {
        "additionalProperties",
        "unevaluatedProperties",
        "items",
        "contains",
        "not",
        "if",
        "then",
        "else",
        "propertyNames",
        "additionalItems",
        "unevaluatedItems",
        "contentSchema",
    }
    arrays = {"allOf", "anyOf", "oneOf", "prefixItems"}
    result: dict[str, Any] = {}
    for name, child in value.items():
        if name in ("default", "examples"):
            continue
        if name in maps and isinstance(child, dict):
            result[name] = {key: _safe_schema(schema) for key, schema in child.items()}
        elif name in schemas and isinstance(child, dict):
            result[name] = _safe_schema(child)
        elif name in arrays and isinstance(child, list):
            result[name] = [_safe_schema(schema) for schema in child]
        else:
            # enum/const and unknown extension values are literal JSON data.
            result[name] = child
    return result


def _capabilities(
    project: PluginProject, plugins: LoadedPlugins, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    names = (
        "handle",
        "startup",
        "shutdown",
        "prepare_early_stream",
        "prepare_responses",
        "check_responses",
        "prepare_early_responses",
    )
    chain = plugins.middleware_chain
    hooks = {
        name: bool(chain) and all(getattr(plugin, name) is not None for plugin in chain)
        for name in names
    }
    tested = sorted(
        {
            case["profile"]
            for case in cases
            if case["passed"]
            and not case["negative"]
            and case["provider_calls"] == 1
            and (not case["profile"].endswith("early") or case["early_emission"])
        }
    )
    return {
        "declared_profiles": list(project.profiles),
        "hooks": hooks,
        "supports_tools": bool(chain) and all(plugin.descriptor.supports_tools for plugin in chain),
        "tested_profiles": tested,
    }


def _profile_matrix(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix = []
    for profile in PROFILES:
        selected = [case for case in cases if case["profile"] == profile]
        positive = sum(case["passed"] and not case["negative"] for case in selected)
        matrix.append(
            {
                "profile": profile,
                "cases": len(selected),
                "passed": sum(case["passed"] for case in selected),
                "positive_passed": positive,
                "early_emission_passed": sum(
                    case["passed"] and case["early_emission"] for case in selected
                ),
                "negative_passed": sum(case["passed"] and case["negative"] for case in selected),
                "status": "failed"
                if any(not case["passed"] for case in selected)
                else "passed_cases"
                if positive
                else "negative_only"
                if selected
                else "not_tested",
            }
        )
    return matrix


def _project_config(project: PluginProject) -> tuple[GatewayConfig, Any]:
    config = load_config(project.config)
    validate_project_config(project, config)
    candidates = [
        project.root.joinpath(*project.module.split(".")).with_suffix(".py"),
        project.root.joinpath(*project.module.split("."), "__init__.py"),
    ]
    if not any(
        path.is_file() and path.resolve().is_relative_to(project.root) for path in candidates
    ):
        raise diagnostic(
            "Declared plugin source is unavailable inside the project",
            "project_source_unavailable",
            "tool.gateway7.plugin.module",
            "Create the declared module inside this project; an installed stale package is not a source-mode fallback",
            file="pyproject.toml",
        )
    # Only an explicit authoring project changes this disposable worker's path.
    sys.path.insert(0, str(project.root))
    try:
        module = _project_module(project)
    except StartupError:
        raise
    except Exception:
        raise diagnostic(
            "Cannot import the declared project plugin",
            "plugin_import_failed",
            "tool.gateway7.plugin.module",
            "Check project imports and installed dependencies; exception text is intentionally omitted",
            file="pyproject.toml",
        ) from None
    return config, module


def _project_module(project: PluginProject) -> Any:
    module = importlib.import_module(project.module)
    source_file = module.__file__
    if source_file is None or not Path(source_file).resolve().is_relative_to(project.root):
        raise diagnostic(
            "Declared module was not imported from project source",
            "project_source_mismatch",
            "tool.gateway7.plugin.module",
            "Use a uniquely named plugin package inside the selected project",
            file="pyproject.toml",
        )
    return module


def _inspect(project: PluginProject, plugins: LoadedPlugins, module: Any) -> dict[str, Any]:
    descriptor = module.PLUGIN
    try:
        schema = _safe_schema(descriptor.settings_model.model_json_schema())
    except Exception:
        raise diagnostic(
            "Cannot describe the plugin settings schema",
            "plugin_schema_invalid",
            "settings_schema",
            "Use JSON-schema-compatible public settings types",
        ) from None
    distributions = []
    for distribution in metadata.packages_distributions().get(project.module.split(".", 1)[0], [])[
        :8
    ]:
        try:
            distributions.append({"name": distribution, "version": metadata.version(distribution)})
        except metadata.PackageNotFoundError:
            pass
    return {
        "schema_version": 2,
        "passed": True,
        "total": 0,
        "failed": 0,
        "cases": [],
        "issues": [],
        "capabilities": _capabilities(project, plugins, []),
        "profiles": _profile_matrix([]),
        "plugin": {
            "module": project.module,
            "id": descriptor.id,
            "api_version": descriptor.api_version,
            "gateway_api_version": API_VERSION,
            "gateway_version": __version__,
            "settings_schema": schema,
            "source": {
                "mode": "project",
                "path": Path(module.__file__).resolve().relative_to(project.root).as_posix(),
            },
            "distributions": distributions,
        },
        "inspection": {
            "factories_executed": True,
            "startup_executed": False,
            "provider_calls": 0,
            "behavior_verified": False,
            "trust_boundary": "trusted_python_not_os_sandbox",
        },
    }


def _annotate(project: PluginProject, report: dict[str, Any]) -> None:
    positions: dict[str, int] = {}
    try:
        with project.config.open("rb") as source:
            raw = source.read(1_048_577)
        if len(raw) > 1_048_576:
            return
        root = yaml.compose(raw.decode("utf-8"), Loader=yaml.SafeLoader)
        visited: set[int] = set()

        def visit(node: Any, path: str, depth: int = 0) -> None:
            if node is None or id(node) in visited or len(visited) >= 20000 or depth > 32:
                return
            visited.add(id(node))
            positions[path] = node.start_mark.line + 1
            if isinstance(node, yaml.MappingNode):
                for key, child in node.value:
                    if isinstance(key, yaml.ScalarNode):
                        visit(child, (path + "." if path else "") + key.value, depth + 1)
            elif isinstance(node, yaml.SequenceNode):
                for index, child in enumerate(node.value):
                    visit(child, path + "." + str(index), depth + 1)

        visit(root, "")
    except Exception:
        return
    for entry in report["issues"]:
        if entry.get("file") == "pyproject.toml":
            continue
        entry["file"] = (
            project.fixtures.relative_to(project.root).as_posix()
            if entry["path"].startswith("fixtures")
            else project.config.relative_to(project.root).as_posix()
        )
        if entry.get("line") is not None or entry["path"].startswith("fixtures"):
            continue
        path = entry["path"].removeprefix("config.")
        while path not in positions and path:
            path = path.rpartition(".")[0]
        if path in positions:
            entry["line"] = positions[path]


async def _run(project_path: str, operation: str) -> dict[str, Any]:
    project = load_project(project_path)
    try:
        config, module = _project_config(project)
        plugins = load_plugins(config)
        if operation == "inspect":
            return _inspect(project, plugins, module)
        suite = load_fixtures(project.fixtures)
        await start_plugins(plugins, config.limits.hook_timeout_seconds)
        try:
            semaphore = asyncio.Semaphore(suite.concurrency)

            async def run(index: int, case: Case):
                async with semaphore:
                    return await _case(plugins, config, case, index)

            results = await asyncio.gather(
                *(run(index, case) for index, case in enumerate(suite.cases))
            )
        finally:
            await stop_plugins(plugins, config.limits.hook_timeout_seconds)
        failed = sum(not case["passed"] for case in results)
        return {
            "schema_version": 2,
            "passed": failed == 0,
            "total": len(results),
            "failed": failed,
            "cases": results,
            "issues": [],
            "capabilities": _capabilities(project, plugins, results),
            "profiles": _profile_matrix(results),
            "execution": {
                "instance_lifecycle": "one_per_suite",
                "concurrency": suite.concurrency,
                "provider": "synthetic",
                "trust_boundary": "trusted_python_not_os_sandbox",
            },
        }
    except StartupError as error:
        report = _failure(str(error), getattr(error, "issues", None))
        _annotate(project, report)
        return report


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[2] not in ("test", "inspect"):
        return 2
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logging.disable(logging.CRITICAL)
    sys.addaudithook(_network_guard)
    try:
        try:
            report = loop.run_until_complete(_run(sys.argv[1], sys.argv[2]))
            code = 0 if report["passed"] else 2 if report.get("error") else 1
        except Exception:
            report, code = _failure("Offline authoring execution failed"), 2
        encoded = json.dumps(report, ensure_ascii=True, sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_REPORT_BYTES:
            report, code = _failure("Offline worker report exceeded its size limit"), 2
            encoded = json.dumps(report).encode("utf-8")
        Path(sys.argv[3]).write_bytes(encoded)
        return code
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())

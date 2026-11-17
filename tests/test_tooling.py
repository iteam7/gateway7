"""Project authoring uses real isolated workers and honest capability evidence."""

import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
import yaml

from gateway7._offline_worker import _safe_schema
from gateway7.errors import StartupError
from gateway7.offline import (
    MAX_FILE_BYTES,
    inspect_project,
    load_fixtures,
    print_report,
    run_project_tests,
)
from gateway7.plugin_project import load_project
from gateway7.scaffold import create_plugin_project

PASS_PLUGIN = """from pydantic import BaseModel, ConfigDict, Field
from gateway7.plugin_api import PluginDescriptor
class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    count: int = Field(default=1, ge=1)
class Middleware:
    async def handle(self, request, context, call_next):
        return await call_next(request)
    async def prepare_early_stream(self, request, context):
        return request
    async def prepare_responses(self, request, context):
        return request
    async def check_responses(self, response, context):
        return response
    async def prepare_early_responses(self, request, context):
        return request
PLUGIN = PluginDescriptor("fixture", 2, Settings, lambda settings: Middleware(), supports_tools=True)
"""


def native_response(text="answer"):
    return {
        "id": "resp_fixture",
        "created_at": 1,
        "model": "fake",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_fixture",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }


def native_deltas():
    return [
        {
            "head": {"id": "resp_fixture", "created_at": 1, "model": "fake"},
            "sequence_number": index + 1,
            "item_id": "msg_fixture",
            "output_index": 0,
            "content_index": 0,
            "phase": "final_answer",
            "delta": value,
            "leading_prefix": True,
        }
        for index, value in enumerate(("ans", "wer"))
    ]


def chat_case(name="ordinary", **changes):
    request = {"messages": [{"role": "user", "content": "synthetic request"}]}
    response = {"text": "answer", "usage": {"input_tokens": 8, "output_tokens": 3}}
    return {
        "name": name,
        "profile": "chat",
        "request": request,
        "provider_response": response,
        "expected": {"provider_calls": 1, "request": request, "response": response},
        **changes,
    }


def project(tmp_path, *, source=PASS_PLUGIN, cases=None, profiles=("chat",), concurrency=1):
    root = tmp_path / "project"
    root.mkdir()
    (root / "plugin_under_test.py").write_text(source, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.gateway7.plugin]\nschema_version=1\nmodule="plugin_under_test"\nconfig="gateway.yaml"\nfixtures="fixtures.json"\nprofiles='
        + json.dumps(list(profiles))
        + "\n",
        encoding="utf-8",
    )
    (root / "gateway.yaml").write_text(
        "plugins:\n  subject:\n    module: plugin_under_test\n    required: true\nmiddleware: [subject]\n",
        encoding="utf-8",
    )
    (root / "fixtures.json").write_text(
        json.dumps(
            {"schema_version": 2, "concurrency": concurrency, "cases": cases or [chat_case()]}
        ),
        encoding="utf-8",
    )
    return root


def test_generated_presets_run_real_profiles_and_do_not_certify_negative_early_support(tmp_path):
    guard = create_plugin_project("guard", tmp_path, "guard")
    redactor = create_plugin_project("redactor", tmp_path, "redact")
    for root, supported in (
        (guard, {"chat", "chat-tools", "chat-early", "responses", "responses-early"}),
        (redactor, {"chat", "chat-tools", "responses"}),
    ):
        code, report = run_project_tests(root)
        assert code == 0, report
        assert report["schema_version"] == 2 and report["passed"]
        assert set(report["capabilities"]["tested_profiles"]) == supported
        assert report["execution"]["instance_lifecycle"] == "one_per_suite"
    assert {row["profile"] for row in report["profiles"] if row["status"] == "negative_only"} == {
        "chat-early",
        "responses-early",
    }


def test_inspect_is_not_a_behavior_certificate_and_reports_actual_source_and_schema(tmp_path):
    root = project(tmp_path)
    code, report = inspect_project(root)
    assert code == 0, report
    assert report["plugin"]["source"] == {"mode": "project", "path": "plugin_under_test.py"}
    assert report["plugin"]["api_version"] == report["plugin"]["gateway_api_version"] == 2
    assert report["capabilities"]["tested_profiles"] == []
    assert report["inspection"]["provider_calls"] == 0
    assert (
        not report["inspection"]["startup_executed"]
        and not report["inspection"]["behavior_verified"]
    )
    schema = report["plugin"]["settings_schema"]
    assert schema["properties"]["count"]["type"] == "integer"
    assert "default" not in schema["properties"]["count"]


def test_schema_annotation_redaction_preserves_reserved_property_and_literal_names():
    schema = {
        "properties": {
            "default": {"type": "string", "default": "synthetic-private-default"},
            "examples": {"enum": [{"default": "literal", "examples": [1]}]},
        },
        "$defs": {"default": {"const": {"default": "literal"}, "examples": ["private"]}},
        "default": {"private": True},
    }
    output = _safe_schema(schema)
    assert output["properties"]["default"] == {"type": "string"}
    assert output["properties"]["examples"]["enum"] == [{"default": "literal", "examples": [1]}]
    assert output["$defs"]["default"]["const"] == {"default": "literal"}
    assert "synthetic-private-default" not in json.dumps(output)


def test_mismatch_has_stable_json_and_concise_human_failure_details(tmp_path, capsys):
    root = project(
        tmp_path,
        cases=[
            chat_case(),
            chat_case("mismatch", expected={"provider_calls": 1, "response": {"text": "wrong"}}),
        ],
    )
    code, report = run_project_tests(root)
    assert code == 1 and report["failed"] == 1 and report["total"] == 2
    print_report(report, as_json=False)
    human = capsys.readouterr().out
    assert "PASS ordinary [chat]" in human and "FAIL mismatch [chat]" in human
    assert human.count("expected:") == 1 and "wrong" in human
    print_report(report, as_json=True)
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize("phase", ["import", "factory", "startup", "handler"])
def test_network_and_process_guard_is_installed_before_all_plugin_phases(tmp_path, phase):
    guard = """import socket, subprocess

def probe():
    try:
        socket.getaddrinfo("localhost", 9)
    except PermissionError:
        pass
    else:
        raise AssertionError("network guard absent")
    try:
        subprocess.run(["unused-synthetic-program"])
    except PermissionError:
        pass
    else:
        raise AssertionError("subprocess guard absent")
"""
    source = guard + PASS_PLUGIN
    if phase == "import":
        source += "\nprobe()\n"
    elif phase == "factory":
        source = source.replace(
            "lambda settings: Middleware()", "lambda settings: (probe(), Middleware())[1]"
        )
    elif phase == "startup":
        source = source.replace(
            "class Middleware:", "class Middleware:\n    async def startup(self):\n        probe()"
        )
    else:
        source = source.replace(
            "        return await call_next(request)",
            "        probe()\n        return await call_next(request)",
        )
    root = project(tmp_path, source=source)
    code, report = run_project_tests(root)
    assert code == 0, report


def test_worker_strips_credentials_proxy_startup_environment_and_discards_plugin_output(
    tmp_path, monkeypatch
):
    variables = (
        "SYNTHETIC_PROVIDER_SECRET",
        "SYNTHETIC_GATEWAY_SECRET",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "HOME",
        "PYTHONPATH",
        "SSL_CERT_FILE",
    )
    for name in variables:
        monkeypatch.setenv(name, "synthetic-private-marker-unique")
    source = (
        "import os,sys\nassert all(name not in os.environ for name in "
        + repr(variables)
        + ")\nprint('SYNTHETIC-PLUGIN-NOISE')\nprint('SYNTHETIC-STDERR-NOISE',file=sys.stderr)\n"
        + PASS_PLUGIN
    )
    root = project(tmp_path, source=source)
    for run in (run_project_tests, inspect_project):
        code, report = run(root)
        assert code == 0
        assert "synthetic-private-marker-unique" not in json.dumps(report)
        assert "SYNTHETIC-PLUGIN-NOISE" not in json.dumps(report)


@pytest.mark.parametrize("phase", ["import", "factory", "startup", "handler"])
def test_wall_clock_bound_stops_noncooperative_code(tmp_path, phase):
    source = PASS_PLUGIN
    if phase == "import":
        source += "\nwhile True:\n    pass\n"
    elif phase == "factory":
        source = source.replace(
            "PLUGIN =", "def blocked(settings):\n    while True:\n        pass\nPLUGIN ="
        ).replace("lambda settings: Middleware()", "blocked")
    elif phase == "startup":
        source = source.replace(
            "class Middleware:",
            "class Middleware:\n    async def startup(self):\n        while True:\n            pass",
        )
    else:
        source = source.replace(
            "        return await call_next(request)", "        while True:\n            pass"
        )
    root = project(tmp_path, source=source)
    started = time.monotonic()
    code, report = run_project_tests(root, timeout=1)
    assert code == 2 and "wall-clock" in report["error"]
    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("config", "../outside.yaml"),
        ("fixtures", "/tmp/private.json"),
        ("config", "C:\\private.yaml"),
    ],
)
def test_project_paths_are_confined_on_all_platforms(tmp_path, field, value):
    root = project(tmp_path)
    path = root / "pyproject.toml"
    text = path.read_text().replace(
        field + '="' + ("gateway.yaml" if field == "config" else "fixtures.json") + '"',
        field + "=" + json.dumps(value),
    )
    path.write_text(text)
    with pytest.raises(StartupError) as caught:
        load_project(root)
    assert "project_path_invalid" in json.dumps(caught.value.issues)


def test_missing_source_never_falls_back_to_installed_plugin(tmp_path):
    root = project(tmp_path)
    (root / "plugin_under_test.py").unlink()
    code, report = inspect_project(root)
    assert code == 2
    assert report["issues"][0]["code"] == "project_source_unavailable"


def test_manifest_module_must_be_enabled_in_the_actual_tested_chain(tmp_path):
    root = project(tmp_path)
    (root / "gateway.yaml").write_text("plugins: {}\nmiddleware: []\n")
    for run in (run_project_tests, inspect_project):
        code, report = run(root)
        assert code == 2 and report["issues"][0]["code"] == "project_module_inactive"


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(schema_version=1),
        lambda value: value.update(schema_version=True),
        lambda value: value["cases"][0].update(profile="unsupported"),
        lambda value: value["cases"][0]["expected"].update(provider_calls=True),
        lambda value: value["cases"][0].update(unknown="synthetic-private"),
    ],
)
def test_only_current_closed_fixture_schema_is_accepted_without_value_leaks(tmp_path, change):
    root = project(tmp_path)
    path = root / "fixtures.json"
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))
    code, report = run_project_tests(root)
    assert code == 2 and report["issues"]
    assert "synthetic-private" not in json.dumps(report)


@pytest.mark.parametrize(
    "content",
    [
        '{"schema_version":2,"schema_version":2}',
        '{"schema_version":2,"cases":[],"bad":NaN}',
        '{"schema_version":2,"cases":[],"bad":"\\ud800"}',
    ],
)
def test_duplicate_nonfinite_and_invalid_unicode_fixture_json_is_rejected(tmp_path, content):
    path = tmp_path / "fixtures.json"
    path.write_text(content)
    with pytest.raises(StartupError):
        load_fixtures(path)


def test_fixture_file_size_and_depth_are_bounded(tmp_path):
    path = tmp_path / "fixtures.json"
    for content in (" " * (MAX_FILE_BYTES + 1), "[" * 80 + "0" + "]" * 80):
        path.write_text(content)
        with pytest.raises(StartupError):
            load_fixtures(path)


def test_settings_diagnostic_contains_safe_path_line_hint_but_never_unknown_key_or_value(tmp_path):
    root = project(tmp_path)
    (root / "gateway.yaml").write_text(
        "plugins:\n  subject:\n    module: plugin_under_test\n    settings:\n      count: 'synthetic-private-value'\n      synthetic_private_key: true\nmiddleware: [subject]\n"
    )
    code, report = inspect_project(root)
    assert code == 2
    assert any(
        row["path"] == "plugins.subject.settings.count" and row["line"] == 5
        for row in report["issues"]
    )
    text = json.dumps(report)
    assert "synthetic-private-value" not in text and "synthetic_private_key" not in text
    assert "Traceback" not in text


def test_api_and_import_failures_get_stage_specific_sanitized_diagnostics(tmp_path):
    root = project(tmp_path, source=PASS_PLUGIN.replace('"fixture", 2,', '"fixture", 3,'))
    code, report = inspect_project(root)
    assert code == 2 and report["issues"][0]["code"] == "plugin_api_unsupported"
    assert "API 2" in report["issues"][0]["hint"] and "API 3" in report["issues"][0]["hint"]
    (root / "plugin_under_test.py").write_text(
        "raise RuntimeError('synthetic-private-import-exception')"
    )
    code, report = inspect_project(root)
    assert code == 2 and report["issues"][0]["code"] == "plugin_import_failed"
    assert "synthetic-private-import-exception" not in json.dumps(report)
    assert "migrate" not in json.dumps(report)


def test_recursive_yaml_diagnostic_annotation_is_bounded(tmp_path):
    root = project(tmp_path)
    (root / "gateway.yaml").write_text("plugins: &cycle {again: *cycle}\n")
    started = time.monotonic()
    code, report = inspect_project(root, timeout=3)
    assert code == 2 and "wall-clock" not in report.get("error", "")
    assert time.monotonic() - started < 3


def test_shared_lifecycle_and_concurrent_contexts_are_really_exercised(tmp_path):
    source = PASS_PLUGIN.replace(
        "class Middleware:",
        """class Middleware:
    def __init__(self):
        self.active = 0
        self.peak = 0
        self.starts = 0
    async def startup(self):
        self.starts += 1
    async def shutdown(self):
        import json
        from pathlib import Path
        Path(__file__).with_name("lifecycle.json").write_text(json.dumps({"starts": self.starts, "peak": self.peak, "active": self.active}))""",
    ).replace(
        "        return await call_next(request)",
        """        import asyncio
        self.active += 1
        self.peak = max(self.peak, self.active)
        context.state["owner"] = context.request_id
        await asyncio.sleep(0.01)
        assert context.state["owner"] == context.request_id
        result = await call_next(request)
        self.active -= 1
        return result""",
    )
    root = project(
        tmp_path,
        source=source,
        cases=[chat_case("case " + str(index)) for index in range(4)],
        concurrency=4,
    )
    code, report = run_project_tests(root)
    assert code == 0, report
    lifecycle = json.loads((root / "lifecycle.json").read_text())
    assert lifecycle == {"starts": 1, "peak": 4, "active": 0}


@pytest.mark.parametrize("profile", ["responses", "responses-early"])
def test_native_profiles_preserve_full_dtos_and_metadata(profile, tmp_path):
    response = native_response()
    case = {
        "name": "native",
        "profile": profile,
        "request": {"input": "synthetic"},
        "provider_response": response,
        "expected": {"provider_calls": 1, "request": {"input": "synthetic"}, "response": response},
    }
    if profile.endswith("early"):
        case["provider_deltas"] = native_deltas()
        case["expected"]["deltas"] = native_deltas()
    root = project(tmp_path, cases=[case], profiles=(profile,))
    code, report = run_project_tests(root)
    assert code == 0, report
    assert report["capabilities"]["tested_profiles"] == [profile]
    if profile.endswith("early"):
        actual = next(
            check["actual"] for check in report["cases"][0]["checks"] if check["field"] == "deltas"
        )
        assert actual[0]["item_id"] == "msg_fixture" and actual[0]["phase"] == "final_answer"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda delta: delta[0]["head"].update(created_at=2),
        lambda delta: delta[0].update(output_index=1),
        lambda delta: delta[0].update(leading_prefix=False),
        lambda delta: delta[1].update(sequence_number=1),
        lambda delta: delta[0]["head"].update(parallel_tool_calls=False),
    ],
)
def test_native_early_provider_oracle_rejects_contradictory_proof(tmp_path, mutation):
    records = native_deltas()
    mutation(records)
    case = {
        "name": "invalid native proof",
        "profile": "responses-early",
        "request": {"input": "synthetic"},
        "provider_response": native_response(),
        "provider_deltas": records,
        "expected": {"provider_calls": 1, "error": "provider_error", "deltas": []},
    }
    root = project(tmp_path, cases=[case], profiles=("responses-early",))
    code, report = run_project_tests(root)
    assert code == 0, report
    assert report["capabilities"]["tested_profiles"] == []


@pytest.mark.parametrize("consent", [False, True])
def test_native_consent_is_explicit_and_cannot_be_inferred_from_fixture_shape(tmp_path, consent):
    request = {
        "input": [
            {"type": "reasoning", "id": "rs_fixture", "encrypted_content": "synthetic-opaque"}
        ]
    }
    expected = (
        {"provider_calls": 1, "request": request, "response": native_response()}
        if consent
        else {"provider_calls": 0, "error": "invalid_request"}
    )
    case = {
        "name": "opaque consent",
        "profile": "responses",
        "request": request,
        "consent": {"allow_opaque": consent, "allow_hosted": False},
        "provider_response": native_response(),
        "expected": expected,
    }
    root = project(tmp_path, cases=[case], profiles=("responses",))
    code, report = run_project_tests(root)
    assert code == 0, report


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal semantics")
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_interruption_reports_failure_and_reaps_isolated_worker(tmp_path, signum):
    source = "import os\nfrom pathlib import Path\nPath(__file__).with_name('worker.pid').write_text(str(os.getpid()))\nwhile True:\n    pass\n"
    root = project(tmp_path, source=source)
    process = subprocess.Popen(
        [sys.executable, "-I", "-m", "gateway7", "plugin", "test", str(root), "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker_pid = None
    try:
        marker = root / "worker.pid"
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.025)
        assert marker.exists()
        worker_pid = int(marker.read_text())
        process.send_signal(signum)
        output, error = process.communicate(timeout=10)
        assert process.returncode == 2
        assert "interrupted" in json.loads(output)["error"] and "Traceback" not in error
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if worker_pid is not None:
            try:
                os.killpg(worker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_nested_case_name_diagnostic_keeps_known_path_and_safe_size_hint(tmp_path):
    root = project(tmp_path, cases=[chat_case("Case " + "x" * 128)])
    code, report = run_project_tests(root)
    assert code == 2
    names = [item for item in report["issues"] if item["path"] == "fixtures.cases.0.name"]
    assert len(names) == 1
    assert names[0]["code"] == "field_size" and "128" in names[0]["hint"]
    assert "Case " + "x" * 128 not in json.dumps(report)


@pytest.mark.parametrize("emit_prefix", [False, True])
def test_native_early_can_hold_all_or_extend_a_valid_prefix_until_final(tmp_path, emit_prefix):
    response = native_response()
    records = native_deltas()[:1] if emit_prefix else []
    if not emit_prefix:
        response["output"].insert(0, {"type": "reasoning", "id": "rs_fixture", "summary": []})
    case = {
        "name": "held final native response",
        "profile": "responses-early",
        "request": {"input": "synthetic"},
        "provider_response": response,
        "provider_deltas": records,
        "expected": {"provider_calls": 1, "response": response, "deltas": records},
    }
    root = project(tmp_path, cases=[case], profiles=("responses-early",))
    code, report = run_project_tests(root)
    assert code == 0, report
    assert report["capabilities"]["tested_profiles"] == (["responses-early"] if emit_prefix else [])


@pytest.mark.parametrize("allow_hosted", [False, True])
def test_hosted_tool_capability_is_explicit_in_synthetic_native_cases(tmp_path, allow_hosted):
    request = {"input": "synthetic", "tools": [{"type": "web_search"}]}
    expected = (
        {"provider_calls": 1, "request": request, "response": native_response()}
        if allow_hosted
        else {"provider_calls": 0, "error": "invalid_request"}
    )
    case = {
        "name": "hosted consent",
        "profile": "responses",
        "request": request,
        "provider_response": native_response(),
        "consent": {"allow_opaque": False, "allow_hosted": allow_hosted},
        "expected": expected,
    }
    root = project(tmp_path, cases=[case], profiles=("responses",))
    code, report = run_project_tests(root)
    assert code == 0, report

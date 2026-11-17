"""Generated plugin projects are self-contained, safe to create and runnable."""

import ast
import json
import os
import subprocess
import sys
import tomllib

from packaging.requirements import Requirement
import pytest

from gateway7 import __version__
from gateway7.errors import StartupError
from gateway7.scaffold import create_plugin_project


@pytest.mark.parametrize("template", ["guard", "redact"])
def test_generated_project_has_local_contract_manifest_and_editable_tests(tmp_path, template):
    project = create_plugin_project("company_policy", tmp_path, template)
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    manifest = metadata["tool"]["gateway7"]["plugin"]
    assert manifest["schema_version"] == 1
    assert manifest["module"] == "gateway7_plugin_company_policy.plugin"
    assert manifest["config"] == "gateway.yaml" and manifest["fixtures"] == "fixtures.json"
    assert metadata["tool"]["ruff"]["lint"]["select"] == ["E4", "E7", "E9", "F"]
    assert metadata["tool"]["mypy"]["strict"] is True
    assert metadata["tool"]["mypy"]["files"] == ["gateway7_plugin_company_policy", "tests"]
    assert metadata["dependency-groups"]["dev"] == ["ruff>=0.11,<1", "mypy>=1.15,<3"]
    for documentation in ("README.md", "AGENTS.md"):
        text = (project / documentation).read_text()
        assert "uv pip install --group dev" in text
        assert "ruff format --check ." in text and "ruff check ." in text and "mypy" in text
    contract = (project / "CONTRACT.md").read_text()
    assert "128 characters" in contract and "1 MiB" in contract
    assert "before completion" in contract and "empty prefix" in contract
    expected = {"chat", "chat-tools", "responses"}
    if template == "guard":
        expected |= {"chat-early", "responses-early"}
    assert set(manifest["profiles"]) == expected
    assert __version__ in (project / "CONTRACT.md").read_text()
    assert "middleware API 2" in (project / "AGENTS.md").read_text()
    assert "--config" not in (project / "AGENTS.md").read_text()
    for path in project.rglob("*.py"):
        ast.parse(path.read_text())
    fixtures = json.loads((project / "fixtures.json").read_text())
    assert fixtures["schema_version"] == 2
    assert {case["profile"] for case in fixtures["cases"]} == {
        "chat",
        "chat-tools",
        "responses",
        "chat-early",
        "responses-early",
    }
    positive = {
        case["profile"]
        for case in fixtures["cases"]
        if case["expected"]["provider_calls"] == 1 and "error" not in case["expected"]
    }
    assert positive == expected
    if template == "redact":
        negatives = {
            case["profile"]: case["expected"]
            for case in fixtures["cases"]
            if case["profile"].endswith("early")
        }
        assert negatives["chat-early"]["error"] == "early_stream_unsupported"
        assert negatives["responses-early"]["error"] == "responses_unsupported"
        assert all(case["provider_calls"] == 0 for case in negatives.values())


@pytest.mark.parametrize("version", [__version__, "0.9.7", "1.2.3"])
def test_dependency_requires_actual_helper_bearing_build_and_excludes_next_minor(
    tmp_path, monkeypatch, version
):
    from gateway7 import scaffold

    monkeypatch.setattr(scaffold, "__version__", version)
    project = create_plugin_project("policy", tmp_path)
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    requirement = Requirement(metadata["project"]["dependencies"][0])
    major, minor, _ = version.split(".", 2)
    assert requirement.name == "gateway7"
    assert requirement.specifier.contains(version)
    assert not requirement.specifier.contains(f"{major}.{int(minor) + 1}.0")
    assert not requirement.specifier.contains("0.4.99")
    assert version in (project / "CONTRACT.md").read_text()
    assert metadata["project"]["dependencies"][0] in (project / "README.md").read_text()


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/b", "a.b", "a-b", "class", "_private", "Upper", "a" * 49, "con", "lpt1"],
)
def test_scaffold_refuses_unsafe_or_nonportable_name_without_partial_project(tmp_path, name):
    with pytest.raises(StartupError):
        create_plugin_project(name, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_scaffold_refuses_existing_target_without_changing_its_contents(tmp_path, kind):
    target = tmp_path / "policy"
    if kind == "file":
        target.write_text("keep")
    elif kind == "directory":
        target.mkdir()
        (target / "keep").write_text("keep")
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep").write_text("keep")
        try:
            target.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Directory symlinks unavailable")
    with pytest.raises(StartupError, match="already exists"):
        create_plugin_project("policy", tmp_path)
    assert (target if kind == "file" else target / "keep").read_text() == "keep"


def test_scaffold_rejects_unknown_template_without_creating_output(tmp_path):
    with pytest.raises(StartupError, match="template"):
        create_plugin_project("policy", tmp_path, "invented")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("template", ["guard", "redact"])
def test_generated_unit_checks_run_using_public_helper_without_core_checkout(tmp_path, template):
    project = create_plugin_project("policy", tmp_path, template)
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=project,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ran 2 tests" in result.stderr


@pytest.mark.parametrize("template", ["guard", "redact"])
def test_generated_fixture_suite_covers_only_actual_compatible_profiles(tmp_path, template):
    from gateway7.offline import inspect_project, run_project_tests

    project = create_plugin_project("policy", tmp_path, template)
    code, report = run_project_tests(project)
    assert code == 0, report
    expected = {"chat", "chat-tools", "responses"}
    if template == "guard":
        expected |= {"chat-early", "responses-early"}
    capabilities = report["capabilities"]
    assert set(capabilities["declared_profiles"]) == expected
    assert set(capabilities["tested_profiles"]) == expected
    assert report["passed"] and report["failed"] == 0
    code, inspected = inspect_project(project)
    assert code == 0, inspected
    assert inspected["capabilities"]["tested_profiles"] == []


@pytest.mark.parametrize("template", ["guard", "redact"])
def test_generated_source_passes_its_actual_formatter_linter_and_strict_types(tmp_path, template):
    project = create_plugin_project("policy", tmp_path, template)
    commands = [
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "mypy"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=project,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

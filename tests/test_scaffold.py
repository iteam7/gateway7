"""Generated plugin projects are self-contained, safe to create and runnable."""

import ast
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
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


@pytest.fixture(scope="module")
def reviewed_gateway_wheel(tmp_path_factory):
    """Build the reviewed SDK once; each install check gets a private environment."""
    root = Path(__file__).resolve().parents[1]
    artifacts = tmp_path_factory.mktemp("reviewed-gateway-wheel")
    cache = tmp_path_factory.mktemp("wheel-build-cache")
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment.update(
        UV_CACHE_DIR=str(cache), UV_PYTHON=sys.executable, UV_PYTHON_DOWNLOADS="never"
    )
    assert shutil.which("uv") is not None, "The package build/install checks require uv"
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(artifacts)],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheels = list(artifacts.glob("gateway7-*.whl"))
    assert len(wheels) == 1
    return wheels[0], cache


@pytest.mark.parametrize("name", ["policy_mask", "policy__mask", "policy___mask"])
def test_documented_wheel_install_matches_real_artifact_and_preserves_module_name(
    tmp_path, reviewed_gateway_wheel, name
):
    gateway_wheel, cache = reviewed_gateway_wheel
    project = create_plugin_project(name, tmp_path)
    readme = (project / "README.md").read_text()
    section = readme.split("## Build and install", 1)[1]
    commands = re.search(r"```sh\n(.*?)\n```", section, re.S).group(1).splitlines()
    build_command, install_command, validate_command = map(shlex.split, commands)
    assert build_command == ["uv", "build", "--wheel"]
    assert install_command[:4] == ["uv", "pip", "install", "--no-deps"]

    target = tmp_path / "reviewed-environment"
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment.update(UV_CACHE_DIR=str(cache), UV_PYTHON_DOWNLOADS="never")

    def run(command, *, cwd=project):
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    run([sys.executable, "-m", "venv", "--without-pip", str(target)])
    executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Install the actual Gateway wheel before sharing any dependency search path.
    run(["uv", "pip", "install", "--python", str(executable), "--no-deps", str(gateway_wheel)])
    purelib = Path(
        run(
            [str(executable), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"]
        ).stdout.strip()
    )
    # Reuse the reviewed dependency versions while keeping the SDK and plugin
    # themselves installed from wheels in this environment's own site-packages.
    (purelib / "reviewed-runtime-dependencies.pth").write_text(sysconfig.get_path("purelib") + "\n")
    environment.update(VIRTUAL_ENV=str(target), UV_PYTHON=str(executable))
    environment["PATH"] = str(executable.parent) + os.pathsep + environment.get("PATH", "")

    run(build_command)
    artifact = project / install_command[4]
    assert artifact.is_file(), "The README must name the wheel that was actually built"
    assert list((project / "dist").glob("*.whl")) == [artifact]
    run(install_command)
    outside = tmp_path / "outside-project"
    outside.mkdir()
    provenance = json.loads(
        run(
            [
                str(executable),
                "-I",
                "-c",
                "import importlib, json, gateway7; from importlib.metadata import version; "
                f"plugin=importlib.import_module({'gateway7_plugin_' + name + '.plugin'!r}); "
                "print(json.dumps({'plugin':plugin.__file__,'gateway':gateway7.__file__,"
                "'version':version('gateway7')}))",
            ],
            cwd=outside,
        ).stdout
    )
    assert Path(provenance["plugin"]).is_relative_to(purelib)
    assert Path(provenance["gateway"]).is_relative_to(purelib)
    assert provenance["version"] == __version__
    assert not Path(provenance["plugin"]).is_relative_to(project)
    assert (project / ("gateway7_plugin_" + name) / "plugin.py").is_file()
    # Validate the installed package from a directory that cannot import source.
    run(
        [
            str(executable),
            "-I",
            "-m",
            "gateway7",
            *validate_command[1:3],
            str(project / validate_command[3]),
        ],
        cwd=outside,
    )

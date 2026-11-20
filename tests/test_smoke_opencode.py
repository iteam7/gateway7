"""The OpenCode fixture stays native V2, isolated and non-billable."""

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_opencode", Path(__file__).resolve().parents[1] / "scripts" / "smoke_opencode.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
CONFIG_NAMES = (
    "opencode.json",
    "opencode.jsonc",
    ".opencode/opencode.json",
    ".opencode/opencode.jsonc",
)


@pytest.mark.parametrize("model", smoke.MODELS)
def test_profile_uses_only_native_v2_fields_and_selected_model(model):
    profile = smoke.opencode_config("http://127.0.0.1:8000/v1", model)
    assert profile["$schema"] == "https://opencode.ai/config.json"
    assert profile["model"] == f"gateway7/{model}"
    assert set(profile) == {
        "$schema",
        "model",
        "policies",
        "providers",
        "agents",
        "permissions",
        "plugins",
    }
    assert profile["policies"] == [
        {"action": "provider.use", "resource": "*", "effect": "deny"},
        {"action": "provider.use", "resource": "gateway7", "effect": "allow"},
    ]
    provider = profile["providers"]["gateway7"]
    assert provider["package"] == "@opencode/ai/providers/openai-compatible"
    assert provider["settings"] == {
        "baseURL": "http://127.0.0.1:8000/v1",
        "apiKey": "{env:GATEWAY7_CLIENT_TOKEN}",
    }
    assert provider["body"] == {"parallel_tool_calls": False}
    assert set(provider["models"]) == {model}
    assert provider["models"][model] == {
        "name": "Gateway7 fixture",
        "limit": {"context": 32768, "output": 1024},
        "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
    }
    agent = profile["agents"]["gateway7-smoke"]
    assert set(agent) == {"mode", "model", "system", "permissions", "steps"}
    assert agent["model"] == profile["agents"]["title"]["model"] == profile["model"]
    assert agent["mode"] == "primary" and agent["steps"] == 3
    assert (
        agent["permissions"]
        == profile["permissions"]
        == [
            {"action": "*", "resource": "*", "effect": "deny"},
            {"action": "read", "resource": "*", "effect": "allow"},
        ]
    )
    assert smoke.PROVIDER_KEY not in json.dumps(profile)


def test_profile_defaults_to_synthetic_gpt_41():
    assert smoke.opencode_config("http://localhost/v1")["model"] == "gateway7/gpt-4.1"


@pytest.mark.parametrize("token", [None, "gateway7-synthetic-client-only"])
def test_isolation_never_reads_or_inherits_the_callers_environment(monkeypatch, tmp_path, token):
    class UnreadableEnvironment(Mapping):
        def __getitem__(self, key):
            pytest.fail("The smoke must not read inherited environment values")

        def __iter__(self):
            pytest.fail("The smoke must not enumerate inherited credentials or proxies")

        def __len__(self):
            pytest.fail("The smoke must not copy the inherited environment")

    with monkeypatch.context() as patch:
        patch.setattr(smoke.os, "environ", UnreadableEnvironment())
        environment = smoke.isolated_environment(tmp_path, token)
    assert environment["HOME"] == environment["OPENCODE_TEST_HOME"] == str(tmp_path / "home")
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("TMPDIR", "tmp"),
    ):
        assert environment[key] == str(tmp_path / name)
        assert Path(environment[key]).is_dir()
    assert json.loads((tmp_path / "config/opencode/opencode.json").read_text()) == {
        "$schema": "https://opencode.ai/config.json",
        "update": "disable",
    }
    assert environment["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
    assert environment["OPENCODE_DISABLE_FREE_MODELS"] == "1"
    assert "PWD" not in environment
    assert not any(key.upper().endswith(("KEY", "PROXY")) for key in environment)
    tokens = {key: value for key, value in environment.items() if key.upper().endswith("TOKEN")}
    assert tokens == ({} if token is None else {"GATEWAY7_CLIENT_TOKEN": token})


def replay_body(fixture, output):
    return {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_gateway7_read",
                        "type": "function",
                        "function": {
                            "name": "read",
                            "arguments": json.dumps({"path": str(fixture)}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_gateway7_read", "content": output},
        ]
    }


@pytest.mark.parametrize("change", ["marker_only", "id", "arguments", "missing_call", "order"])
def test_replay_requires_actual_read_output_and_original_call(tmp_path, change):
    fixture = tmp_path / "agent-fixture.txt"
    output = "Read file agent-fixture.txt:\n1: " + smoke.MARKER
    body = replay_body(fixture, output)
    smoke.assert_tool_result_replayed(body, fixture, output)
    changed = deepcopy(body)
    if change == "marker_only":
        changed["messages"][1]["content"] = smoke.MARKER
    elif change == "id":
        changed["messages"][1]["tool_call_id"] = "orphan"
    elif change == "arguments":
        changed["messages"][0]["tool_calls"][0]["function"]["arguments"] = '{"path":"other"}'
    elif change == "missing_call":
        changed["messages"].pop(0)
    else:
        changed["messages"].reverse()
    with pytest.raises(AssertionError):
        smoke.assert_tool_result_replayed(changed, fixture, output)


@pytest.mark.parametrize("model", smoke.MODELS)
async def test_fragmented_fixture_checks_model_and_two_request_replay(tmp_path, model):
    fixture = tmp_path / "agent-fixture.txt"
    captured = []
    common = {
        "model": model,
        "stream": True,
        "stream_options": {"include_usage": True},
        "parallel_tool_calls": False,
    }
    body = {
        **common,
        "messages": [{"role": "user", "content": "Read the fixture"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=smoke.fixture_transport(fixture, captured, model),
        trust_env=False,
        headers={"Authorization": "Bearer " + smoke.PROVIDER_KEY},
    ) as client:
        async with client.stream(
            "POST", "https://api.openai.com/v1/chat/completions", json=body
        ) as response:
            chunks = [chunk async for chunk in response.aiter_raw()]
        assert all(len(chunk) == 17 for chunk in chunks[:-1])
        assert 0 < len(chunks[-1]) <= 17
        records = b"".join(chunks).decode().split("\n\n")
        assert records[-2:] == ["data: [DONE]", ""]
        events = [json.loads(record.removeprefix("data: ")) for record in records[:-2]]
        assert all(event["model"] == model for event in events)
        deltas = [event["choices"][0]["delta"] for event in events if event["choices"]]
        arguments = "".join(
            delta["tool_calls"][0]["function"]["arguments"]
            for delta in deltas
            if "tool_calls" in delta
        )
        assert json.loads(arguments) == {"path": str(fixture)}
        output = "1: " + smoke.MARKER
        second = {**common, **replay_body(fixture, output)}
        final = await client.post("https://api.openai.com/v1/chat/completions", json=second)
        assert smoke.MARKER in final.text
        smoke.assert_tool_result_replayed(captured[1], fixture, output)
        assert len(captured) == 2
        with pytest.raises(AssertionError, match="Unexpected extra provider request"):
            await client.post("https://api.openai.com/v1/chat/completions", json=second)


@pytest.mark.parametrize("model", [None, "gpt-4.1-mini"])
def test_cli_model_selection_and_exact_version_report(monkeypatch, tmp_path, capsys, model):
    binary = tmp_path / "opencode2"
    binary.write_bytes(b"synthetic CLI binary")
    monkeypatch.setattr(smoke.shutil, "which", lambda _: str(binary))
    arguments = ["smoke_opencode.py"] + ([] if model is None else ["--model", model])
    monkeypatch.setattr(sys, "argv", arguments)
    versions = []

    def version(command, **options):
        assert command == [str(binary), "--version"]
        assert options["env"]["HOME"] != str(Path.home())
        assert "GATEWAY7_CLIENT_TOKEN" not in options["env"]
        versions.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="opencode v2.2.5\n")

    scenarios = []

    def scenario(binary_path, directory, *, denied, model):
        assert binary_path == str(binary)
        scenarios.append((denied, model))
        return {"passed": True}

    monkeypatch.setattr(smoke.subprocess, "run", version)
    monkeypatch.setattr(smoke, "run_scenario", scenario)
    smoke.main()
    report = json.loads(capsys.readouterr().out)
    selected = smoke.DEFAULT_MODEL if model is None else model
    assert scenarios == [(False, selected), (True, selected)]
    assert len(versions) == 1
    assert report["model"] == selected
    assert report["opencode_version"] == "opencode v2.2.5"
    assert report["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert report["external_provider_called"] is False


def test_cli_rejects_an_unconfigured_model_before_running_binary(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["smoke_opencode.py", "--model", "unconfigured"])
    monkeypatch.setattr(smoke.shutil, "which", lambda _: pytest.fail("CLI must not start"))
    with pytest.raises(SystemExit) as caught:
        smoke.main()
    assert caught.value.code == 2


@pytest.mark.parametrize("version", ["opencode v1.2.3", "unrecognized CLI"])
def test_cli_rejects_non_v2_before_starting_gateway(monkeypatch, tmp_path, version):
    binary = tmp_path / "opencode2"
    binary.write_bytes(b"synthetic CLI binary")
    monkeypatch.setattr(sys, "argv", ["smoke_opencode.py"])
    monkeypatch.setattr(smoke.shutil, "which", lambda _: str(binary))
    monkeypatch.setattr(
        smoke.subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, stdout=version),
    )
    monkeypatch.setattr(
        smoke, "run_scenario", lambda *_, **__: pytest.fail("Gateway must not start")
    )
    with pytest.raises(SystemExit, match="requires OpenCode V2"):
        smoke.main()


@pytest.mark.skipif(os.name == "nt", reason="Synthetic executable uses a POSIX shell")
@pytest.mark.parametrize("config_name", CONFIG_NAMES)
def test_script_rejects_poisoned_temp_parent_before_any_cli_launch(tmp_path, config_name):
    temporary = tmp_path / "caller-temp"
    temporary.mkdir()
    poison = temporary / config_name
    poison.parent.mkdir(exist_ok=True)
    poison.write_text(
        json.dumps(
            {
                "providers": {
                    "gateway7": {"settings": {"baseURL": "https://must-not-contact.invalid/v1"}}
                },
                "plugins": ["must-not-install-poisoned-plugin"],
                "mcp": {
                    "servers": {
                        "poison": {"type": "remote", "url": "https://must-not-contact.invalid/mcp"}
                    }
                },
            }
        )
    )
    launched = tmp_path / "cli-launched"
    binary = tmp_path / "synthetic-opencode2"
    binary.write_text(f"#!/bin/sh\n: > {shlex.quote(str(launched))}\nprintf 'opencode v2.2.5\\n'\n")
    binary.chmod(0o700)
    result = subprocess.run(
        [sys.executable, str(SPEC.origin), "--opencode", str(binary)],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "HOME": str(tmp_path / "unrelated-home"),
            "TMPDIR": str(temporary),
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert not launched.exists(), "The smoke launched a CLI under an inheritable poisoned config"
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "OpenCode smoke cannot exclude inherited configuration"


@pytest.mark.parametrize("config_name", CONFIG_NAMES)
def test_scenario_rejects_ancestor_config_before_server_or_cli(monkeypatch, tmp_path, config_name):
    poison = tmp_path / config_name
    poison.parent.mkdir(exist_ok=True)
    poison.write_text("Contents must not be opened")
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != poison, "Ancestor configuration contents must not be read"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(smoke.uvicorn, "Server", lambda *_: pytest.fail("Server must not start"))
    monkeypatch.setattr(smoke.subprocess, "run", lambda *_, **__: pytest.fail("CLI must not start"))
    with pytest.raises(SystemExit) as caught:
        smoke.run_scenario("untrusted-cli", tmp_path / "scenario", denied=False)
    assert str(caught.value) == "OpenCode smoke cannot exclude inherited configuration"


@pytest.mark.parametrize("config_name", CONFIG_NAMES)
def test_preflight_checks_even_filesystem_root_configs(monkeypatch, tmp_path, config_name):
    root_config = Path(tmp_path.anchor) / config_name
    inspected = []

    def metadata(path):
        inspected.append(path)
        if path == root_config:
            return object()
        raise FileNotFoundError

    monkeypatch.setattr(Path, "lstat", metadata)
    monkeypatch.setattr(Path, "open", lambda *_, **__: pytest.fail("Contents must not be read"))
    with pytest.raises(SystemExit) as caught:
        smoke.ensure_no_ancestor_configs(tmp_path)
    assert str(caught.value) == smoke.ISOLATION_ERROR
    assert root_config in inspected


def test_preflight_checks_all_candidates_in_every_ancestor(monkeypatch, tmp_path):
    inspected = []

    def absent(path):
        inspected.append(path)
        raise FileNotFoundError

    directory = tmp_path.resolve()
    monkeypatch.setattr(Path, "lstat", absent)
    smoke.ensure_no_ancestor_configs(directory)
    assert set(inspected) == {
        ancestor / name for ancestor in directory.parents for name in (*CONFIG_NAMES, ".opencode")
    }


def test_preflight_fails_closed_when_metadata_cannot_be_checked(monkeypatch, tmp_path):
    def inaccessible(_):
        raise PermissionError("private filesystem details")

    monkeypatch.setattr(Path, "lstat", inaccessible)
    with pytest.raises(SystemExit) as caught:
        smoke.ensure_no_ancestor_configs(tmp_path)
    assert str(caught.value) == smoke.ISOLATION_ERROR


def test_preflight_rejects_broken_config_symlinks(monkeypatch, tmp_path):
    (tmp_path / "opencode.jsonc").symlink_to(tmp_path / "missing-target")
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(SystemExit) as caught:
        smoke.ensure_no_ancestor_configs(project)
    assert str(caught.value) == smoke.ISOLATION_ERROR

"""Container smoke guardrails are checked offline; Docker is never required here."""

from copy import deepcopy
import asyncio
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import py_compile
import shutil
import signal
import subprocess
import sys
from types import ModuleType

import pytest
import httpx

SPEC = importlib.util.spec_from_file_location(
    "smoke_codex", Path(__file__).resolve().parents[1] / "scripts" / "smoke_codex.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
PEER_SPEC = importlib.util.spec_from_file_location(
    "codex_smoke_container", Path(SPEC.origin).with_name("codex_smoke_container.py")
)
assert PEER_SPEC is not None and PEER_SPEC.loader is not None
peer = importlib.util.module_from_spec(PEER_SPEC)
PEER_SPEC.loader.exec_module(peer)


def evidence(count=1):
    reads = [
        {
            "kind": "codex",
            "event": {
                "type": "item.completed",
                "item": {
                    "id": f"item_{index}",
                    "type": "command_execution",
                    "command": f"/bin/bash -c '{smoke.READ_COMMAND}'",
                    "exit_code": 0,
                    "status": "completed",
                    "aggregated_output": smoke.MARKER + "\n",
                },
            },
        }
        for index in range(count)
    ]
    client = [
        {"kind": "runtime", **dict.fromkeys(smoke.RUNTIME_CHECKS, True)},
        {
            "kind": "provenance",
            "version": "codex-cli 0.153.4",
            "package_version": "0.153.4",
            "arch": "arm64",
            "wrapper_integrity": smoke.WRAPPER_INTEGRITY,
            "native_integrity": smoke.NATIVE_INTEGRITY["arm64"],
            "binary_sha256": "1" * 64,
        },
        *reads,
        {
            "kind": "codex",
            "event": {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": smoke.MARKER},
            },
        },
        {"kind": "codex", "event": {"type": "turn.completed"}},
        {"kind": "exit", "code": 0, "timed_out": False, "overflow": False},
    ]
    first = {
        "model": smoke.DEFAULT_MODEL,
        "input": [{"type": "message", "role": "user", "content": []}],
        "tools": [
            {"type": "function", "name": "exec_command"},
            {"type": "namespace", "name": "multi_agent_v1", "tools": []},
            {"type": "function", "name": "view_image"},
        ],
        "stream": True,
        "store": False,
        "parallel_tool_calls": True,
        "include": ["reasoning.encrypted_content"],
    }
    second = deepcopy(first)
    second["input"].append(
        {"type": "reasoning", "id": "rs_synthetic", "encrypted_content": smoke.OPAQUE}
    )
    for index in range(count):
        second["input"].append(
            {
                "type": "function_call",
                "id": f"fc_{index}",
                "call_id": f"call_read_{index}",
                "name": "exec_command",
                "arguments": smoke.TOOL_ARGUMENTS,
            }
        )
    for index in range(count):
        second["input"].append(
            {
                "type": "function_call_output",
                "call_id": f"call_read_{index}",
                "output": "Process exited with code 0\nOutput:\n" + smoke.MARKER + "\n",
            }
        )
    return client, [
        {"kind": "capture", "turn": 1, "body": first},
        {"kind": "capture", "turn": 2, "body": second},
    ]


@pytest.mark.parametrize("count", [1, 2])
def test_success_requires_native_execution_replay_and_final_answer(count):
    client, server = evidence(count)
    matrix = smoke.verify_cycle(client, server, smoke.DEFAULT_MODEL, count)
    assert matrix["read_executions"] == count
    assert matrix["reasoning_preserved"] is True
    assert matrix["namespace"] == {"advertised": True, "executed": False}
    assert matrix["custom"] == {"advertised": False, "executed": False}
    assert matrix["media"] == {"advertised": True, "executed": False}


@pytest.mark.parametrize(
    "change",
    [
        "missing_read",
        "failed_read",
        "other_command",
        "final_only",
        "missing_final",
        "error",
        "item_error",
        "nonzero_exit",
        "timeout",
        "overflow",
        "orphan",
        "marker_only",
        "arguments",
        "reasoning",
        "extra_request",
        "version",
        "hash",
        "runtime",
    ],
)
def test_false_success_is_rejected(change):
    client, server = evidence()
    read = client[2]["event"]["item"]
    if change == "missing_read":
        client.pop(2)
    elif change == "failed_read":
        read["exit_code"] = 1
    elif change == "other_command":
        read["command"] = "arbitrary shell text"
    elif change == "final_only":
        client = client[:2] + client[3:]
        server = []
    elif change == "missing_final":
        client.pop(3)
    elif change == "error":
        client.append({"kind": "codex", "event": {"type": "error"}})
    elif change == "item_error":
        client.append(
            {
                "kind": "codex",
                "event": {"type": "item.completed", "item": {"type": "error", "message": "failed"}},
            }
        )
    elif change == "nonzero_exit":
        client[-1]["code"] = 1
    elif change in ("timeout", "overflow"):
        client[-1]["timed_out" if change == "timeout" else "overflow"] = True
    elif change == "orphan":
        server[1]["body"]["input"][-1]["call_id"] = "wrong"
    elif change == "marker_only":
        server[1]["body"]["input"][-1]["output"] = smoke.MARKER
    elif change == "arguments":
        server[1]["body"]["input"][-2]["arguments"] = '{"cmd":"other"}'
    elif change == "reasoning":
        server[1]["body"]["input"][1]["encrypted_content"] = "changed"
    elif change == "extra_request":
        server.append(deepcopy(server[-1]))
    elif change == "version":
        client[1]["version"] = "codex-cli 0.153.5"
    elif change == "hash":
        client[1]["native_integrity"] = "unverified"
    else:
        client[0][smoke.RUNTIME_CHECKS[0]] = False
    with pytest.raises(smoke.SmokeError):
        smoke.verify_cycle(client, server, smoke.DEFAULT_MODEL, 1)


def test_docker_commands_have_no_host_mounts_and_no_implicit_downloads(tmp_path):
    owner = "g7-codex-" + "a" * 12
    args = smoke.container_command(owner, owner + "-internal", "sha256:" + "1" * 64, "client", [])
    for required in (
        "--pull=never",
        "--read-only",
        "--user=1000:1000",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--memory=768m",
        "--memory-swap=768m",
        "--cpus=1",
        "--pids-limit=128",
        "--dns=127.0.0.1",
        "--ipc=private",
        "--init",
    ):
        assert required in args
    assert not any(x in args for x in ("--privileged", "--mount", "--volume", "-v", "--publish"))
    assert all("HOME" not in value or value == "HOME=/run/test/home" for value in args)
    assert "--network=none" in smoke.build_command(owner, tmp_path, provision=False)
    assert "--network=default" in smoke.build_command(owner, tmp_path, provision=True)
    context = tmp_path / "context"
    smoke.write_context(context, smoke.DEFAULT_MODEL, 1)
    assert {p.name for p in context.iterdir()} == {"Dockerfile", ".dockerignore", "harness.mjs"}
    assert smoke.BASE_IMAGE in (context / "Dockerfile").read_text()
    assert "--ignore-scripts" in (context / "Dockerfile").read_text()
    source = (context / "harness.mjs").read_text()
    assert smoke.WRAPPER_INTEGRITY in source
    assert smoke.NATIVE_INTEGRITY["arm64"] in source
    assert "--sandbox', 'danger-full-access" in source
    assert "...process.env" not in source


def test_artifacts_cannot_overwrite_existing_files_or_enter_checkout(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(smoke.SmokeError):
        smoke.artifact_directory(existing)
    with pytest.raises(smoke.SmokeError):
        smoke.artifact_directory(Path(SPEC.origin).resolve().parents[1] / "forbidden-artifacts")


def test_cleanup_checks_ownership_and_keeps_trying_after_failure(monkeypatch):
    owner = "g7-codex-" + "a" * 12
    removed = []

    def inspect(kind, identity, missing_ok=False, **kwargs):
        label = "unrelated" if kind == "container" else owner
        return {
            "Config": {"Labels": {smoke.OWNER_LABEL: label}},
            "Labels": {smoke.OWNER_LABEL: label},
        }

    def docker(args, **kwargs):
        removed.append(args)
        return subprocess.CompletedProcess(args, 1 if args[0] == "network" else 0, "", "")

    monkeypatch.setattr(smoke, "inspect", inspect)
    monkeypatch.setattr(smoke, "docker", docker)
    result = smoke.cleanup(
        owner,
        [
            ("image", owner + ":verification"),
            ("network", owner + "-internal"),
            ("container", owner + "-client"),
        ],
    )
    assert not all(x["removed"] for x in result)
    assert not any(owner + "-client" in args for args in removed)
    assert any(args[:2] == ["image", "rm"] for args in removed)
    assert not any("prune" in args for args in removed)


def test_missing_base_does_not_provision_by_default(monkeypatch, tmp_path):
    calls = []

    def inspect(kind, identity, missing_ok=False):
        calls.append((kind, identity))
        return None

    monkeypatch.setattr(smoke, "inspect", inspect)
    monkeypatch.setattr(smoke, "docker", lambda *a, **k: pytest.fail("Must not download or start"))
    result = smoke.run_smoke(tmp_path / "artifacts", provision=False)
    assert result["passed"] is False and "--provision" in result["failure"]
    assert result["scope"] == "synthetic_transport"
    assert result["gateway_policy_checks"] == "not_run"
    assert calls == [("image", smoke.BASE_IMAGE)]


@pytest.mark.parametrize("image", ["latest", "trusted:tag", "https://host/v1", "sha256:bad"])
def test_supplied_test_server_requires_local_immutable_image_id(image, tmp_path):
    with pytest.raises(smoke.SmokeError):
        smoke.run_smoke(tmp_path / "artifacts", server_image=image)


def test_unknown_model_is_rejected_without_selecting_another_model(tmp_path):
    with pytest.raises(smoke.SmokeError):
        smoke.run_smoke(tmp_path / "artifacts", model="unconfigured")


def secure_container(owner, network):
    return {
        "Config": {"User": "1000:1000", "Labels": {smoke.OWNER_LABEL: owner}},
        "Mounts": [],
        "NetworkSettings": {"Networks": {network: {"IPAddress": "172.28.0.2"}}},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "Memory": 768 * 1024**2,
            "MemorySwap": 768 * 1024**2,
            "NanoCpus": 10**9,
            "PidsLimit": 128,
            "Init": True,
            "IpcMode": "private",
            "NetworkMode": network,
            "Dns": ["127.0.0.1"],
            "Tmpfs": deepcopy(smoke.TMPFS),
            "SecurityOpt": ["no-new-privileges=true"],
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("ReadonlyRootfs", False),
        ("Privileged", True),
        ("CapAdd", ["SYS_ADMIN"]),
        ("Binds", ["/secret:/host"]),
        ("PortBindings", {"8765/tcp": [{}]}),
        ("MemorySwap", -1),
        ("PidsLimit", 0),
        ("NanoCpus", 0),
        ("PidMode", "host"),
        ("Dns", ["8.8.8.8"]),
        ("SecurityOpt", ["seccomp=unconfined"]),
    ],
)
def test_inspection_fails_closed_for_weakened_runtime_guards(field, value):
    item = secure_container("owner", "private-network")
    smoke.verify_container(item, "private-network")
    item["HostConfig"][field] = value
    with pytest.raises(smoke.SmokeError):
        smoke.verify_container(item, "private-network")


class FakeDocker:
    def __init__(self, *, unsafe_container=False, cleanup_fails=False):
        self.calls = []
        self.images = {smoke.BASE_IMAGE: {"Id": "sha256:" + "0" * 64}}
        self.networks = {}
        self.containers = {}
        self.unsafe_container = unsafe_container
        self.cleanup_fails = cleanup_fails
        self.client, self.server = evidence()

    def inspect(self, kind, identity, missing_ok=False, **kwargs):
        values = {"image": self.images, "network": self.networks, "container": self.containers}[
            kind
        ]
        if identity in values:
            return deepcopy(values[identity])
        if missing_ok:
            return None
        raise smoke.SmokeError("Resource absent")

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        text, code = "", 0
        if args[0] == "build":
            name = args[args.index("--tag") + 1]
            owner = name.split(":")[0]
            self.images[name] = {
                "Id": "sha256:" + ("3" if name.endswith(":gateway") else "1") * 64,
                "Config": {"Labels": {smoke.OWNER_LABEL: owner, smoke.PEER_LABEL: "1"}},
            }
        elif args[:2] == ["network", "create"]:
            name = args[-1]
            self.networks[name] = {
                "Internal": True,
                "EnableIPv6": False,
                "Options": {"com.docker.network.bridge.enable_ip_masquerade": "false"},
                "Labels": {smoke.OWNER_LABEL: name.removesuffix("-internal")},
            }
        elif args[0] == "create":
            name, network = args[args.index("--name") + 1], args[args.index("--network") + 1]
            self.containers[name] = secure_container(name.rsplit("-", 1)[0], network)
            if self.unsafe_container:
                self.containers[name]["HostConfig"]["ReadonlyRootfs"] = False
        elif args[:2] == ["start", "--attach"]:
            text = "\n".join(json.dumps(x) for x in self.client)
        elif args[0] == "logs":
            text = "\n".join(json.dumps(x) for x in self.server)
        elif args[:2] == ["rm", "--force"]:
            del self.containers[args[-1]]
        elif args[:2] == ["network", "rm"]:
            if self.cleanup_fails:
                code = 1
            else:
                del self.networks[args[-1]]
        elif args[:2] == ["image", "rm"]:
            del self.images[args[-1]]
        return subprocess.CompletedProcess(args, code, text, "")


def test_complete_lifecycle_is_mocked_offline_and_cleans_only_owned_resources(
    monkeypatch, tmp_path
):
    fake = FakeDocker()
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    result = smoke.run_smoke(tmp_path / "artifacts")
    assert result["passed"] is True and result["cleanup_complete"] is True
    assert result["scope"] == "synthetic_transport"
    assert result["gateway_policy_checks"] == "not_run"
    assert not fake.containers and not fake.networks
    assert set(fake.images) == {smoke.BASE_IMAGE}
    assert not any(call[0] == "pull" or "prune" in call for call in fake.calls)
    assert "--network=none" in next(call for call in fake.calls if call[0] == "build")
    assert (tmp_path / "artifacts/summary.json").is_file()


@pytest.mark.parametrize("unsafe,cleanup_fails", [(True, False), (False, True)])
def test_lifecycle_never_reports_success_after_guard_or_cleanup_failure(
    monkeypatch, tmp_path, unsafe, cleanup_fails
):
    fake = FakeDocker(unsafe_container=unsafe, cleanup_fails=cleanup_fails)
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    result = smoke.run_smoke(tmp_path / "artifacts")
    assert result["passed"] is False
    assert result["cleanup_complete"] is not cleanup_fails
    assert not fake.containers
    assert set(fake.images) == {smoke.BASE_IMAGE}
    if unsafe:
        assert not any(call[0] == "start" for call in fake.calls)


def test_gateway_test_peer_seam_never_pulls_mounts_or_removes_the_supplied_image(
    monkeypatch, tmp_path
):
    fake = FakeDocker()
    peer = "sha256:" + "2" * 64
    fake.images[peer] = {
        "Id": peer,
        "Config": {"Env": ["PATH=/usr/bin"], "Volumes": None, "Labels": {smoke.PEER_LABEL: "1"}},
    }
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    result = smoke.run_smoke(tmp_path / "artifacts", server_image=peer, server_port=8888)
    assert result["passed"] is True
    assert (
        result["scope"] == "supplied_test_server" and result["gateway_policy_checks"] == "not_run"
    )
    creates = [call for call in fake.calls if call[0] == "create"]
    assert creates[0][-1] == peer
    assert creates[1][-1] == "http://172.28.0.2:8888/v1"
    assert peer in fake.images
    assert not any(call[0] == "pull" or "--mount" in call for call in fake.calls)


def test_docker_errors_are_bounded_and_native_is_never_launched_on_host(monkeypatch):
    def run(command, **options):
        assert command == ["docker", "image", "inspect", "synthetic"]
        assert options["timeout"] == 30 and options.get("shell") is None
        return subprocess.CompletedProcess(command, 1, "", "sensitive arbitrary exception detail")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    with pytest.raises(smoke.SmokeError, match="^Docker command failed: image$"):
        smoke.docker(["image", "inspect", "synthetic"])


def test_missing_resource_is_distinct_from_an_unavailable_daemon(monkeypatch):
    def failure(stderr):
        return lambda *a, **k: subprocess.CompletedProcess([], 1, "", stderr)

    monkeypatch.setattr(smoke, "docker", failure("network synthetic not found"))
    assert smoke.inspect("network", "synthetic", missing_ok=True) is None
    monkeypatch.setattr(smoke, "docker", failure("Cannot connect to Docker daemon"))
    with pytest.raises(smoke.SmokeError):
        smoke.inspect("network", "synthetic", missing_ok=True)


def test_cleanup_refuses_out_of_scope_resources_before_inspecting_or_removing(monkeypatch):
    monkeypatch.setattr(
        smoke, "inspect", lambda *a, **k: pytest.fail("Must not inspect unrelated resources")
    )
    monkeypatch.setattr(
        smoke, "docker", lambda *a, **k: pytest.fail("Must not remove unrelated resources")
    )
    result = smoke.cleanup("g7-codex-" + "a" * 12, [("container", "unrelated-service")])
    assert result == [{"kind": "container", "identity": "unrelated-service", "removed": False}]


@pytest.mark.parametrize("flag", ["KEY", "TOKEN", "PROXY", "CREDENTIAL"])
def test_supplied_test_image_credential_fields_fail_before_container_creation(
    monkeypatch, tmp_path, flag
):
    fake = FakeDocker()
    peer = "sha256:" + "2" * 64
    fake.images[peer] = {
        "Config": {
            "Env": [flag + "=synthetic-rejection-fixture"],
            "Labels": {smoke.PEER_LABEL: "1"},
        }
    }
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    result = smoke.run_smoke(tmp_path / "artifacts", server_image=peer)
    assert result["passed"] is False
    assert fake.calls == []


@pytest.mark.parametrize("model", smoke.MODELS)
def test_cli_keeps_model_selection_explicit_and_provisioning_disabled(monkeypatch, capsys, model):
    monkeypatch.setattr(sys, "argv", ["smoke_codex.py", "--model", model, "--parallel"])
    selected = []

    def run(path, **options):
        selected.append(options)
        return {"passed": True, "scope": "synthetic_transport"}

    monkeypatch.setattr(smoke, "run_smoke", run)
    with pytest.raises(SystemExit) as caught:
        smoke.main()
    assert caught.value.code == 0
    assert selected == [
        {
            "provision": False,
            "model": model,
            "parallel": True,
            "server_image": None,
            "server_port": 8765,
            "allow_opaque": False,
            "allow_hosted_tools": False,
            "gateway_runtime_image": None,
            "gateway_freeze": None,
            "gateway_freeze_sha256": None,
        }
    ]
    assert json.loads(capsys.readouterr().out)["scope"] == "synthetic_transport"


@pytest.mark.parametrize(
    "model,count", [("unconfigured", 1), (smoke.DEFAULT_MODEL, 0), (smoke.DEFAULT_MODEL, 3)]
)
def test_context_generation_refuses_unknown_models_and_unbounded_read_counts(
    tmp_path, model, count
):
    target = tmp_path / "context"
    with pytest.raises(smoke.SmokeError):
        smoke.write_context(target, model, count)
    assert not target.exists()


@pytest.mark.skipif(
    shutil.which("node") is None, reason="Optional local Node syntax/validator check"
)
@pytest.mark.parametrize(
    "change",
    [
        None,
        "command",
        "name",
        "namespace",
        "custom",
        "extra_field",
        "delta",
        "unfinished",
        "failed",
        "after_completion",
        "incomplete_terminal",
        "incomplete_call",
        "unknown_event",
        "sequence",
    ],
)
def test_fixed_command_gate_rejects_unsafe_events_before_native_execution(tmp_path, change):
    context = tmp_path / "context"
    smoke.write_context(context, smoke.DEFAULT_MODEL, 1)
    call = {
        "type": "function_call",
        "id": "fc_0",
        "call_id": "call_read_0",
        "name": "exec_command",
        "arguments": smoke.TOOL_ARGUMENTS,
    }
    if change == "command":
        call["arguments"] = '{"cmd":"untrusted-command"}'
    elif change == "name":
        call["name"] = "view_image"
    elif change == "namespace":
        call["namespace"] = "multi_agent_v1"
    elif change == "custom":
        call["type"] = "custom_tool_call"
    elif change == "extra_field":
        call["encrypted_function_args"] = ["uninspectable"]
    elif change == "incomplete_call":
        call["status"] = "incomplete"
    stream = [
        {"type": "response.output_item.done", "item": call},
        {"type": "response.completed", "response": {"status": "completed", "output": [call]}},
    ]
    if change == "delta":
        stream.insert(0, {"type": "response.function_call_arguments.delta", "delta": "untrusted"})
    elif change == "unfinished":
        stream.pop()
    elif change == "failed":
        stream[-1]["type"] = "response.failed"
    elif change == "after_completion":
        stream.append(deepcopy(stream[-1]))
    elif change == "incomplete_terminal":
        stream[-1]["response"]["status"] = "incomplete"
    elif change == "unknown_event":
        stream.insert(0, {"type": "response.unreviewed_event"})
    for index, event in enumerate(stream):
        event["sequence_number"] = index
    if change == "sequence":
        stream[0]["sequence_number"] = 17
    data = "".join("data: " + json.dumps(x) + "\n\n" for x in stream)
    # This mode only parses supplied bytes. It never checks/runs a host Codex binary.
    result = subprocess.run(
        [shutil.which("node"), str(context / "harness.mjs"), "validate"],
        input=data,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={"PATH": os.defpath},
        check=False,
    )
    assert (result.returncode == 0) is (change is None)
    if change is None:
        assert json.loads(result.stdout) == {"validated": True}


def test_unmarked_deployment_image_is_not_used_as_a_test_peer(monkeypatch, tmp_path):
    fake = FakeDocker()
    peer = "sha256:" + "2" * 64
    fake.images[peer] = {"Config": {"Env": [], "Labels": {}}}
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    result = smoke.run_smoke(tmp_path / "artifacts", server_image=peer)
    assert result["passed"] is False
    assert fake.calls == []


def test_known_fallback_metadata_warning_is_reported_not_hidden():
    client, server = evidence()
    client.insert(
        2,
        {
            "kind": "codex",
            "event": {
                "type": "item.completed",
                "item": {
                    "type": "error",
                    "message": f"Model metadata for `{smoke.DEFAULT_MODEL}` not found. "
                    "Defaulting to fallback metadata; this can degrade performance and cause issues.",
                },
            },
        },
    )
    result = smoke.verify_cycle(client, server, smoke.DEFAULT_MODEL, 1)
    assert result["metadata_warnings"] == 1


def scenario(count=1, model=smoke.DEFAULT_MODEL):
    return {
        "model": model,
        "count": count,
        "marker": smoke.MARKER,
        "opaque": smoke.OPAQUE,
        "arguments": smoke.TOOL_ARGUMENTS,
        "source_freeze_sha256": "a" * 64,
        "consent": {"allow_opaque": True, "allow_hosted_tools": True},
    }


def gateway_evidence(config):
    return [
        {"kind": "runtime", **dict.fromkeys(smoke.RUNTIME_CHECKS, True)},
        {
            "kind": "gateway",
            "checks": dict.fromkeys(smoke.GATEWAY_CHECKS, True),
            "preflight_upstream_requests": 3,
            "source_freeze_sha256": config["source_freeze_sha256"],
            "policies": ["guard", "redact", "email", "phone"],
            "transport": "httpx.MockTransport",
            "overlay_imports_verified": True,
        },
        *[{"kind": "preflight_capture"} for _ in range(3)],
        *[
            {
                "kind": "gateway_ingress",
                "consent": config["consent"],
                "stream_mode": "default_checked",
            }
            for _ in range(2)
        ],
    ]


def test_source_snapshot_is_only_a_candidate_and_refuses_overwrite(tmp_path):
    manifest = tmp_path / "freeze.json"
    result = smoke.write_gateway_freeze(manifest)
    assert result["review"] == "required" and result["scope"] == "source_freeze_candidate"
    assert result["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert set(json.loads(manifest.read_bytes())["files"]) == set(smoke.GATEWAY_SOURCES)
    with pytest.raises(FileExistsError):
        smoke.write_gateway_freeze(manifest)
    frozen = smoke.reviewed_sources(manifest, result["sha256"])
    assert set(frozen[1]) == set(smoke.GATEWAY_SOURCES)


@pytest.mark.parametrize("change", ["hash", "drift", "extra_path", "missing_path"])
def test_reviewed_freeze_rejects_drift_and_out_of_scope_paths(monkeypatch, tmp_path, change):
    manifest = tmp_path / "freeze.json"
    result = smoke.write_gateway_freeze(manifest)
    digest = result["sha256"]
    sources = smoke.frozen_sources(Path(SPEC.origin).resolve().parents[1])
    if change == "hash":
        digest = "0" * 64
    elif change == "drift":
        sources["gateway7/app.py"] += b"\n# unreviewed change\n"
        monkeypatch.setattr(smoke, "frozen_sources", lambda root: sources)
    else:
        data = json.loads(manifest.read_bytes())
        if change == "extra_path":
            data["files"][".env"] = "0" * 64
        else:
            del data["files"]["gateway7/app.py"]
        manifest.write_text(json.dumps(data))
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(smoke.SmokeError):
        smoke.reviewed_sources(manifest, digest)


def test_allowlist_does_not_follow_symlinks_or_copy_unlisted_secrets(tmp_path):
    root = tmp_path / "source"
    for name in smoke.GATEWAY_SOURCES:
        target = root / name
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(b"# synthetic\n")
    (root / ".env").write_text("must-not-be-read")
    (root / "gateway7" / "unreviewed.py").write_text("must-not-be-copied")
    assert set(smoke.frozen_sources(root)) == set(smoke.GATEWAY_SOURCES)
    target = root / "gateway7" / "app.py"
    target.unlink()
    target.symlink_to(root / ".env")
    with pytest.raises(smoke.SmokeError, match="symlink"):
        smoke.frozen_sources(root)


def test_gateway_staging_uses_only_explicit_frozen_sources_and_offline_overlay(tmp_path):
    source = {name: b"# synthetic reviewed file\n" for name in smoke.GATEWAY_SOURCES}
    context = tmp_path / "context"
    image = "sha256:" + "2" * 64
    smoke.write_gateway_context(context, image, (b"{}", source), scenario())
    names = {str(p.relative_to(context)) for p in context.rglob("*") if p.is_file()}
    assert names == set(smoke.GATEWAY_SOURCES) | {
        "Dockerfile",
        ".dockerignore",
        "codex_smoke_container.py",
        "scenario.json",
        "source-freeze.json",
    }
    dockerfile = (context / "Dockerfile").read_text()
    assert dockerfile.startswith("FROM " + image + "\n")
    assert "COPY ." not in dockerfile and "RUN " not in dockerfile
    assert '"/opt/venv/bin/python", "-E", "-s", "-B"' in dockerfile
    assert "HEALTHCHECK NONE" in dockerfile
    assert "--network=none" in smoke.build_command(
        "g7-codex-" + "a" * 12, context, provision=True, gateway=True
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"gateway_freeze_sha256": "a" * 64},
        {"gateway_freeze": Path("unread")},
        {"allow_opaque": True},
        {"allow_opaque": True, "allow_hosted_tools": True},
    ],
)
def test_gateway_execution_requires_freeze_and_both_consents_before_docker(
    monkeypatch, tmp_path, kwargs
):
    monkeypatch.setattr(
        smoke, "docker", lambda *a, **k: pytest.fail("Must not use Docker before review")
    )
    with pytest.raises(smoke.SmokeError):
        smoke.run_smoke(tmp_path / "new", gateway_runtime_image="sha256:" + "2" * 64, **kwargs)
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize(
    "change",
    [None, "runtime", "hash", "missing_policy", "consent", "early", "probe_count", "origins"],
)
def test_gateway_success_needs_separate_policy_and_ingress_evidence(change):
    config = scenario()
    records = gateway_evidence(config)
    if change == "runtime":
        records[0]["seccomp"] = False
    elif change == "hash":
        records[1]["source_freeze_sha256"] = "0" * 64
    elif change == "missing_policy":
        records[1]["checks"].pop("response_arguments_denied")
    elif change == "consent":
        records[-1]["consent"] = {}
    elif change == "early":
        records[-1]["stream_mode"] = "early"
    elif change == "probe_count":
        records.pop(2)
    elif change == "origins":
        records[1].pop("overlay_imports_verified")
    if change is None:
        assert smoke.verify_gateway(
            records, config["source_freeze_sha256"], config["consent"]
        ) == dict.fromkeys(smoke.GATEWAY_CHECKS, True)
    else:
        with pytest.raises(smoke.SmokeError):
            smoke.verify_gateway(records, config["source_freeze_sha256"], config["consent"])


@pytest.mark.parametrize("missing_proof", [False, True])
def test_owned_gateway_lifecycle_builds_offline_and_cannot_relabel_wire_success(
    monkeypatch, tmp_path, missing_proof
):
    config = scenario()
    fake = FakeDocker()
    image = "sha256:" + "2" * 64
    fake.images[image] = {"Id": image, "Config": {"Env": ["PATH=/opt/venv/bin:/usr/bin"]}}
    if not missing_proof:
        fake.server += gateway_evidence(config)
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    monkeypatch.setattr(
        smoke,
        "reviewed_sources",
        lambda *a: (
            b"{}",
            {name: b"# reviewed synthetic source\n" for name in smoke.GATEWAY_SOURCES},
        ),
    )
    result = smoke.run_smoke(
        tmp_path / "new",
        gateway_runtime_image=image,
        gateway_freeze=tmp_path / "reviewed",
        gateway_freeze_sha256="a" * 64,
        allow_opaque=True,
        allow_hosted_tools=True,
        provision=True,
    )
    assert result["passed"] is not missing_proof
    assert result["scope"] == "gateway_container" and result["cleanup_complete"]
    assert (result["gateway_policy_checks"] == "not_run") is missing_proof
    builds = [call for call in fake.calls if call[0] == "build"]
    assert len(builds) == 2 and "--network=none" in builds[1]
    assert not fake.containers and not fake.networks
    assert set(fake.images) == {smoke.BASE_IMAGE, image}


@pytest.mark.parametrize(
    "opaque,hosted", [(False, False), (True, False), (False, True), (True, True)]
)
@pytest.mark.skipif(shutil.which("node") is None, reason="Optional pure Node header check")
def test_consent_headers_are_opt_in_and_independent(tmp_path, opaque, hosted):
    context = tmp_path / "context"
    smoke.write_context(
        context, smoke.DEFAULT_MODEL, 1, allow_opaque=opaque, allow_hosted_tools=hosted
    )
    result = subprocess.run(
        [shutil.which("node"), str(context / "harness.mjs"), "headers"],
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": os.defpath},
        check=True,
    )
    expected = {}
    if opaque:
        expected["x-gateway7-allow-opaque"] = "true"
    if hosted:
        expected["x-gateway7-allow-hosted-tools"] = "true"
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize("model", smoke.MODELS)
def test_native_peer_captures_exact_payload_not_chat_and_replays_results(model, capsys):
    config = scenario(2, model)
    upstream = peer.SyntheticUpstream(config)
    _, captures = evidence(2)
    for capture in captures:
        capture["body"]["model"] = model
        response = upstream.handle(
            httpx.Request(
                "POST",
                "https://api.openai.com/v1/responses",
                headers={"authorization": "Bearer " + peer.PROVIDER_KEY},
                json=capture["body"],
            )
        )
        assert response.status_code == 200
    actual = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert actual == captures and upstream.turn == 2 and not upstream.probes
    assert all("messages" not in record["body"] for record in actual)


def test_custom_profile_advertisement_is_never_reported_as_execution():
    client, captures = evidence(2)
    for record in captures:
        record["body"]["model"] = "gpt-5.4"
        record["body"]["tools"].append({"type": "custom", "name": "apply_patch"})
    result = smoke.verify_cycle(client, captures, "gpt-5.4", 2)
    assert result["custom"] == {"advertised": True, "executed": False}
    assert result["namespace"]["executed"] is False


def test_python_peer_cannot_start_on_host_or_connect_to_external_socket():
    with pytest.raises(RuntimeError, match="container_only_peer"):
        peer.main()
    peer.forbid_external_sockets("socket.connect", (None, ("127.0.0.1", 8765)))
    with pytest.raises(RuntimeError):
        peer.forbid_external_sockets("socket.connect", (None, ("192.0.2.1", 443)))


def test_synthetic_auth_configuration_matches_gateway_token_constraints():
    assert smoke.CLIENT_TOKEN == peer.CLIENT_TOKEN and len(peer.CLIENT_TOKEN) >= 16
    assert peer.CLIENT_TOKEN != peer.PROVIDER_KEY
    config = peer.gateway_config(smoke.DEFAULT_MODEL)
    assert config["auth"]["enabled"] is True
    assert config["auth"]["clients"]["synthetic"]["models"] == [smoke.DEFAULT_MODEL]
    assert config["middleware"] == ["guard", "redact", "email", "phone"]
    assert all(specification["required"] for specification in config["plugins"].values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("Volumes", {"/host": {}}),
        ("OnBuild", ["RUN unexpected"]),
        ("Env", ["PROVIDER_SECRET=synthetic"]),
    ],
)
def test_dependency_image_rejects_volumes_build_hooks_and_credential_fields(field, value):
    with pytest.raises(smoke.SmokeError):
        smoke.verify_peer_base({"Config": {field: value}})


@pytest.mark.parametrize(
    "case",
    [
        "exact",
        "other_image",
        "missing_image",
        "other_name",
        "lowercase_name",
        "unknown_hex",
        "changed_value",
        "lowercase_value",
        "empty_value",
        "suffix",
        "no_equals",
        "mixed_duplicate",
        "key",
        "token",
        "proxy",
        "credential",
        "secret",
        "password",
        "volume",
        "build_hook",
    ],
)
def test_public_python_signing_fingerprint_requires_exact_image_name_and_value(case):
    image = "sha256:09cbaba853686c120466c9e572dcd72c3dabf735c362452b1cd4babd2669a4f2"
    public = "7169605F62C751356D054A26A821E680E5FA6305"
    entry = "GPG_KEY=" + public
    item = {"Id": image, "Config": {"Env": ["PATH=/opt/venv/bin:/usr/bin", entry]}}
    config = item["Config"]
    if case == "other_image":
        item["Id"] = "sha256:" + "f" * 64
    elif case == "missing_image":
        item.pop("Id")
    elif case == "other_name":
        config["Env"][-1] = "OTHER_KEY=" + public
    elif case == "lowercase_name":
        config["Env"][-1] = "gpg_key=" + public
    elif case in ("unknown_hex", "changed_value", "lowercase_value", "empty_value", "suffix"):
        value = {
            "unknown_hex": "0" * 40,
            "changed_value": public[:-1] + "0",
            "lowercase_value": public.lower(),
            "empty_value": "",
            "suffix": public + "=extra",
        }[case]
        config["Env"][-1] = "GPG_KEY=" + value
    elif case == "no_equals":
        config["Env"][-1] = "GPG_KEY"
    elif case == "mixed_duplicate":
        config["Env"].append("GPG_KEY=synthetic-unapproved-value")
    elif case in ("key", "token", "proxy", "credential", "secret", "password"):
        config["Env"].append(case.upper() + "=synthetic-unapproved-value")
    elif case == "volume":
        config["Volumes"] = {"/synthetic": {}}
    elif case == "build_hook":
        config["OnBuild"] = ["RUN synthetic-unapproved-hook"]
    if case == "exact":
        smoke.verify_peer_base(item)
    else:
        with pytest.raises(smoke.SmokeError) as caught:
            smoke.verify_peer_base(item)
        assert str(caught.value) in {
            "Test runtime image has credential environment fields",
            "Test runtime image declares volumes",
            "Test runtime image declares build hooks",
        }


@pytest.mark.parametrize(
    "incorrect", [None, "request_denial_attempt", "missing_response_policy", "leaked_text"]
)
async def test_policy_preflight_assertions_are_checked_offline_without_running_gateway(incorrect):
    upstream = peer.SyntheticUpstream(scenario())

    def handle(request):
        body = json.loads(request.content)
        status, code = 200, None
        if "authorization" not in request.headers:
            status, code = 401, "unauthorized"
        elif body["model"] != smoke.DEFAULT_MODEL:
            status, code = 403, "model_forbidden"
        elif body["input"] == peer.BLOCKED:
            status, code = 403, "policy_denied"
            if incorrect == "request_denial_attempt":
                upstream.probes.append(body)
        elif body.get("include") or body.get("tools", [{}])[0].get("type") == "web_search":
            status, code = 400, "invalid_request"
        if code:
            return httpx.Response(status, json={"error": {"code": code}})
        probe = body["instructions"]
        upstream.probes.append({**body, "input": peer.MASKED})
        if probe == "synthetic-argument-block":
            if incorrect == "missing_response_policy":
                return httpx.Response(200, json={"output": []})
            return httpx.Response(403, json={"error": {"code": "policy_denied"}})
        if probe == "synthetic-response-mask":
            text = peer.REDACT if incorrect == "leaked_text" else "[removed] " + peer.MASKED
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=peer.event_bytes(body, [peer.message(text)], 99),
            )
        return httpx.Response(200, json={"output": [peer.message(smoke.MARKER)]})

    async with httpx.AsyncClient(
        base_url="http://synthetic.invalid", transport=httpx.MockTransport(handle)
    ) as client:
        if incorrect is None:
            assert await peer.preflight(client, upstream, smoke.DEFAULT_MODEL) == dict.fromkeys(
                peer.CHECKS, True
            )
        else:
            with pytest.raises(RuntimeError):
                await peer.preflight(client, upstream, smoke.DEFAULT_MODEL)


class _DiagnosticResponse:
    def __init__(self, status=502, payload=None):
        self.status_code = status
        self.payload = payload
        self.json_calls = 0

    def json(self):
        self.json_calls += 1
        return self.payload


def _complete_diagnostic(coroutine):
    """These pure controls must complete without an event loop or any sockets."""
    try:
        try:
            coroutine.send(None)
        except StopIteration as done:
            return done.value
        raise AssertionError("Pure diagnostic control unexpectedly suspended")
    finally:
        coroutine.close()


@pytest.mark.parametrize("primary_type", [RuntimeError, asyncio.CancelledError])
def test_preflight_diagnostic_known_failure_preserves_primary_and_cleanup(
    monkeypatch, capsys, primary_type
):
    primary = primary_type("PRIVATE_DIAGNOSTIC_SENTINEL")
    response = _DiagnosticResponse(payload={"error": {"code": "provider_error"}})
    cleanup = []

    class Client:
        async def post(self):
            return response

    async def failing(client, upstream, model):
        for _ in range(6):
            assert await client.post() is response
        raise primary

    monkeypatch.setattr(peer, "preflight", failing)
    with pytest.raises(primary_type) as caught:
        try:
            _complete_diagnostic(peer.observed_preflight(Client(), object(), smoke.DEFAULT_MODEL))
        finally:
            cleanup.append(True)
    assert caught.value is primary and cleanup == [True] and response.json_calls == 1
    assert json.loads(capsys.readouterr().out) == {
        "kind": "failure",
        "reason": "gateway_preflight_failed",
        "stage": "request_redacted",
        "status": 502,
        "category": "provider_error",
    }


@pytest.mark.parametrize("case", range(16))
def test_preflight_diagnostic_untrusted_error_json_is_unknown(case):
    class UntrustedDict(dict):
        pass

    class UntrustedString(str):
        pass

    sentinel = "PRIVATE_DIAGNOSTIC_SENTINEL"
    payloads: list[
        None
        | str
        | list[str]
        | dict[
            str, None | str | list[str] | dict[str, None | str | bool | list[str] | dict[str, str]]
        ]
    ]
    payloads = [
        None,
        [],
        sentinel,
        {},
        {"error": None},
        {"error": []},
        {"error": sentinel},
        {"error": {}},
        {"error": {"code": None}},
        {"error": {"code": [sentinel]}},
        {"error": {"code": {"private": sentinel}}},
        {"error": {"code": sentinel}},
        UntrustedDict(error={"code": "provider_error"}),
        {"error": UntrustedDict(code="provider_error")},
        {"error": {"code": UntrustedString("provider_error")}},
        {"error": {"code": True}},
    ]
    record = peer.preflight_failure(6, _DiagnosticResponse(payload=payloads[case]))
    assert record["status"] == 502 and record["category"] == "unknown"
    assert sentinel not in json.dumps(record)


@pytest.mark.parametrize("error_type", [ValueError, KeyboardInterrupt])
def test_preflight_diagnostic_invalid_json_retains_only_safe_status(error_type):
    class InvalidJSON:
        status_code = 502

        def json(self):
            raise error_type("PRIVATE_DIAGNOSTIC_SENTINEL")

    record = peer.preflight_failure(6, InvalidJSON())
    assert record["status"] == 502 and record["category"] == "unknown"


@pytest.mark.parametrize("status", [None, True, False, "502", 502.0, 99, 600, -1])
def test_preflight_diagnostic_invalid_status_is_explicitly_absent(status):
    record = peer.preflight_failure(6, _DiagnosticResponse(status))
    assert record["status"] is None and record["category"] == "unknown"


def test_preflight_diagnostic_hostile_values_are_never_formatted():
    class Untrusted:
        def __str__(self):
            raise AssertionError("Untrusted value was formatted")

        __repr__ = __str__

    response = _DiagnosticResponse(Untrusted(), {"error": {"code": Untrusted()}})
    record = peer.preflight_failure(6, response)
    assert record["status"] is None and record["category"] == "unknown"
    assert json.loads(json.dumps(record)) == record


@pytest.mark.parametrize(
    "step",
    [0, -1, 9, True, "PRIVATE_DIAGNOSTIC_SENTINEL"],
    ids=["zero", "negative", "out_of_sequence", "boolean", "untrusted"],
)
def test_preflight_diagnostic_invalid_stage_is_source_authored_unknown(step):
    assert peer.preflight_failure(step, None) == {
        "kind": "failure",
        "reason": "gateway_preflight_failed",
        "stage": "unknown",
        "status": None,
        "category": "unknown",
    }


def test_preflight_diagnostic_stages_and_categories_are_closed():
    for step, stage in enumerate(peer.CHECKS, 1):
        for category in peer.PREFLIGHT_ERROR_CATEGORIES:
            response = _DiagnosticResponse(payload={"error": {"code": category}})
            record = peer.preflight_failure(step, response)
            assert record["stage"] is stage and record["category"] is category
            assert set(record) == {"kind", "reason", "stage", "status", "category"}


def test_preflight_diagnostic_private_payload_and_exception_cannot_escape(monkeypatch, capsys):
    sentinel = "PRIVATE_DIAGNOSTIC_SENTINEL"
    response = _DiagnosticResponse(
        payload={"error": {"code": "provider_error", "message": sentinel}, "private": sentinel}
    )
    primary = RuntimeError(sentinel)

    class Client:
        async def post(self, *args, **kwargs):
            return response

    async def failing(client, upstream, model):
        await client.post(sentinel, headers={"private": sentinel}, json={"private": sentinel})
        raise primary

    monkeypatch.setattr(peer, "preflight", failing)
    with pytest.raises(RuntimeError) as caught:
        _complete_diagnostic(peer.observed_preflight(Client(), object(), sentinel))
    serialized = capsys.readouterr().out
    assert caught.value is primary and sentinel not in serialized
    assert set(json.loads(serialized)) == {"kind", "reason", "stage", "status", "category"}


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_preflight_diagnostic_emit_failure_cannot_replace_primary(monkeypatch, error_type):
    primary = RuntimeError("PRIVATE_DIAGNOSTIC_SENTINEL")

    async def failing(*args):
        raise primary

    def broken_emit(record):
        raise error_type("PRIVATE_DIAGNOSTIC_SENTINEL")

    monkeypatch.setattr(peer, "preflight", failing)
    monkeypatch.setattr(peer, "emit", broken_emit)
    with pytest.raises(RuntimeError) as caught:
        _complete_diagnostic(peer.observed_preflight(object(), object(), smoke.DEFAULT_MODEL))
    assert caught.value is primary


def test_preflight_diagnostic_failed_post_does_not_reuse_previous_response(monkeypatch, capsys):
    primary = RuntimeError("PRIVATE_DIAGNOSTIC_SENTINEL")

    class Client:
        calls = 0

        async def post(self):
            self.calls += 1
            if self.calls == 2:
                raise primary
            return _DiagnosticResponse(payload={"error": {"code": "provider_error"}})

    async def failing(client, upstream, model):
        await client.post()
        await client.post()

    monkeypatch.setattr(peer, "preflight", failing)
    with pytest.raises(RuntimeError) as caught:
        _complete_diagnostic(peer.observed_preflight(Client(), object(), smoke.DEFAULT_MODEL))
    record = json.loads(capsys.readouterr().out)
    assert caught.value is primary
    assert record["stage"] == "model_denied"
    assert record["status"] is None and record["category"] == "unknown"


def test_preflight_diagnostic_success_has_identical_result_and_no_extra_parsing(
    monkeypatch, capsys
):
    response = _DiagnosticResponse(200, object())
    result: dict[str, bool]
    result, upstream, model, payload = {}, object(), object(), object()
    calls = []

    class Client:
        async def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            return response

    async def successful(client, actual_upstream, actual_model):
        assert actual_upstream is upstream and actual_model is model
        assert await client.post(payload, json=payload) is response
        return result

    monkeypatch.setattr(peer, "preflight", successful)
    assert _complete_diagnostic(peer.observed_preflight(Client(), upstream, model)) is result
    assert calls == [((payload,), {"json": payload})]
    assert response.json_calls == 0 and capsys.readouterr().out == ""


def test_preflight_diagnostic_uses_existing_failure_record_rejection():
    record = peer.preflight_failure(
        6, _DiagnosticResponse(payload={"error": {"code": "provider_error"}})
    )
    assert smoke.records(json.dumps(record)) == [record]
    client, server = evidence()
    with pytest.raises(smoke.SmokeError):
        smoke.verify_cycle(client, server + [record], smoke.DEFAULT_MODEL, 1)


def test_preflight_diagnostic_retains_exact_original_assertions_fixtures_and_cleanup():
    hashes = {
        "preflight": "fa06171248183f4e56a4b36d0c4917e9a66ed9ad8d5ec538861641ff6eeff484",
        "main": "29350ec2fd3932f8e56ff316715266d4f3e8c8b5f5a60454767e11f70dbe544a",
        "message": "6273ac085c46abd10e03e209c63cb5d1fafd1283c2d280956067b3f2bd544b66",
        "envelope": "547c895208e4267e70aad1716ccb82f3442fcab92ab2ec588b7d5401fb91ecbf",
        "event_bytes": "ba6bc3bcfdcade129d012262ce610b1d15efdb954f44db79ac504b8698253648",
    }
    for name, expected in hashes.items():
        source = inspect.getsource(getattr(peer, name)).encode()
        assert hashlib.sha256(source).hexdigest() == expected
    original_serve = inspect.getsource(peer.serve).replace(
        'await observed_preflight(client, upstream, config["model"])',
        'await preflight(client, upstream, config["model"])',
    )
    assert hashlib.sha256(original_serve.encode()).hexdigest() == (
        "2a024decb3e089e2369923b9ca3c118ce47c4803bc1adc1f0076ae6eb49c0939"
    )
    assert peer.message("Synthetic")["content"][0]["logprobs"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Optional pure Node wire validation")
@pytest.mark.parametrize("count,turn", [(1, 1), (2, 1), (2, 2)])
def test_python_gateway_peer_fixture_is_accepted_by_fixed_command_gate(tmp_path, count, turn):
    context = tmp_path / "context"
    smoke.write_context(context, smoke.DEFAULT_MODEL, count)
    config = scenario(count)
    wire = peer.event_bytes({"model": smoke.DEFAULT_MODEL}, peer.output_items(config, turn), turn)
    result = subprocess.run(
        [shutil.which("node"), str(context / "harness.mjs"), "validate"],
        input=wire,
        capture_output=True,
        timeout=10,
        env={"PATH": os.defpath},
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_freeze_candidate_cli_never_runs_docker_or_approves_sources(monkeypatch, tmp_path, capsys):
    path = tmp_path / "freeze.json"
    monkeypatch.setattr(sys, "argv", ["smoke_codex.py", "--write-gateway-freeze", str(path)])
    monkeypatch.setattr(smoke, "run_smoke", lambda *a, **k: pytest.fail("Freeze is not execution"))
    monkeypatch.setattr(smoke, "docker", lambda *a, **k: pytest.fail("Freeze must stay offline"))
    smoke.main()
    report = json.loads(capsys.readouterr().out)
    assert report["review"] == "required" and "passed" not in report


def test_source_drift_blocks_gateway_before_any_artifact_or_docker(monkeypatch, tmp_path):
    path = tmp_path / "freeze.json"
    candidate = smoke.write_gateway_freeze(path)
    sources = smoke.frozen_sources(Path(SPEC.origin).resolve().parents[1])
    sources["gateway7/app.py"] += b"\n# synthetic drift\n"
    monkeypatch.setattr(smoke, "frozen_sources", lambda root: sources)
    monkeypatch.setattr(smoke, "docker", lambda *a, **k: pytest.fail("Drift must block execution"))
    with pytest.raises(smoke.SmokeError, match="changed after"):
        smoke.run_smoke(
            tmp_path / "new",
            gateway_runtime_image="sha256:" + "2" * 64,
            gateway_freeze=path,
            gateway_freeze_sha256=candidate["sha256"],
            allow_opaque=True,
            allow_hosted_tools=True,
        )
    assert not (tmp_path / "new").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="Offline mocked Node proxy test")
@pytest.mark.parametrize(
    "status,safe",
    [
        (200, True),
        (200, False),
        (201, False),
        (202, False),
        (206, False),
        (204, True),
        (201, True),
        (400, False),
    ],
)
def test_proxy_rejects_unexpected_status_before_reading_or_forwarding_tool_payload(
    tmp_path, status, safe
):
    context = tmp_path / "context"
    smoke.write_context(context, smoke.DEFAULT_MODEL, 1)
    # Export the actual proxy implementation without the container-only entrypoint.
    # All HTTP/fetch operations below are mocked; no sockets or Codex are used.
    source = (context / "harness.mjs").read_text().split("\nif (mode === 'verify')", 1)[0]
    (context / "proxy.mjs").write_text(source + "\nexport {safetyProxy};\n")
    output = peer.output_items(scenario(), 1)
    if not safe:
        output[-1]["arguments"] = '{"cmd":"UNAPPROVED_SYNTHETIC_COMMAND"}'
    wire = peer.event_bytes({"model": smoke.DEFAULT_MODEL}, output, 1).decode()
    script = (
        r"""
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import http from 'node:http';
let handle, reads = 0;
http.createServer = (options, callback) => {
  handle = callback;
  return {listen(port, host, done) { assert.equal(host, '127.0.0.1'); done(); },
    address() { return {port: 12345}; }};
};
globalThis.fetch = async (url, options) => {
  assert.equal(url, 'http://synthetic.invalid/v1/responses');
  assert.equal(options.redirect, 'error');
  return {status: __STATUS__, headers: new Headers({'content-type': 'text/event-stream'}),
    body: {async *[Symbol.asyncIterator]() { reads++; yield Buffer.from(__WIRE__); }}};
};
const {safetyProxy} = await import('./proxy.mjs');
await safetyProxy('http://synthetic.invalid/v1');
const request = new EventEmitter(), response = new EventEmitter();
request.method = 'POST'; request.url = '/v1/responses';
let observedStatus, delivered;
const done = new Promise(resolve => {
  response.writeHead = code => { observedStatus = code; response.headersSent = true; return response; };
  response.end = bytes => { delivered = bytes ?? Buffer.alloc(0); resolve(); };
});
handle(request, response); request.emit('data', Buffer.from('{}')); request.emit('end');
await done;
assert.equal(observedStatus, __APPROVED__ ? 200 : 502);
assert.equal(reads, __STATUS__ === 200 ? 1 : 0);
assert.equal(delivered.includes('UNAPPROVED_SYNTHETIC_COMMAND'), false);
if (!__APPROVED__) assert.equal(delivered.length, 0);
console.log(JSON.stringify({proxy_checked: true}));
""".replace("__STATUS__", str(status))
        .replace("__WIRE__", json.dumps(wire))
        .replace("__APPROVED__", json.dumps(status == 200 and safe))
    )
    (context / "proxy-test.mjs").write_text(script)
    result = subprocess.run(
        [shutil.which("node"), str(context / "proxy-test.mjs")],
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": os.defpath},
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"proxy_checked": True}


def overlay_modules(root):
    files, modules = {}, {}
    for name, relative in (
        ("gateway7", "gateway7/__init__.py"),
        ("gateway7.app", "gateway7/app.py"),
        ("gateway7.plugins", "gateway7/plugins/__init__.py"),
        ("gateway7.plugins.content_policy", "gateway7/plugins/content_policy.py"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SYNTHETIC_REVIEWED_SOURCE = True\n")
        spec = importlib.util.spec_from_file_location(name, path)
        modules[name] = importlib.util.module_from_spec(spec)
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files, modules


@pytest.mark.parametrize(
    "collision",
    [
        None,
        "package",
        "nested",
        "spec_origin",
        "source_hash",
        "search_path",
        "unknown_module",
        "missing_spec",
    ],
)
def test_gateway_import_origin_guard_rejects_preloaded_installed_collisions(tmp_path, collision):
    root = tmp_path / "reviewed-overlay"
    files, modules = overlay_modules(root)
    sentinel = "/synthetic-installed-private-location/gateway7/unreviewed.py"
    if collision in ("package", "nested"):
        name = "gateway7" if collision == "package" else "gateway7.plugins.content_policy"
        spec = importlib.util.spec_from_file_location(name, sentinel)
        modules[name] = importlib.util.module_from_spec(spec)
    elif collision == "spec_origin":
        modules["gateway7.app"].__spec__.origin = sentinel
    elif collision == "source_hash":
        (root / "gateway7/app.py").write_text("SYNTHETIC_SOURCE_DRIFT = True\n")
    elif collision == "search_path":
        modules["gateway7"].__path__.append("/synthetic-installed-private-location/gateway7")
    elif collision == "unknown_module":
        modules["gateway7.unreviewed"] = ModuleType("gateway7.unreviewed")
    elif collision == "missing_spec":
        modules["gateway7.app"].__spec__ = None
    if collision is None:
        verified = peer.verify_gateway_imports(root, files, modules=modules)
        assert set(verified) == set(modules)
    else:
        with pytest.raises(RuntimeError) as caught:
            peer.verify_gateway_imports(root, files, modules=modules)
        assert str(caught.value) == "gateway_import_verification_failed"
        assert sentinel not in str(caught.value)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, asyncio.CancelledError])
@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_double_interruption_defers_until_owned_cleanup_and_summary(
    monkeypatch, tmp_path, interruption, cleanup_failure
):
    fake = FakeDocker(cleanup_fails=cleanup_failure)
    primary = interruption("synthetic primary interruption")
    secondary = interruption("synthetic second interruption")
    injected = False

    def docker(args, **kwargs):
        nonlocal injected
        if args[:2] == ["start", "--attach"]:
            raise primary
        if args[:2] == ["rm", "--force"] and not injected:
            injected = True
            raise secondary
        return fake(args, **kwargs)

    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    output = tmp_path / "run"
    with pytest.raises(BaseException) as caught:
        smoke.run_smoke(output)
    assert caught.value is primary
    assert not fake.containers and set(fake.images) == {smoke.BASE_IMAGE}
    report = json.loads((output / "summary.json").read_text())
    assert report["passed"] is False and report["interrupted"] is True
    assert report["cleanup_complete"] is not cleanup_failure
    if cleanup_failure:
        assert fake.networks and any(not record["removed"] for record in report["cleanup"])
        fake.cleanup_fails = False
        manifest = json.loads((output / "ownership.json").read_text())
        assert all(
            record["removed"]
            for record in smoke.cleanup(
                manifest["owner"], [tuple(item) for item in manifest["resources"]]
            )
        )
    assert not fake.networks


def test_authorized_native_events_module_is_in_exact_source_allowlist():
    assert "gateway7/responses_events.py" in smoke.GATEWAY_SOURCES
    assert len(smoke.GATEWAY_SOURCES) == 25


async def test_installed_preload_is_rejected_before_product_import_despite_overlay_first(
    monkeypatch, tmp_path
):
    root = tmp_path / "reviewed-overlay"
    files, modules = overlay_modules(root)
    installed = tmp_path / "installed/gateway7/__init__.py"
    spec = importlib.util.spec_from_file_location("gateway7", installed)
    modules["gateway7"] = importlib.util.module_from_spec(spec)
    # Model a .pth/startup import cached before this process changes sys.path.
    loaded = {
        name: module
        for name, module in sys.modules.items()
        if name != "gateway7" and not name.startswith("gateway7.")
    }
    loaded.update(modules)
    monkeypatch.setattr(sys, "modules", loaded)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setattr(peer, "__file__", str(root / "codex_smoke_container.py"))
    monkeypatch.setattr(
        peer.importlib,
        "import_module",
        lambda *a, **k: pytest.fail("Must reject preload before importing the app"),
    )
    with pytest.raises(RuntimeError, match="^gateway_import_verification_failed$"):
        await peer.serve(scenario(), files)


def test_sigint_is_deferred_through_cleanup_and_previous_handler_is_restored(monkeypatch, tmp_path):
    fake = FakeDocker()
    primary = KeyboardInterrupt("synthetic first signal")
    previous = signal.getsignal(signal.SIGINT)
    observed = 0

    def docker(args, **kwargs):
        nonlocal observed
        if args[:2] == ["start", "--attach"]:
            raise primary
        if args[:2] == ["rm", "--force"]:
            handler = signal.getsignal(signal.SIGINT)
            assert callable(handler)
            handler(signal.SIGINT, None)
            handler(signal.SIGINT, None)
            observed += 2
        return fake(args, **kwargs)

    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    with pytest.raises(KeyboardInterrupt) as caught:
        smoke.run_smoke(tmp_path / "run")
    assert caught.value is primary and observed == 4
    assert signal.getsignal(signal.SIGINT) == previous
    assert not fake.containers and not fake.networks and set(fake.images) == {smoke.BASE_IMAGE}
    report = json.loads((tmp_path / "run/summary.json").read_text())
    assert report["cleanup_complete"] and report["interrupted"] and not report["passed"]


def test_interruption_during_summary_write_retries_and_preserves_primary(monkeypatch, tmp_path):
    fake = FakeDocker()
    primary = asyncio.CancelledError("synthetic first cancellation")
    write = Path.write_text
    writes = 0

    def write_text(path, *args, **kwargs):
        nonlocal writes
        if path.name == "summary.json":
            writes += 1
            if writes == 1:
                raise KeyboardInterrupt("synthetic repeated cancellation")
        return write(path, *args, **kwargs)

    def docker(args, **kwargs):
        if args[:2] == ["start", "--attach"]:
            raise primary
        return fake(args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)
    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    with pytest.raises(asyncio.CancelledError) as caught:
        smoke.run_smoke(tmp_path / "run")
    assert caught.value is primary and writes == 2
    assert not fake.containers and not fake.networks
    report = json.loads((tmp_path / "run/summary.json").read_text())
    assert report["cleanup_complete"] and report["interrupted"] and not report["passed"]


def test_exhausted_cancellation_retries_report_remaining_owned_resources(monkeypatch, tmp_path):
    fake = FakeDocker()
    primary = KeyboardInterrupt("synthetic primary")
    attempts = 0

    def docker(args, **kwargs):
        nonlocal attempts
        if args[:2] == ["start", "--attach"]:
            raise primary
        if args[:2] == ["rm", "--force"]:
            attempts += 1
            raise asyncio.CancelledError("synthetic repeated cancellation")
        return fake(args, **kwargs)

    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    output = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt) as caught:
        smoke.run_smoke(output)
    assert caught.value is primary and attempts == 2 * smoke.INTERRUPTION_ATTEMPTS
    report = json.loads((output / "summary.json").read_text())
    assert not report["passed"] and not report["cleanup_complete"] and report["interrupted"]
    assert len(fake.containers) == 2
    # The ownership record retains every resource for an explicit scoped retry.
    monkeypatch.setattr(smoke, "docker", fake)
    manifest = json.loads((output / "ownership.json").read_text())
    assert all(
        record["removed"]
        for record in smoke.cleanup(
            manifest["owner"], [tuple(item) for item in manifest["resources"]]
        )
    )
    assert not fake.containers and not fake.networks and set(fake.images) == {smoke.BASE_IMAGE}


def test_cleanup_deadline_bounds_docker_timeouts_and_does_not_claim_removal(monkeypatch):
    owner = "g7-codex-" + "a" * 12
    times = iter([0.0, smoke.CLEANUP_SECONDS + 1])
    monkeypatch.setattr(smoke.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(smoke, "docker", lambda *a, **k: pytest.fail("Deadline already expired"))
    assert smoke.cleanup(owner, [("container", owner + "-client")]) == [
        {"kind": "container", "identity": owner + "-client", "removed": False}
    ]


def test_cleanup_docker_steps_have_short_bounded_timeouts(monkeypatch):
    owner = "g7-codex-" + "a" * 12
    deadlines = []

    def inspect(kind, identity, *, missing_ok, timeout):
        deadlines.append(timeout)
        return {"Config": {"Labels": {smoke.OWNER_LABEL: owner}}}

    def docker(args, *, check, timeout):
        deadlines.append(timeout)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(smoke, "inspect", inspect)
    monkeypatch.setattr(smoke, "docker", docker)
    assert smoke.cleanup(owner, [("container", owner + "-client")]) == [
        {"kind": "container", "identity": owner + "-client", "removed": True}
    ]
    assert len(deadlines) == 2 and all(
        0 < value <= smoke.CLEANUP_STEP_SECONDS for value in deadlines
    )


def test_signal_during_successful_summary_write_is_recorded_before_reraising(monkeypatch, tmp_path):
    fake = FakeDocker()
    write = Path.write_text
    writes = 0

    def write_text(path, *args, **kwargs):
        nonlocal writes
        if path.name == "summary.json":
            writes += 1
            if writes == 1:
                signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        return write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    with pytest.raises(KeyboardInterrupt):
        smoke.run_smoke(tmp_path / "run")
    assert writes == 2 and not fake.containers and not fake.networks
    report = json.loads((tmp_path / "run/summary.json").read_text())
    assert report["interrupted"] and report["cleanup_complete"] and not report["passed"]


def test_summary_io_failure_does_not_replace_primary_or_hide_evidence_failure(
    monkeypatch, tmp_path, capsys
):
    fake = FakeDocker()
    primary = KeyboardInterrupt("synthetic primary")
    write = Path.write_text

    def write_text(path, *args, **kwargs):
        if path.name == "summary.json":
            raise OSError("SYNTHETIC_PRIVATE_FILESYSTEM_DETAIL")
        return write(path, *args, **kwargs)

    def docker(args, **kwargs):
        if args[:2] == ["start", "--attach"]:
            raise primary
        return fake(args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)
    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    with pytest.raises(KeyboardInterrupt) as caught:
        smoke.run_smoke(tmp_path / "run")
    assert caught.value is primary and not fake.containers and not fake.networks
    assert "summary could not be saved" in " ".join(primary.__notes__)
    assert capsys.readouterr().err == "Owned cleanup summary could not be saved\n"


@pytest.mark.parametrize(
    "cache_mode",
    [py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH],
)
@pytest.mark.parametrize("site_preload", [False, True])
def test_real_stale_bytecode_cannot_override_frozen_gateway_source(
    tmp_path, cache_mode, site_preload
):
    root = tmp_path / "overlay"
    files, _ = overlay_modules(root)
    old = "import builtins\nbuiltins.EXECUTIONS.append((__name__, 'OLD'))\n"
    new = old.replace("'OLD'", "'NEW'")
    timestamps = {}
    for relative in files:
        source = root / relative
        source.write_text(old)
        timestamps[relative] = source.stat().st_mtime_ns
    # Compile and consume the synthetic stale caches under the same explicit
    # private prefix, independent of the caller's cache-prefix policy. All real
    # repository imports keep a private process-start prefix, even in the control.
    stale_cache = tmp_path / "stale-cache"
    stale_cache.mkdir(mode=0o700)
    subprocess.run(
        [
            sys.executable,
            "-E",
            "-s",
            "-B",
            "-X",
            "pycache_prefix=" + str(stale_cache),
            "-c",
            "import importlib.util, py_compile, sys; "
            "mode = py_compile.PycInvalidationMode[sys.argv[1]]; "
            "[py_compile.compile(path, cfile=importlib.util.cache_from_source(path), "
            "doraise=True, invalidation_mode=mode) for path in sys.argv[2:]]",
            cache_mode.name,
            *(str(root / relative) for relative in files),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={"PATH": os.defpath},
        check=True,
    )
    assert len(list(stale_cache.rglob("*.pyc"))) == len(files) == 4
    for relative in files:
        source = root / relative
        source.write_text(new)
        os.utime(source, ns=(timestamps[relative], timestamps[relative]))
        assert len(old) == len(new)
        files[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    site = tmp_path / "synthetic-site"
    site.mkdir()
    (site / "preload.pth").write_text(
        "import gateway7.app; import gateway7.plugins.content_policy\n"
    )
    context = tmp_path / "context"
    smoke.write_gateway_context(
        context,
        "sha256:" + "2" * 64,
        (b"{}", {name: b"# synthetic\n" for name in smoke.GATEWAY_SOURCES}),
        scenario(),
    )
    entry = next(
        line[11:]
        for line in (context / "Dockerfile").read_text().splitlines()
        if line.startswith("ENTRYPOINT ")
    )
    flags = json.loads(entry)[1:-1]
    # Use the production process-start flags, but a new private test directory
    # instead of a container tmpfs. No provider, socket or real Gateway is used.
    flags = [
        value.replace("/run/test/gateway7-bytecode", str(tmp_path / "empty-cache"))
        for value in flags
    ]
    script = f"""
import builtins, hashlib, importlib, importlib.util, json, pathlib, site, sys
root = pathlib.Path({str(root)!r})
sys.path.insert(0, str(root))
builtins.EXECUTIONS = []
if {site_preload!r}:
    site.addsitedir({str(site)!r})
else:
    importlib.import_module('gateway7.app')
    importlib.import_module('gateway7.plugins.content_policy')
spec = importlib.util.spec_from_file_location('synthetic_peer', {PEER_SPEC.origin!r})
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
files = {files!r}
verified = helper.verify_gateway_imports(root, files)
assert len(verified) == 4
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in files.items())
print(json.dumps(builtins.EXECUTIONS))
"""
    # These deliberately stale synthetic caches must execute OLD. Do not clear
    # the private prefix: this subprocess also imports the real repository helper.
    control = [flag.replace(str(tmp_path / "empty-cache"), str(stale_cache)) for flag in flags]
    result = subprocess.run(
        [sys.executable, *control, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={"PATH": os.defpath},
        check=True,
    )
    assert all(version == "OLD" for _, version in json.loads(result.stdout))
    result = subprocess.run(
        [sys.executable, *flags, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={"PATH": os.defpath},
        check=True,
    )
    assert all(version == "NEW" for _, version in json.loads(result.stdout))
    cache = tmp_path / "empty-cache"
    assert not cache.exists() or not any(cache.iterdir())


def test_interrupted_ownership_tracking_keeps_recovery_manifest_for_failed_network_cleanup(
    monkeypatch, tmp_path, capsys
):
    fake = FakeDocker(cleanup_fails=True)
    fake.networks["unrelated-network"] = {"Labels": {smoke.OWNER_LABEL: "unrelated"}}
    primary = KeyboardInterrupt("synthetic interrupted ownership write")
    output = tmp_path / "run"
    original_open = Path.open
    previous = None
    interrupted = False

    class InterruptedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, text):
            self.stream.write(text[:3])
            self.stream.flush()
            raise primary

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    def open_path(path, mode="r", *args, **kwargs):
        nonlocal previous, interrupted
        ledger = path.name == "ownership.json" or path.name.startswith(".ownership-")
        network_exists = any(name.startswith("g7-codex-") for name in fake.networks)
        if ledger and mode in ("w", "x") and network_exists and not interrupted:
            previous = (output / "ownership.json").read_bytes()
            interrupted = True
            return InterruptedWriter(original_open(path, mode, *args, **kwargs))
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(smoke, "docker", fake)
    monkeypatch.setattr(smoke, "inspect", fake.inspect)
    with pytest.raises(KeyboardInterrupt) as caught:
        smoke.run_smoke(output)
    assert caught.value is primary and interrupted
    assert (output / "ownership.json").read_bytes() == previous
    manifest = json.loads((output / "ownership.json").read_bytes())
    owned_networks = set(fake.networks) - {"unrelated-network"}
    assert owned_networks and owned_networks <= {
        identity for kind, identity in manifest["resources"] if kind == "network"
    }
    summary = json.loads((output / "summary.json").read_bytes())
    assert not summary["cleanup_complete"] and not summary["passed"]
    assert any(
        item["kind"] == "network" and item["identity"] in owned_networks and not item["removed"]
        for item in summary["cleanup"]
    )
    assert not list(output.glob(".ownership-*"))
    fake.cleanup_fails = False
    monkeypatch.setattr(sys, "argv", ["smoke_codex.py", "--cleanup", str(output)])
    with pytest.raises(SystemExit) as exit_info:
        smoke.main()
    assert exit_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["cleanup_complete"] is True
    assert set(fake.networks) == {"unrelated-network"}
    assert not fake.containers and set(fake.images) == {smoke.BASE_IMAGE}


@pytest.mark.parametrize(
    "state", ["absent", "empty", "populated", "wrong_prefix", "writes_enabled"]
)
def test_private_bytecode_prefix_configuration_fails_closed(monkeypatch, tmp_path, state):
    cache = tmp_path / "private-cache"
    monkeypatch.setattr(peer, "BYTECODE_PREFIX", str(cache))
    monkeypatch.setattr(sys, "pycache_prefix", str(cache))
    monkeypatch.setattr(sys, "dont_write_bytecode", state != "writes_enabled")
    if state in ("empty", "populated"):
        cache.mkdir(mode=0o700)
    if state == "populated":
        (cache / "unreviewed.pyc").write_bytes(b"synthetic-not-executed")
    if state == "wrong_prefix":
        monkeypatch.setattr(sys, "pycache_prefix", str(tmp_path / "other-cache"))
    if state in ("absent", "empty"):
        peer.verify_private_bytecode_cache()
    else:
        with pytest.raises(RuntimeError, match="^private_bytecode_cache_"):
            peer.verify_private_bytecode_cache()


@pytest.mark.parametrize("when", ["before_replace", "after_replace"])
def test_atomic_ownership_publication_preserves_a_complete_record_at_interruption(
    monkeypatch, tmp_path, when
):
    owner = "g7-codex-" + "a" * 12
    previous = [("image", owner + ":verification")]
    intended = [*previous, ("network", owner + "-internal")]
    smoke.write_ownership(tmp_path, owner, previous)
    original = (tmp_path / "ownership.json").read_bytes()
    replace = os.replace
    primary = KeyboardInterrupt("synthetic publication interruption")

    def publish(source, target):
        assert Path(source).parent == Path(target).parent == tmp_path
        assert Path(source).stat().st_mode & 0o777 == 0o600
        assert json.loads(Path(source).read_bytes())["resources"] == [
            list(item) for item in intended
        ]
        assert Path(target).read_bytes() == original
        if when == "after_replace":
            replace(source, target)
        raise primary

    monkeypatch.setattr(smoke.os, "replace", publish)
    with pytest.raises(KeyboardInterrupt) as caught:
        smoke.write_ownership(tmp_path, owner, intended)
    assert caught.value is primary
    actual = json.loads((tmp_path / "ownership.json").read_bytes())
    expected = intended if when == "after_replace" else previous
    assert actual == {"owner": owner, "resources": [list(item) for item in expected]}
    assert not list(tmp_path.glob(".ownership-*"))

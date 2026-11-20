r"""Run non-billable Codex 0.153.4 read cycles inside hardened Linux containers.

CLI: python scripts/smoke_codex.py [--provision] [--parallel] [--model gpt-5.4]
Default builds are offline and require the pinned base/tool layers already cached.
Only --provision permits pulling the pinned public base and downloading hash-pinned
official npm packages. Nothing is installed globally. Artifacts stay outside the checkout.

API: run_smoke(path, server_image="sha256:<64 hex>", server_port=8765).
The optional local, immutable test-server image is started on the new private network;
arbitrary URLs, host mounts, host credentials and published ports are not accepted.
That image must carry the label gateway7.synthetic.responses-peer=1.
Its /health returns 200 and /v1/responses serves the selected synthetic scenario.
It emits JSON capture records {kind: "capture", turn: 1|2, body: <upstream request>}
on stdout. A future Gateway integration server must emit those records from its injected
synthetic upstream, not its HTTP ingress. Build that image from a temporary whitelist
containing only the built Gateway wheel, explicit synthetic server code and pre-resolved
test dependencies; never send the checkout, HOME, keys or .env as Docker build context.
For the owned real-Gateway peer, first write a candidate freeze outside the checkout:
  python scripts/smoke_codex.py --write-gateway-freeze /TEMP/source-freeze.json
After review approves its exact SHA256 and a local /opt/venv Python dependency image:
  python scripts/smoke_codex.py --gateway-runtime-image sha256:<64 hex> \
    --gateway-freeze /TEMP/source-freeze.json --gateway-freeze-sha256 <reviewed hash> \
    --allow-opaque --allow-hosted-tools --parallel --artifacts /TEMP/new-run
API: run_smoke(path, gateway_runtime_image=image_id, gateway_freeze=manifest_path,
               gateway_freeze_sha256=approved_hash, allow_opaque=True,
               allow_hosted_tools=True, parallel=True).
The supplied dependency image is never pulled/modified/removed. The peer overlay
build is always offline, uses only the frozen Python allowlist and this test helper,
and runs actual create_app/pipeline/HTTPProvider/policies/encoders with MockTransport.
The image must contain /opt/venv with Python 3.11-3.13 and the existing production
dependencies, accessible to UID 1000, with no credentials or volumes. Dependency
versions are inherited from the supplied image; lockfile equivalence is not proved.
Candidate generation is not review approval. Source drift fails before Docker use.
Gateway Python starts with -X pycache_prefix=/run/test/gateway7-bytecode under its
fresh private tmpfs before site processing; -B keeps that lookup prefix empty.
Frozen source hashes and loaded-module origins are still checked before readiness.

The built-in peer proves synthetic transport only, not Gateway policies or live model
compatibility. Namespace/custom/media advertisement is reported separately from execution.
This uses default checked playback and a buffering safety gate, not early-delivery
latency validation. Two executed calls do not establish simultaneous scheduling.
Only fixed synthetic file reads are released by the client-side safety gate; no patches,
searches or agents are executed. Supplied test peers cannot bypass that gate.
Docker's host/kernel and bridge-host reachability remain trust boundaries: this is not
a separate-kernel sandbox. Base/build caches are retained; no Docker prune is performed.
Recovery after interruption: python scripts/smoke_codex.py --cleanup <artifact-directory>.
Cleanup defers SIGINT through a 30-second teardown (at most 5 seconds per Docker
step) and summary writing, then re-raises the first interruption. Direct cancellation
exceptions retry a step at most three times. Incomplete cleanup remains a failure
with ownership.json available for a scoped retry; recovery writes cleanup-summary.json.
Ownership records are published atomically before resource creation. Interrupted
temporary writes preserve the previous valid record; cleanup results include exact IDs.
The native sandbox-disabling flag is used only inside the inspected test container.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Literal, TypeVar, overload
import uuid

VERSION = "0.153.4"
DEFAULT_MODEL = "gpt-4.1-mini"
MODELS = (DEFAULT_MODEL, "gpt-5.4")
BASE_IMAGE = "node@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9"
# Official npm archive integrities recorded from the verified 0.153.4 installation.
WRAPPER_INTEGRITY = "sha512-wbHDmit7S/YvBGVX1DQmk13xtWblZ2cApeJ/pB7xDZ10Cna+DZc5ij7f0F4OxdsXN4FW1oLT48OpogUI1+8Y2w=="
NATIVE_INTEGRITY = {
    "arm64": "sha512-QKdjYLYV4hXIuUQDP3P6F4NXuWFoKo9WUoV4nAREIx55kiUyi8UsYdsVobkeXir5n/maEQgYMCKLHVma4rNPiw==",
    "x64": "sha512-x1EcwBlY3AObM1VTUHNM2AzAJQsyreGdagpF+qFiYi/Oa30VBktvvG0C6tLtCzqW6hjZNWkGZQWmeVk7MuJKWg==",
}
OWNER_LABEL = "gateway7.synthetic.owner"
PEER_LABEL = "gateway7.synthetic.responses-peer"
# Public Python 3.12.14 release-signing fingerprint, pinned provenance:
# https://github.com/docker-library/python/blob/f2c5d1b8a6adecb5b00b3c9331d4f863beade6b3/3.12/slim-bookworm/Dockerfile
PYTHON_31214_SIGNING_IMAGE = (
    "sha256:09cbaba853686c120466c9e572dcd72c3dabf735c362452b1cd4babd2669a4f2"
)
PYTHON_31214_SIGNING_FINGERPRINT = "7169605F62C751356D054A26A821E680E5FA6305"
CLIENT_TOKEN = "gateway7-synthetic-codex-client"
MARKER = "GATEWAY7_CODEX_SYNTHETIC_READ_OK"
OPAQUE = "SYNTHETIC_OPAQUE_REASONING_NOT_REAL_CIPHERTEXT"
READ_COMMAND = "/bin/cat -- /run/test/work/synthetic-read.txt"
TOOL_ARGUMENTS = json.dumps(
    {"cmd": READ_COMMAND, "login": False, "yield_time_ms": 1000, "max_output_tokens": 128},
    separators=(",", ":"),
)
RUNTIME_CHECKS = (
    "non_root",
    "rootfs_read_only",
    "no_default_route",
    "egress_blocked",
    "zero_capabilities",
    "no_new_privileges",
    "seccomp",
    "no_docker_socket",
)
TMPFS = {
    "/run/test": "rw,nosuid,nodev,noexec,size=192m,uid=1000,gid=1000,mode=0700",
    "/tmp": "rw,nosuid,nodev,noexec,size=32m,uid=1000,gid=1000,mode=0700",
}
# Explicit runtime import closure, not a recursive checkout/package copy. A new
# production import needs review and a new freeze before it can enter the peer.
GATEWAY_SOURCES = tuple(
    "gateway7/" + name
    for name in (
        "__init__.py",
        "app.py",
        "auth.py",
        "config.py",
        "errors.py",
        "loader.py",
        "metrics.py",
        "models.py",
        "openai_api.py",
        "openai_stream.py",
        "pipeline.py",
        "plugin_api.py",
        "providers.py",
        "responses_api.py",
        "responses_events.py",
        "responses_models.py",
        "responses_policy.py",
        "responses_provider.py",
        "responses_stream.py",
        "transport_api.py",
        "transport_loader.py",
        "plugins/__init__.py",
        "plugins/content_policy.py",
        "plugins/email_mask.py",
        "plugins/phone_mask.py",
    )
)
GATEWAY_CHECKS = (
    "auth_denied",
    "model_denied",
    "request_denied",
    "opaque_default_denied",
    "hosted_default_denied",
    "request_redacted",
    "response_arguments_denied",
    "response_redacted",
)
CLEANUP_SECONDS = 30.0
CLEANUP_STEP_SECONDS = 5.0
INTERRUPTION_ATTEMPTS = 3
Result = TypeVar("Result")


class SmokeError(RuntimeError):
    """A bounded verification failure, without provider bodies or caller credentials."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def docker(args: list[str], *, timeout: float = 30, check: bool = True):
    try:
        result = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SmokeError("Docker command unavailable or exceeded its deadline") from None
    if check and result.returncode:
        raise SmokeError("Docker command failed: " + args[0])
    return result


@overload
def inspect(
    kind: str, identity: str, missing_ok: Literal[False] = False, *, timeout: float = 30
) -> dict[str, Any]: ...


@overload
def inspect(
    kind: str, identity: str, missing_ok: Literal[True], *, timeout: float = 30
) -> dict[str, Any] | None: ...


def inspect(
    kind: str, identity: str, missing_ok: bool = False, *, timeout: float = 30
) -> dict[str, Any] | None:
    result = docker([kind, "inspect", identity], check=False, timeout=timeout)
    if result.returncode:
        if missing_ok and re.search(
            r"No such (?:image|container|object)|network [^\n]+ not found", result.stderr
        ):
            return None
        raise SmokeError("Cannot inspect Docker resource")
    try:
        values = json.loads(result.stdout)
        require(isinstance(values, list) and len(values) == 1, "Invalid Docker inspection")
        require(isinstance(values[0], dict), "Invalid Docker inspection")
        return values[0]
    except (ValueError, TypeError):
        raise SmokeError("Invalid Docker inspection") from None


def artifact_directory(path: Path | None) -> Path:
    checkout = Path(__file__).resolve().parents[1]
    temporary = Path(tempfile.gettempdir()).resolve()
    if (temporary / "opencode").is_dir():
        temporary /= "opencode"
    target = path.resolve() if path is not None else temporary
    require(not target.is_relative_to(checkout), "Artifacts must stay outside the checkout")
    if path is None:
        return Path(tempfile.mkdtemp(prefix="gateway7-codex-", dir=target))
    require(not target.exists(), "Artifact directory must be new")
    target.mkdir(mode=0o700)
    return target


def frozen_sources(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    result = {}
    for name in GATEWAY_SOURCES:
        source = root / name
        require(
            source.resolve() == source and source.is_file(),
            "Gateway allowlisted source missing or contains a symlink: " + name,
        )
        with source.open("rb") as stream:
            data = stream.read(1_048_577)
        require(len(data) <= 1_048_576, "Gateway source exceeds its bound")
        result[name] = data
    require(sum(map(len, result.values())) <= 3 * 1024**2, "Gateway bundle exceeds its bound")
    return result


def write_gateway_freeze(path: Path) -> dict:
    target = path.resolve()
    require(
        not target.is_relative_to(Path(__file__).resolve().parents[1]),
        "Source freeze must stay outside the checkout",
    )
    sources = frozen_sources(Path(__file__).resolve().parents[1])
    data = (
        json.dumps(
            {
                "format": 1,
                "files": {
                    name: hashlib.sha256(content).hexdigest() for name, content in sources.items()
                },
            },
            indent=2,
        )
        + "\n"
    ).encode()
    with target.open("xb") as destination:
        destination.write(data)
    return {
        "scope": "source_freeze_candidate",
        "review": "required",
        "sha256": hashlib.sha256(data).hexdigest(),
        "files": len(sources),
        "path": str(target),
    }


def reviewed_sources(freeze: Path, digest: str) -> tuple[bytes, dict[str, bytes]]:
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "Supply the reviewed source-freeze SHA256")
    with freeze.open("rb") as stream:
        data = stream.read(16_385)
    require(
        len(data) <= 16_384 and hashlib.sha256(data).hexdigest() == digest,
        "Reviewed source-freeze hash mismatch",
    )
    manifest = json.loads(data)
    require(
        isinstance(manifest, dict)
        and set(manifest) == {"format", "files"}
        and type(manifest["format"]) is int
        and manifest["format"] == 1
        and isinstance(manifest["files"], dict)
        and set(manifest["files"]) == set(GATEWAY_SOURCES),
        "Freeze must contain exactly the Gateway source allowlist",
    )
    sources = frozen_sources(Path(__file__).resolve().parents[1])
    require(
        manifest["files"]
        == {name: hashlib.sha256(content).hexdigest() for name, content in sources.items()},
        "Gateway sources changed after the reviewed freeze",
    )
    return data, sources


def verify_peer_base(item: dict) -> None:
    config = item.get("Config", {})
    require(not config.get("Volumes"), "Test runtime image declares volumes")
    require(not config.get("OnBuild"), "Test runtime image declares build hooks")
    require(
        not any(
            re.search(r"KEY|TOKEN|PROXY|CREDENTIAL|SECRET|PASSWORD", value.split("=", 1)[0], re.I)
            and not (
                item.get("Id") == PYTHON_31214_SIGNING_IMAGE
                and value == "GPG_KEY=" + PYTHON_31214_SIGNING_FINGERPRINT
            )
            for value in config.get("Env", [])
        ),
        "Test runtime image has credential environment fields",
    )


def write_gateway_context(
    context: Path,
    runtime_image: str,
    frozen: tuple[bytes, dict[str, bytes]],
    scenario: dict,
) -> None:
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_image),
        "Gateway runtime must be a local immutable image ID",
    )
    require(set(frozen[1]) == set(GATEWAY_SOURCES), "Invalid Gateway staging allowlist")
    context.mkdir(mode=0o700)
    for name, content in frozen[1].items():
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    helper = Path(__file__).with_name("codex_smoke_container.py")
    (context / helper.name).write_bytes(helper.read_bytes())
    (context / "scenario.json").write_text(json.dumps(scenario))
    (context / "source-freeze.json").write_bytes(frozen[0])
    names = [*GATEWAY_SOURCES, helper.name, "scenario.json", "source-freeze.json"]
    (context / ".dockerignore").write_text(
        "**\n!Dockerfile\n!gateway7/\n!gateway7/plugins/\n"
        + "".join("!" + name + "\n" for name in names)
    )
    # No package install, resolver, checkout Dockerfile or project entrypoint.
    (context / "Dockerfile").write_text(
        f"FROM {runtime_image}\nWORKDIR /opt/synthetic\n"
        + "".join(f"COPY {name} /opt/synthetic/{name}\n" for name in names)
        + f"LABEL {PEER_LABEL}=1\nUSER 1000:1000\nHEALTHCHECK NONE\n"
        # -B prevents writes, not cache reads. Set the lookup prefix at process
        # startup, before site/.pth processing, under the fresh private tmpfs.
        + 'ENTRYPOINT ["/opt/venv/bin/python", "-E", "-s", "-B", "-X", '
        + '"pycache_prefix=/run/test/gateway7-bytecode", "/opt/synthetic/codex_smoke_container.py"]\n'
        + "CMD []\n"
    )


def verify_gateway(server: list[dict], digest: str, consent: dict) -> dict:
    proofs = [item for item in server if item.get("kind") == "gateway"]
    runtime = [item for item in server if item.get("kind") == "runtime"]
    ingress = [item for item in server if item.get("kind") == "gateway_ingress"]
    require(
        len(runtime) == 1 and all(runtime[0].get(key) is True for key in RUNTIME_CHECKS),
        "Gateway peer runtime isolation evidence missing",
    )
    require(
        len(proofs) == 1
        and proofs[0].get("source_freeze_sha256") == digest
        and proofs[0].get("checks") == dict.fromkeys(GATEWAY_CHECKS, True)
        and proofs[0].get("preflight_upstream_requests") == 3
        and proofs[0].get("policies") == ["guard", "redact", "email", "phone"]
        and proofs[0].get("overlay_imports_verified") is True
        and proofs[0].get("transport") == "httpx.MockTransport",
        "Real Gateway policy preflight evidence missing",
    )
    require(
        len([item for item in server if item.get("kind") == "preflight_capture"]) == 3,
        "Gateway preflight captures must be separate from Codex requests",
    )
    require(
        len(ingress) == 2
        and all(
            item.get("consent") == consent and item.get("stream_mode") == "default_checked"
            for item in ingress
        ),
        "Gateway did not observe the explicit consent and default checked stream mode",
    )
    return proofs[0]["checks"]


def build_command(
    owner: str, context: Path, *, provision: bool, gateway: bool = False
) -> list[str]:
    require(re.fullmatch(r"g7-codex-[0-9a-f]{12}", owner), "Invalid run owner")
    args = [
        "build",
        "--pull=false",
        "--force-rm=true",
        "--rm=true",
        "--network=default" if provision and not gateway else "--network=none",
        "--label",
        OWNER_LABEL + "=" + owner,
        "--tag",
        owner + (":gateway" if gateway else ":verification"),
    ]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        for key in (name, name.lower()):
            args.extend(["--build-arg", key + "="])
    return [*args, str(context)]


def container_command(
    owner: str, network: str, image: str, role: str, command: list[str]
) -> list[str]:
    require(
        re.fullmatch(r"g7-codex-[0-9a-f]{12}", owner) and network == owner + "-internal",
        "Container must use this run's private network",
    )
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", image), "Container image must be immutable and local"
    )
    require(role in ("server", "client"), "Unknown container role")
    return [
        "create",
        "--pull=never",
        "--name",
        owner + "-" + role,
        "--label",
        OWNER_LABEL + "=" + owner,
        "--network",
        network,
        "--dns=127.0.0.1",
        "--user=1000:1000",
        "--read-only",
        "--init",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--memory=768m",
        "--memory-swap=768m",
        "--cpus=1",
        "--pids-limit=128",
        "--ulimit=nofile=1024:1024",
        "--shm-size=8m",
        "--ipc=private",
        "--stop-timeout=2",
        "--log-opt=max-size=2m",
        "--log-opt=max-file=1",
        "--tmpfs",
        "/run/test:" + TMPFS["/run/test"],
        "--tmpfs",
        "/tmp:" + TMPFS["/tmp"],
        "--env",
        "HOME=/run/test/home",
        image,
        *command,
    ]


def verify_container(item: dict[str, Any], network: str) -> None:
    host = item["HostConfig"]
    require(
        item["Config"]["User"] == "1000:1000"
        and host["ReadonlyRootfs"]
        and not host.get("Binds")
        and not host.get("Mounts")
        and not host.get("PortBindings")
        and all(m["Type"] == "tmpfs" for m in item.get("Mounts", []))
        and not host["Privileged"]
        and host.get("CapDrop") == ["ALL"]
        and not host.get("CapAdd")
        and not host.get("Devices")
        and not host.get("DeviceRequests")
        and host["Memory"] == host["MemorySwap"] == 768 * 1024**2
        and host["NanoCpus"] == 10**9
        and host["PidsLimit"] == 128
        and host["Init"]
        and host.get("PidMode", "") == ""
        and host["IpcMode"] == "private"
        and host["NetworkMode"] == network
        and host.get("Dns") == ["127.0.0.1"]
        and host.get("Tmpfs") == TMPFS
        and host.get("SecurityOpt") == ["no-new-privileges=true"],
        "Container isolation inspection failed",
    )


def records(text: str) -> list[dict[str, Any]]:
    require(len(text.encode()) <= 2 * 1024**2, "Verification output exceeded its bound")
    try:
        result = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
        require(all(isinstance(value, dict) for value in result), "Invalid verification record")
        return result
    except ValueError:
        raise SmokeError("Invalid verification JSON") from None


def verify_cycle(client: list[dict], server: list[dict], model: str, count: int) -> dict:
    def one(kind):
        matching = [x for x in client if x.get("kind") == kind]
        require(len(matching) == 1, "Missing or duplicated client evidence: " + kind)
        return matching[0]

    runtime, provenance, exit_record = one("runtime"), one("provenance"), one("exit")
    require(
        not any(x.get("kind") == "safety_rejection" for x in client),
        "Client-side fixed-command gate rejected an upstream response",
    )
    require(all(runtime.get(key) is True for key in RUNTIME_CHECKS), "Runtime isolation failed")
    require(
        provenance.get("version") == "codex-cli " + VERSION
        and provenance.get("package_version") == VERSION
        and provenance.get("wrapper_integrity") == WRAPPER_INTEGRITY
        and provenance.get("native_integrity") == NATIVE_INTEGRITY.get(provenance.get("arch"))
        and provenance.get("arch") in NATIVE_INTEGRITY
        and re.fullmatch(r"[0-9a-f]{64}", provenance.get("binary_sha256", "")),
        "Codex version or archive integrity was not verified",
    )
    require(
        exit_record.get("code") == 0
        and exit_record.get("timed_out") is False
        and exit_record.get("overflow") is False,
        "Native client did not finish successfully",
    )
    events = [x["event"] for x in client if x.get("kind") == "codex"]
    require(
        not any(e.get("type") in ("error", "turn.failed") for e in events), "Native client error"
    )
    complete = [e["item"] for e in events if e.get("type") == "item.completed"]
    warning = (
        f"Model metadata for `{model}` not found. Defaulting to fallback metadata; "
        "this can degrade performance and cause issues."
    )
    require(
        all(item.get("message") == warning for item in complete if item.get("type") == "error"),
        "Native client reported an item error",
    )
    reads = [item for item in complete if item.get("type") == "command_execution"]
    require(
        len(reads) == count and len({item.get("id") for item in reads}) == count,
        "Expected distinct actual completed file reads",
    )
    allowed_commands = {
        READ_COMMAND,
        *(f"{shell} -c '{READ_COMMAND}'" for shell in ("/bin/bash", "/bin/sh")),
    }
    require(
        all(
            item.get("status") == "completed"
            and item.get("exit_code") == 0
            and item.get("command") in allowed_commands
            and item.get("aggregated_output") == MARKER + "\n"
            for item in reads
        ),
        "Read command or its actual result did not match the fixture",
    )
    require(
        [x.get("text") for x in complete if x.get("type") == "agent_message"] == [MARKER]
        and sum(e.get("type") == "turn.completed" for e in events) == 1,
        "Missing exact final answer or completed turn",
    )
    captures = [x for x in server if x.get("kind") == "capture"]
    require(
        len(captures) == 2
        and [x.get("turn") for x in captures] == [1, 2]
        and not any(x.get("kind") == "failure" for x in server),
        "Expected two upstream requests",
    )
    first, second = [x["body"] for x in captures]
    require(
        not any(
            item.get("type") in ("function_call", "function_call_output") for item in first["input"]
        ),
        "Unexpected initial tool history",
    )
    for body in (first, second):
        require(
            body.get("model") == model
            and body.get("stream") is True
            and body.get("store") is False
            and body.get("parallel_tool_calls") is True
            and "reasoning.encrypted_content" in body.get("include", []),
            "Client profile controls changed",
        )
    history = second["input"]
    calls = [x for x in history if x.get("type") == "function_call"]
    outputs = [x for x in history if x.get("type") == "function_call_output"]
    require(len(calls) == len(outputs) == count, "Unexpected tool history count")
    for index in range(count):
        identity = f"call_read_{index}"
        call = [x for x in calls if x.get("call_id") == identity]
        output = [x for x in outputs if x.get("call_id") == identity]
        require(
            len(call) == len(output) == 1
            and call[0].get("name") == "exec_command"
            and call[0].get("arguments") == TOOL_ARGUMENTS,
            "Tool identity or arguments changed",
        )
        value = output[0].get("output")
        require(
            isinstance(value, str)
            and "Process exited with code 0\n" in value
            and value.endswith("\nOutput:\n" + MARKER + "\n")
            and history.index(call[0]) < history.index(output[0]),
            "Actual read result was not replayed",
        )
    reasoning = [item for item in history if item.get("type") == "reasoning"]
    require(
        len(reasoning) == 1
        and reasoning[0].get("id") == "rs_synthetic"
        and reasoning[0].get("encrypted_content") == OPAQUE,
        "Opaque reasoning was not preserved",
    )
    tools = first["tools"]
    return {
        "read_executions": count,
        "parallel_calls_executed": count > 1,
        "reasoning_preserved": True,
        "metadata_warnings": sum(item.get("type") == "error" for item in complete),
        **{
            name: {"advertised": any(test(t) for t in tools), "executed": False}
            for name, test in (
                ("namespace", lambda t: t.get("type") == "namespace"),
                ("custom", lambda t: t.get("type") == "custom"),
                ("media", lambda t: t.get("name") == "view_image"),
                ("hosted", lambda t: t.get("type") in ("web_search", "web_search_preview")),
            )
        },
    }


class DeferredInterrupts:
    """Hold SIGINT during bounded teardown and retain the first interruption.

    Direct cancellation exceptions (for example from an embedding caller) retry
    the current idempotent teardown step, rather than skipping the owned resource.
    SIGKILL, daemon failure and process crashes still require manifest recovery.
    """

    def __init__(self, primary: BaseException | None = None) -> None:
        self.primary = primary

    def remember(self, error: BaseException) -> None:
        if self.primary is None:
            self.primary = error

    @contextmanager
    def hold(self):
        main = threading.current_thread() is threading.main_thread()
        previous = signal.getsignal(signal.SIGINT) if main else None
        if main:
            signal.signal(signal.SIGINT, lambda *_: self.remember(KeyboardInterrupt()))
        try:
            yield self
        finally:
            if main:
                signal.signal(signal.SIGINT, previous)

    def retry(self, operation: Callable[[], Result]) -> Result:
        for _ in range(INTERRUPTION_ATTEMPTS):
            try:
                return operation()
            except (KeyboardInterrupt, asyncio.CancelledError) as error:
                self.remember(error)
        raise SmokeError("Repeated cancellation prevented a bounded cleanup step")


def cleanup(
    owner: str, resources: list[tuple[str, str]], *, deferred: DeferredInterrupts | None = None
) -> list[dict]:
    if deferred is None:
        pending = DeferredInterrupts()
        with pending.hold():
            result = cleanup(owner, resources, deferred=pending)
        if pending.primary is not None:
            raise pending.primary
        return result
    require(re.fullmatch(r"g7-codex-[0-9a-f]{12}", owner), "Invalid run owner")
    results = []
    deadline = time.monotonic() + CLEANUP_SECONDS

    def timeout() -> float:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "Owned cleanup deadline exceeded")
        return min(CLEANUP_STEP_SECONDS, remaining)

    allowed = {
        ("image", owner + ":verification"),
        ("image", owner + ":gateway"),
        ("network", owner + "-internal"),
        ("container", owner + "-server"),
        ("container", owner + "-client"),
    }
    for kind, identity in reversed(resources):

        def remove() -> None:
            require((kind, identity) in allowed, "Resource is outside this run")
            item = inspect(kind, identity, missing_ok=True, timeout=timeout())
            if item is not None:
                labels = (
                    item.get("Labels", {})
                    if kind == "network"
                    else item.get("Config", {}).get("Labels", {})
                )
                require((labels or {}).get(OWNER_LABEL) == owner, "Resource ownership mismatch")
                args = (
                    ["rm", "--force", identity] if kind == "container" else [kind, "rm", identity]
                )
                require(
                    docker(args, check=False, timeout=timeout()).returncode == 0,
                    "Resource removal failed",
                )

        try:
            deferred.retry(remove)
            results.append({"kind": kind, "identity": identity, "removed": True})
        except Exception:
            results.append({"kind": kind, "identity": identity, "removed": False})
    return results


def finish_cleanup(
    output: Path,
    owner: str,
    resources: list[tuple[str, str]],
    report: dict,
    primary: BaseException | None = None,
    *,
    summary_name: str = "summary.json",
) -> None:
    pending = DeferredInterrupts(primary)
    with pending.hold():
        report["cleanup"] = cleanup(owner, resources, deferred=pending)
        report["cleanup_complete"] = all(item["removed"] for item in report["cleanup"])

        def save() -> None:
            report["interrupted"] = pending.primary is not None
            report["passed"] = (
                report["passed"] and report["cleanup_complete"] and not report["interrupted"]
            )
            (output / summary_name).write_text(json.dumps(report, indent=2) + "\n")

        try:
            pending.retry(save)
            # A SIGINT handler can run during the successful write without
            # raising. Persist that newly deferred interruption as well.
            if report["interrupted"] != (pending.primary is not None):
                pending.retry(save)
        except Exception:
            if pending.primary is None:
                raise SmokeError("Owned cleanup summary could not be saved") from None
            pending.primary.add_note(
                "Owned cleanup summary could not be saved; use ownership.json for recovery"
            )
            print("Owned cleanup summary could not be saved", file=sys.stderr)
        if pending.primary is not None and not report["cleanup_complete"]:
            pending.primary.add_note(
                "Owned cleanup incomplete; use --cleanup with the artifact directory"
            )
    if pending.primary is not None:
        raise pending.primary


def write_ownership(output: Path, owner: str, resources: list[tuple[str, str]]) -> None:
    """Publish a complete same-directory record before any resource creation.

    An interrupted temporary write leaves the previous valid ledger untouched.
    Records retain attempted IDs after cleanup, so a failed removal is recoverable.
    """
    temporary = output / (".ownership-" + uuid.uuid4().hex + ".tmp")
    created = False
    pending = DeferredInterrupts()
    try:
        with temporary.open("x", encoding="utf-8") as destination:
            created = True
            os.fchmod(destination.fileno(), 0o600)
            destination.write(json.dumps({"owner": owner, "resources": resources}))
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output / "ownership.json")
    except BaseException as error:
        pending.remember(error)
    finally:
        with pending.hold():
            if created:
                try:
                    pending.retry(lambda: temporary.unlink(missing_ok=True))
                except Exception:
                    if pending.primary is None:
                        pending.remember(SmokeError("Temporary ownership record removal failed"))
                    else:
                        pending.primary.add_note("Temporary ownership record removal failed")
    if pending.primary is not None:
        raise pending.primary


def run_smoke(
    path: Path | None = None,
    *,
    provision: bool = False,
    model: str = DEFAULT_MODEL,
    parallel: bool = False,
    server_image: str | None = None,
    server_port: int = 8765,
    allow_opaque: bool = False,
    allow_hosted_tools: bool = False,
    gateway_runtime_image: str | None = None,
    gateway_freeze: Path | None = None,
    gateway_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    require(model in MODELS, "Select an explicitly supported synthetic model")
    require(type(server_port) is int and 1024 <= server_port <= 65535, "Invalid test-server port")
    require(
        server_image is None or re.fullmatch(r"sha256:[0-9a-f]{64}", server_image),
        "Test server must be a local immutable image ID",
    )
    require(
        type(allow_opaque) is bool and type(allow_hosted_tools) is bool,
        "Consent must be explicit booleans",
    )
    gateway = gateway_runtime_image is not None
    require(
        gateway or (gateway_freeze is None and gateway_freeze_sha256 is None),
        "Gateway freeze requires a supplied runtime image",
    )
    frozen = None
    if gateway:
        require(
            server_image is None and server_port == 8765,
            "Choose the owned Gateway peer or a supplied peer, not both",
        )
        require(
            re.fullmatch(r"sha256:[0-9a-f]{64}", gateway_runtime_image or ""),
            "Gateway runtime must be a local immutable image ID",
        )
        require(
            allow_opaque and allow_hosted_tools,
            "Full Codex Gateway profile requires --allow-opaque and --allow-hosted-tools",
        )
        require(
            gateway_freeze is not None and gateway_freeze_sha256 is not None,
            "Gateway execution awaits a reviewed source freeze and its SHA256",
        )
        assert gateway_freeze is not None and gateway_freeze_sha256 is not None
        frozen = reviewed_sources(gateway_freeze, gateway_freeze_sha256)
    consent = {"allow_opaque": allow_opaque, "allow_hosted_tools": allow_hosted_tools}
    output = artifact_directory(path)
    owner, count = "g7-codex-" + uuid.uuid4().hex[:12], 2 if parallel else 1
    network, image = owner + "-internal", owner + ":verification"
    resources: list[tuple[str, str]] = []
    report: dict[str, Any] = {
        "scope": "gateway_container"
        if gateway
        else "supplied_test_server"
        if server_image
        else "synthetic_transport",
        "gateway_policy_checks": "not_run",
        "model": model,
        "codex_version": VERSION,
        "consent": consent,
        "billing_requests": 0,
        "artifacts": str(output),
        "passed": False,
        "isolation_limit": "Docker host/kernel and bridge-host reachability remain trusted",
    }
    primary: BaseException | None = None

    def track(kind, identity):
        resources.append((kind, identity))
        write_ownership(output, owner, resources)

    try:
        if inspect("image", BASE_IMAGE, missing_ok=True) is None:
            require(provision, "Pinned base image missing; use --provision to allow its download")
            docker(["pull", BASE_IMAGE], timeout=300)
        if server_image:
            peer = inspect("image", server_image)
            require(
                peer.get("Config", {}).get("Labels", {}).get(PEER_LABEL) == "1",
                "Image is not marked as a synthetic Responses test peer",
            )
            verify_peer_base(peer)
        if gateway_runtime_image:
            verify_peer_base(inspect("image", gateway_runtime_image))
        context = output / "context"
        write_context(
            context, model, count, allow_opaque=allow_opaque, allow_hosted_tools=allow_hosted_tools
        )
        require(inspect("image", image, missing_ok=True) is None, "Image tag is already in use")
        track("image", image)
        built = docker(build_command(owner, context, provision=provision), timeout=600, check=False)
        (output / "build.txt").write_text(built.stdout + built.stderr)
        require(
            built.returncode == 0,
            "Offline build failed; use --provision only to fetch pinned tools",
        )
        built_image = inspect("image", image)
        require(built_image is not None, "Built image unavailable")
        require(
            built_image.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == owner,
            "Built image ownership mismatch",
        )
        image_id = built_image["Id"]
        if gateway_runtime_image:
            assert frozen is not None
            peer_context = output / "gateway-context"
            write_gateway_context(
                peer_context,
                gateway_runtime_image,
                frozen,
                {
                    "model": model,
                    "count": count,
                    "marker": MARKER,
                    "opaque": OPAQUE,
                    "arguments": TOOL_ARGUMENTS,
                    "consent": consent,
                    "source_freeze_sha256": gateway_freeze_sha256,
                },
            )
            peer_tag = owner + ":gateway"
            require(
                inspect("image", peer_tag, missing_ok=True) is None,
                "Gateway image tag is already in use",
            )
            track("image", peer_tag)
            built = docker(
                build_command(owner, peer_context, provision=False, gateway=True),
                timeout=60,
                check=False,
            )
            (output / "gateway-build.txt").write_text(built.stdout + built.stderr)
            require(built.returncode == 0, "Offline Gateway peer overlay build failed")
            peer = inspect("image", peer_tag)
            require(
                peer.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == owner,
                "Gateway peer image ownership mismatch",
            )
            server_image = peer["Id"]
            report["source_freeze_sha256"] = gateway_freeze_sha256
            report["gateway_runtime_image"] = gateway_runtime_image
        track("network", network)
        docker(
            [
                "network",
                "create",
                "--internal",
                "--label",
                OWNER_LABEL + "=" + owner,
                "--opt",
                "com.docker.network.bridge.enable_ip_masquerade=false",
                network,
            ]
        )
        net = inspect("network", network)
        require(
            net is not None
            and net["Internal"]
            and not net["EnableIPv6"]
            and net.get("Options", {}).get("com.docker.network.bridge.enable_ip_masquerade")
            == "false",
            "Network is not private IPv4 without masquerading",
        )

        def create(role, selected_image, command):
            name = owner + "-" + role
            track("container", name)
            docker(container_command(owner, network, selected_image, role, command))
            item = inspect("container", name)
            require(item is not None, "Container unavailable")
            verify_container(item, network)
            (output / (role + "-isolation.json")).write_text(
                json.dumps(item["HostConfig"], indent=2)
            )
            return name

        server = create("server", server_image or image_id, [])
        docker(["start", server])
        peer = inspect("container", server)
        require(peer is not None, "Test server unavailable")
        attached = peer["NetworkSettings"]["Networks"]
        require(set(attached) == {network}, "Test server has another network")
        address = ipaddress.ip_address(attached[network]["IPAddress"])
        require(
            address.version == 4 and address.is_private and not address.is_loopback,
            "Test server address is not private IPv4",
        )
        port = server_port if server_image else 8765
        client = create(
            "client",
            image_id,
            ["node", "/opt/harness/harness.mjs", "client", f"http://{address}:{port}/v1"],
        )
        result = docker(["start", "--attach", client], timeout=90, check=False)
        (output / "client.jsonl").write_text(result.stdout)
        (output / "client-stderr.txt").write_text(result.stderr)
        server_logs = docker(["logs", server]).stdout
        (output / "server.jsonl").write_text(server_logs)
        require(result.returncode == 0, "Client container failed")
        report["features"] = verify_cycle(
            records(result.stdout), records(server_logs), model, count
        )
        if gateway:
            report["gateway_policy_checks"] = verify_gateway(
                records(server_logs), gateway_freeze_sha256 or "", consent
            )
        report["passed"] = True
    except Exception as error:
        report["failure"] = str(error) if isinstance(error, SmokeError) else "Verification failed"
    except BaseException as error:
        primary = error
        report["passed"] = False
        report["failure"] = "Verification interrupted"
    finally:
        finish_cleanup(output, owner, resources, report, primary)
    return report


# Generated only into an isolated temporary build context, never into the checkout.
CONTAINER_SOURCE = r"""
import fs from 'node:fs';
import net from 'node:net';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn, execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
const C = __CONFIG__;
const emit = value => console.log(JSON.stringify(value));
const ensure = value => { if (!value) throw Error('synthetic_verification_failed'); };
const mode = process.argv[2];
function provenance() {
  const require = createRequire('/opt/codex/node_modules/@openai/codex/package.json');
  const pkg = require('/opt/codex/node_modules/@openai/codex/package.json');
  const native = '@openai/codex-linux-' + process.arch;
  const nativeRoot = require.resolve(native + '/package.json').replace(/\/package.json$/, '');
  const lock = JSON.parse(fs.readFileSync('/opt/codex/package-lock.json'));
  const wrapperIntegrity = lock.packages['node_modules/@openai/codex'].integrity;
  const nativeIntegrity = lock.packages['node_modules/' + native].integrity;
  ensure(process.platform === 'linux' && pkg.version === C.version && C.native[process.arch]
    && wrapperIntegrity === C.wrapper && nativeIntegrity === C.native[process.arch]);
  const target = process.arch === 'arm64' ? 'aarch64-unknown-linux-musl' : 'x86_64-unknown-linux-musl';
  const binary = nativeRoot + '/vendor/' + target + '/bin/codex';
  return {package_version: pkg.version, arch: process.arch, wrapper_integrity: wrapperIntegrity,
    native_integrity: nativeIntegrity, binary_sha256: crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex')};
}
async function guard() {
  const status = fs.readFileSync('/proc/self/status', 'utf8');
  const routes = fs.readFileSync('/proc/net/route', 'utf8');
  let readonly = false;
  try { fs.writeFileSync('/var/tmp/gateway7-write-probe', 'synthetic'); }
  catch (error) { readonly = error.code === 'EROFS'; }
  const egress = await new Promise(resolve => {
    const socket = net.createConnection({host: '192.0.2.1', port: 443});
    socket.setTimeout(1000);
    socket.on('connect', () => { socket.destroy(); resolve('connected'); });
    socket.on('error', error => resolve(error.code));
    socket.on('timeout', () => { socket.destroy(); resolve('timeout'); });
  });
  const checks = {non_root: process.getuid() === 1000, rootfs_read_only: readonly,
    no_default_route: !routes.trim().split('\n').slice(1).some(x => x.split(/\s+/)[1] === '00000000'),
    egress_blocked: egress === 'ENETUNREACH', zero_capabilities: /^CapEff:\s+0+$/m.test(status),
    no_new_privileges: /^NoNewPrivs:\s+1$/m.test(status), seccomp: /^Seccomp:\s+2$/m.test(status),
    no_docker_socket: !fs.existsSync('/var/run/docker.sock')};
  emit({kind: 'runtime', ...checks});
  ensure(Object.values(checks).every(Boolean));
}
function response(body, output, turn, status = 'completed') {
  return {id: 'resp_synthetic_' + turn, object: 'response', created_at: 1800000000, access_programs: null,
    status, model: body.model, instructions: body.instructions, output, error: null, incomplete_details: null,
    parallel_tool_calls: true, store: false, previous_response_id: null, reasoning: body.reasoning,
    temperature: null, top_p: null, text: body.text ?? {format: {type: 'text'}}, tool_choice: 'auto',
    tools: body.tools, metadata: {}, usage: status === 'completed' ? {input_tokens: 40,
      input_tokens_details: {cached_tokens: 5, cache_write_tokens: 0}, output_tokens: 10,
      output_tokens_details: {reasoning_tokens: 3}, total_tokens: 50} : null};
}
function events(body, turn) {
  const list = [], output = [];
  const add = (type, fields) => list.push({type, sequence_number: list.length, ...fields});
  add('response.created', {response: response(body, [], turn, 'in_progress')});
  add('response.in_progress', {response: response(body, [], turn, 'in_progress')});
  if (turn === 1) {
    const reasoning = {type: 'reasoning', id: 'rs_synthetic', summary: [], encrypted_content: C.opaque};
    add('response.output_item.added', {output_index: 0, item: {...reasoning, encrypted_content: null}});
    add('response.output_item.done', {output_index: 0, item: reasoning}); output.push(reasoning);
    for (let i = 0; i < C.count; i++) {
      const item = {type: 'function_call', id: 'fc_' + i, call_id: 'call_read_' + i,
        name: 'exec_command', arguments: C.arguments, status: 'completed'};
      add('response.output_item.added', {output_index: i + 1, item: {...item, arguments: '', status: 'in_progress'}});
      add('response.function_call_arguments.delta', {output_index: i + 1, item_id: item.id, delta: C.arguments});
      add('response.function_call_arguments.done', {output_index: i + 1, item_id: item.id, arguments: C.arguments});
      add('response.output_item.done', {output_index: i + 1, item}); output.push(item);
    }
  } else {
    const part = {type: 'output_text', text: C.marker, annotations: [], logprobs: []};
    const item = {type: 'message', id: 'msg_synthetic', role: 'assistant', status: 'completed',
      phase: 'final_answer', content: [part]};
    add('response.output_item.added', {output_index: 0, item: {...item, content: [], status: 'in_progress'}});
    add('response.content_part.added', {output_index: 0, item_id: item.id, content_index: 0, part: {...part, text: ''}});
    add('response.output_text.delta', {output_index: 0, item_id: item.id, content_index: 0, delta: C.marker, logprobs: []});
    add('response.output_text.done', {output_index: 0, item_id: item.id, content_index: 0, text: C.marker, logprobs: []});
    add('response.content_part.done', {output_index: 0, item_id: item.id, content_index: 0, part});
    add('response.output_item.done', {output_index: 0, item}); output.push(item);
  }
  add('response.completed', {response: response(body, output, turn)}); return list;
}
function validateStream(bytes) {
  const fragments = new Map(), checked = []; let completed = false;
  const allowed = new Set(['response.created', 'response.in_progress', 'response.output_item.added',
    'response.output_item.done', 'response.function_call_arguments.delta', 'response.function_call_arguments.done',
    'response.content_part.added', 'response.content_part.done', 'response.output_text.delta', 'response.output_text.done',
    'response.reasoning_summary_part.added', 'response.reasoning_summary_part.done',
    'response.reasoning_summary_text.delta', 'response.reasoning_summary_text.done', 'response.completed']);
  function item(value, added = false) {
    ensure(value && ['message', 'reasoning', 'function_call'].includes(value.type));
    if (value.type === 'function_call') {
      ensure(Object.keys(value).every(key => ['type', 'id', 'call_id', 'name', 'arguments', 'status', 'namespace'].includes(key))
        && value.name === 'exec_command' && [undefined, null, 'functions'].includes(value.namespace)
        && Array.from({length: C.count}, (_, i) => 'call_read_' + i).includes(value.call_id)
        && (added ? [undefined, null, 'in_progress'].includes(value.status) : [undefined, null, 'completed'].includes(value.status))
        && (value.arguments === C.arguments || (added && value.arguments === '')));
    }
  }
  for (const frame of bytes.toString('utf8').split(/\r?\n\r?\n/)) {
    const data = frame.split(/\r?\n/).filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
    if (!data) continue;
    ensure(!completed);
    const event = JSON.parse(data), type = event.type;
    ensure(allowed.has(type) && event.sequence_number === checked.length);
    if (type === 'response.output_item.added' || type === 'response.output_item.done')
      item(event.item, type === 'response.output_item.added');
    if (type === 'response.function_call_arguments.delta') {
      ensure(typeof event.delta === 'string');
      const value = (fragments.get(event.item_id) ?? '') + event.delta;
      ensure(C.arguments.startsWith(value)); fragments.set(event.item_id, value);
    }
    if (type === 'response.function_call_arguments.done') ensure(event.arguments === C.arguments);
    if (event.response) {
      ensure(Array.isArray(event.response.output));
      for (const value of event.response.output) item(value);
    }
    if (type === 'response.completed') {
      ensure(event.response?.status === 'completed' && event.response.output.length > 0);
      completed = true;
    }
    checked.push(event);
  }
  ensure(completed);
  // Re-encode the inspected objects, so duplicate JSON keys or mismatched SSE
  // event labels cannot mean something else to the native client's parser.
  return Buffer.from(checked.map(e => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join(''));
}
function consentHeaders() {
  return {...(C.allow_opaque ? {'x-gateway7-allow-opaque': 'true'} : {}),
    ...(C.allow_hosted_tools ? {'x-gateway7-allow-hosted-tools': 'true'} : {})};
}
async function safetyProxy(peer) {
  let forwarded = 0;
  const proxy = http.createServer({maxHeaderSize: 16384, requestTimeout: 10000}, (req, res) => {
    if (req.method !== 'POST' || req.url !== '/v1/responses' || forwarded++ >= 2) {
      res.writeHead(400).end(); return;
    }
    let size = 0, parts = [];
    req.on('data', chunk => { size += chunk.length; if (size > 262144) req.destroy(); else parts.push(chunk); });
    req.on('end', async () => {
      const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 65000);
      res.once('close', () => abort.abort());
      try {
        const upstream = await fetch(peer + '/responses', {method: 'POST', redirect: 'error',
          headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + C.client_token, ...consentHeaders()},
          body: Buffer.concat(parts), signal: abort.signal});
        // Only the expected success status is eligible for tool delivery. Reject
        // all other statuses before even reading an untrusted response body.
        ensure(upstream.status === 200);
        ensure(upstream.headers.get('content-type')?.split(';')[0].trim() === 'text/event-stream');
        const received = []; let length = 0;
        for await (const chunk of upstream.body) { length += chunk.length; ensure(length <= 1048576); received.push(chunk); }
        const bytes = validateStream(Buffer.concat(received));
        res.writeHead(200, {'Content-Type': 'text/event-stream'});
        res.end(bytes);
      } catch { emit({kind: 'safety_rejection'}); if (!res.headersSent) res.writeHead(502).end(); }
      finally { abort.abort(); clearTimeout(timer); }
    });
  });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  return {proxy, base: 'http://127.0.0.1:' + proxy.address().port + '/v1'};
}
async function server() {
  let turn = 0;
  const instance = http.createServer({maxHeaderSize: 16384, requestTimeout: 10000}, (req, res) => {
    if (req.method === 'GET' && req.url === '/health') { res.end('ready'); return; }
    if (req.method !== 'POST' || req.url !== '/v1/responses' || turn >= 2 ||
        req.headers.authorization !== 'Bearer ' + C.client_token) { emit({kind: 'failure'}); res.writeHead(400).end(); return; }
    let size = 0, chunks = [];
    req.on('data', chunk => { size += chunk.length; if (size > 262144) req.destroy(); else chunks.push(chunk); });
    req.on('end', () => {
      try {
        const body = JSON.parse(Buffer.concat(chunks));
        ensure(body.model === C.model && body.stream === true && body.store === false && body.parallel_tool_calls === true
          && body.tools.some(t => t.type === 'function' && t.name === 'exec_command'));
        if (turn === 1) for (let i = 0; i < C.count; i++) {
          const outputs = body.input.filter(x => x.type === 'function_call_output' && x.call_id === 'call_read_' + i);
          ensure(outputs.length === 1 && typeof outputs[0].output === 'string' &&
            outputs[0].output.includes('Process exited with code 0\n') &&
            outputs[0].output.endsWith('\nOutput:\n' + C.marker + '\n'));
        }
        turn++; emit({kind: 'capture', turn, body});
        res.writeHead(200, {'Content-Type': 'text/event-stream'});
        for (const item of events(body, turn)) res.write(`event: ${item.type}\ndata: ${JSON.stringify(item)}\n\n`);
        res.end();
      } catch { emit({kind: 'failure'}); res.writeHead(400).end(); }
    });
  });
  instance.listen(8765, '0.0.0.0');
  setTimeout(() => instance.close(() => process.exit(0)), 180000).unref();
}
async function client() {
  const base = process.argv[3];
  ensure(/^http:\/\/[0-9.]+:[0-9]+\/v1$/.test(base));
  for (const name of ['home', 'codex', 'config', 'data', 'cache', 'state', 'tmp', 'work'])
    fs.mkdirSync('/run/test/' + name, {recursive: true, mode: 0o700});
  fs.writeFileSync('/run/test/work/synthetic-read.txt', C.marker + '\n', {mode: 0o444});
  const env = {PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/run/test/home', CODEX_HOME: '/run/test/codex',
    XDG_CONFIG_HOME: '/run/test/config', XDG_DATA_HOME: '/run/test/data', XDG_CACHE_HOME: '/run/test/cache',
    XDG_STATE_HOME: '/run/test/state', TMPDIR: '/run/test/tmp', SHELL: '/bin/sh', LANG: 'C.UTF-8',
    TERM: 'dumb', GATEWAY7_SYNTHETIC_CREDENTIAL: C.client_token};
  const executable = '/opt/codex/node_modules/.bin/codex', cwd = '/run/test/work';
  const current = provenance(), built = JSON.parse(fs.readFileSync('/opt/harness/provenance.json'));
  ensure(current.binary_sha256 === built.binary_sha256);
  const version = execFileSync(executable, ['--version'], {env, cwd, encoding: 'utf8', timeout: 10000}).trim();
  ensure(version === 'codex-cli ' + C.version);
  emit({kind: 'provenance', ...current, version});
  let ready = false;
  for (let n = 0; n < 100 && !ready; n++) {
    try { ready = (await fetch(new URL('/health', base), {signal: AbortSignal.timeout(500)})).ok; } catch {}
    if (!ready) await new Promise(resolve => setTimeout(resolve, 100));
  }
  ensure(ready);
  emit({kind: 'consent', allow_opaque: C.allow_opaque, allow_hosted_tools: C.allow_hosted_tools});
  const safety = await safetyProxy(base);
  const provider = `model_providers.gateway7={name="Synthetic fixture",base_url="${safety.base}",env_key="GATEWAY7_SYNTHETIC_CREDENTIAL",wire_api="responses",request_max_retries=0,stream_max_retries=0}`;
  const args = ['exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check', '--json',
    '--sandbox', 'danger-full-access', '-c', 'approval_policy="never"', '-c', 'model_provider="gateway7"',
    '-c', provider, '-m', C.model, 'Read only /run/test/work/synthetic-read.txt and return its control string.'];
  const child = spawn(executable, args, {env, cwd, detached: true, stdio: ['ignore', 'pipe', 'pipe']});
  let stdout = '', stderr = '', timedOut = false, overflow = false;
  const kill = () => { try { process.kill(-child.pid, 'SIGKILL'); } catch {} };
  const timer = setTimeout(() => { timedOut = true; kill(); }, 60000);
  process.on('SIGTERM', kill);
  child.stdout.on('data', x => { stdout += x; if (stdout.length > 1048576) { overflow = true; kill(); } });
  child.stderr.on('data', x => { stderr += x; if (stderr.length > 65536) { overflow = true; kill(); } });
  const code = await new Promise((resolve, reject) => { child.on('close', resolve); child.on('error', reject); });
  clearTimeout(timer);
  safety.proxy.closeAllConnections(); safety.proxy.close();
  for (const line of stdout.trim().split('\n').filter(Boolean)) emit({kind: 'codex', event: JSON.parse(line)});
  emit({kind: 'exit', code, timed_out: timedOut, overflow});
  process.exitCode = code === 0 && !timedOut && !overflow ? 0 : 1;
}
if (mode === 'verify') fs.writeFileSync('/opt/harness/provenance.json', JSON.stringify(provenance()));
else if (mode === 'validate') { validateStream(fs.readFileSync(0)); emit({validated: true}); }
else if (mode === 'headers') emit(consentHeaders());
else { await guard(); if (mode === 'server') await server(); else if (mode === 'client') await client(); else ensure(false); }
"""


def write_context(
    context: Path,
    model: str,
    count: int,
    *,
    allow_opaque: bool = False,
    allow_hosted_tools: bool = False,
) -> None:
    require(
        model in MODELS and type(count) is int and count in (1, 2),
        "Select one or two fixed reads and an explicit synthetic model",
    )
    require(
        type(allow_opaque) is bool and type(allow_hosted_tools) is bool,
        "Consent must be explicit booleans",
    )
    context.mkdir(mode=0o700)
    config = {
        "version": VERSION,
        "wrapper": WRAPPER_INTEGRITY,
        "native": NATIVE_INTEGRITY,
        "model": model,
        "count": count,
        "marker": MARKER,
        "opaque": OPAQUE,
        "arguments": TOOL_ARGUMENTS,
        "client_token": CLIENT_TOKEN,
        "allow_opaque": allow_opaque,
        "allow_hosted_tools": allow_hosted_tools,
    }
    (context / "harness.mjs").write_text(CONTAINER_SOURCE.replace("__CONFIG__", json.dumps(config)))
    (context / ".dockerignore").write_text("*\n!Dockerfile\n!harness.mjs\n")
    (context / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\n"
        'RUN ["npm", "install", "--prefix", "/opt/codex", "--registry=https://registry.npmjs.org", '
        f'"--ignore-scripts", "--no-audit", "--no-fund", "@openai/codex@{VERSION}"]\n'
        "COPY harness.mjs /opt/harness/harness.mjs\n"
        'RUN ["node", "/opt/harness/harness.mjs", "verify"]\n'
        "USER 1000:1000\n"
        'CMD ["node", "/opt/harness/harness.mjs", "server"]\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--provision", action="store_true", help="Allow only pinned public tool downloads"
    )
    parser.add_argument("--model", choices=MODELS, default=DEFAULT_MODEL)
    parser.add_argument(
        "--parallel", action="store_true", help="Emit two fixed reads, not another model"
    )
    parser.add_argument("--artifacts", type=Path, help="New directory outside the checkout")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--server-image", help="Existing local sha256 image ID for a synthetic Gateway test peer"
    )
    parser.add_argument("--server-port", type=int, default=8765)
    parser.add_argument(
        "--allow-opaque",
        action="store_true",
        help="Explicitly forward synthetic opaque-history consent",
    )
    parser.add_argument(
        "--allow-hosted-tools",
        action="store_true",
        help="Explicitly permit hosted-tool advertisement, never execution",
    )
    mode.add_argument(
        "--gateway-runtime-image", help="Existing immutable Python dependency image with /opt/venv"
    )
    parser.add_argument(
        "--gateway-freeze", type=Path, help="Reviewed allowlisted-source hash manifest"
    )
    parser.add_argument(
        "--gateway-freeze-sha256", help="Exact manifest SHA256 approved at source freeze"
    )
    mode.add_argument(
        "--write-gateway-freeze",
        type=Path,
        help="Write a candidate manifest only; no Docker execution or approval",
    )
    mode.add_argument(
        "--cleanup", type=Path, help="Recover only labelled resources in this artifact directory"
    )
    args = parser.parse_args()
    try:
        if args.write_gateway_freeze:
            print(json.dumps(write_gateway_freeze(args.write_gateway_freeze), indent=2))
            return
        if args.cleanup:
            with (args.cleanup / "ownership.json").open("rb") as source:
                data = source.read(16_385)
            require(len(data) <= 16_384, "Ownership manifest exceeds its bound")
            manifest = json.loads(data)
            require(
                isinstance(manifest["owner"], str)
                and isinstance(manifest["resources"], list)
                and len(manifest["resources"]) <= 5,
                "Invalid ownership manifest",
            )
            report = {"passed": True}
            finish_cleanup(
                args.cleanup,
                manifest["owner"],
                [tuple(x) for x in manifest["resources"]],
                report,
                summary_name="cleanup-summary.json",
            )
        else:
            report = run_smoke(
                args.artifacts,
                provision=args.provision,
                model=args.model,
                parallel=args.parallel,
                server_image=args.server_image,
                server_port=args.server_port,
                allow_opaque=args.allow_opaque,
                allow_hosted_tools=args.allow_hosted_tools,
                gateway_runtime_image=args.gateway_runtime_image,
                gateway_freeze=args.gateway_freeze,
                gateway_freeze_sha256=args.gateway_freeze_sha256,
            )
    except (SmokeError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(
            1, (str(error) if isinstance(error, SmokeError) else "Invalid smoke invocation") + "\n"
        )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

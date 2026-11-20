"""Test-only Gateway peer, copied into a disposable allowlisted container context.

Never launch this server on the host. The controller supplies scenario.json and
the frozen package; this module does not discover configuration or credentials.
Imports of product/runtime dependencies are deliberately deferred until startup.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib
from importlib.machinery import ModuleSpec, SourceFileLoader
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType
from typing import Any

BLOCKED = "GATEWAY7_BLOCKED_ARGUMENT"
REDACT = "GATEWAY7_REDACT_ME"
CONTACT = "fixture@example.invalid +7 000 000-00-00"
MASKED = "[EMAIL] [PHONE]"
PROVIDER_KEY = "gateway7-synthetic-provider-only"
CLIENT_TOKEN = "gateway7-synthetic-codex-client"
BYTECODE_PREFIX = "/run/test/gateway7-bytecode"
CHECKS = (
    "auth_denied",
    "model_denied",
    "request_denied",
    "opaque_default_denied",
    "hosted_default_denied",
    "request_redacted",
    "response_arguments_denied",
    "response_redacted",
)


def require(value: object, reason: str) -> None:
    if not value:
        raise RuntimeError(reason)


def emit(record: dict) -> None:
    print(json.dumps(record, separators=(",", ":")), flush=True)


def verify_private_bytecode_cache() -> None:
    """The process-start -X flag covers imports during site/.pth startup too.

    /run/test is a new private tmpfs for each container. With -B this prefix stays
    absent or empty; inherited image caches are never lookup candidates.
    """
    require(
        sys.pycache_prefix == BYTECODE_PREFIX and sys.dont_write_bytecode,
        "private_bytecode_cache_required",
    )
    cache = Path(BYTECODE_PREFIX)
    require(
        not cache.exists() or (cache.is_dir() and not any(cache.iterdir())),
        "private_bytecode_cache_not_empty",
    )


def verify_gateway_imports(
    root: Path,
    files: dict[str, str],
    *,
    modules: dict | None = None,
) -> dict[str, str]:
    """Bind every loaded product module to its frozen source, not sys.path order.

    Do not read a claimed installed origin: only allowlisted overlay files are
    hashed. Failures contain no arbitrary paths, module names or source contents.
    """
    try:
        root = root.resolve()
        verified = {}
        loaded = dict(sys.modules if modules is None else modules)
        for name, module in loaded.items():
            if name != "gateway7" and not name.startswith("gateway7."):
                continue
            require(type(module) is ModuleType, "invalid_module")
            state = vars(module)
            stem = name.replace(".", "/")
            package = stem + "/__init__.py" in files
            relative = stem + ("/__init__.py" if package else ".py")
            require(relative in files, "unlisted_module")
            expected = root / relative
            require(expected.resolve() == expected, "symlink_origin")
            spec = state.get("__spec__")
            if type(spec) is not ModuleSpec:
                raise RuntimeError("unexpected_spec")
            loader = spec.loader
            require(state.get("__loader__") is spec.loader, "unexpected_bound_loader")
            if loader is None or type(loader) is not SourceFileLoader:
                raise RuntimeError("unexpected_loader")
            require(
                spec.name == name
                and spec.has_location
                and spec.origin == str(expected)
                and state.get("__file__") == str(expected)
                and loader.path == str(expected)
                and loader.name == name,
                "unexpected_origin",
            )
            if package:
                search = [str(expected.parent)]
                require(
                    state.get("__path__") == search and spec.submodule_search_locations == search,
                    "unexpected_package_search_path",
                )
            else:
                require(
                    "__path__" not in state and spec.submodule_search_locations is None,
                    "unexpected_module_search_path",
                )
            digest = hashlib.sha256(expected.read_bytes()).hexdigest()
            require(digest == files[relative], "source_hash_mismatch")
            verified[name] = digest
        return verified
    except Exception:
        raise RuntimeError("gateway_import_verification_failed") from None


def runtime_guard() -> dict:
    status = Path("/proc/self/status").read_text()
    routes = Path("/proc/net/route").read_text().splitlines()[1:]
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    readonly = False
    try:
        Path("/var/tmp/gateway7-write-probe").write_text("synthetic")
    except OSError as error:
        import errno

        readonly = error.errno == errno.EROFS
    blocked = False
    with socket.socket() as probe:
        probe.settimeout(1)
        try:
            probe.connect(("192.0.2.1", 443))
        except OSError as error:
            import errno

            blocked = error.errno == errno.ENETUNREACH
    return {
        "kind": "runtime",
        "non_root": os.getuid() == 1000,
        "rootfs_read_only": readonly,
        "no_default_route": not any(line.split()[1] == "00000000" for line in routes),
        "egress_blocked": blocked,
        "zero_capabilities": int(fields["CapEff"], 16) == 0,
        "no_new_privileges": fields["NoNewPrivs"].strip() == "1",
        "seccomp": fields["Seccomp"].strip() == "2",
        "no_docker_socket": not Path("/var/run/docker.sock").exists(),
    }


def forbid_external_sockets(event: str, args: tuple) -> None:
    if event == "socket.connect":
        address = args[1]
        require(
            isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback,
            "peer_external_socket_forbidden",
        )


def gateway_config(model: str) -> dict:
    return {
        "provider": {
            "kind": "openai",
            "model": model,
            "key_env": "GATEWAY7_SYNTHETIC_PROVIDER",
            "timeout_seconds": 5.0,
        },
        "auth": {
            "enabled": True,
            "clients": {"synthetic": {"token_env": "GATEWAY7_SYNTHETIC_CLIENT", "models": [model]}},
        },
        "limits": {"max_body_bytes": 262144, "request_timeout_seconds": 8.0},
        "plugins": {
            "guard": {
                "module": "gateway7.plugins.content_policy",
                "required": True,
                "settings": {"terms": [BLOCKED], "phase": "both", "action": "block"},
            },
            "redact": {
                "module": "gateway7.plugins.content_policy",
                "required": True,
                "settings": {"terms": [REDACT], "phase": "response", "action": "redact"},
            },
            "email": {
                "module": "gateway7.plugins.email_mask",
                "required": True,
                "settings": {"phase": "both"},
            },
            "phone": {
                "module": "gateway7.plugins.phone_mask",
                "required": True,
                "settings": {"phase": "both"},
            },
        },
        "middleware": ["guard", "redact", "email", "phone"],
    }


def message(text: str) -> dict:
    return {
        "type": "message",
        "id": "msg_synthetic",
        "role": "assistant",
        "status": "completed",
        "phase": "final_answer",
        "content": [{"type": "output_text", "text": text, "annotations": [], "logprobs": []}],
    }


def output_items(config: dict, turn: int) -> list[dict]:
    if turn == 2:
        return [message(config["marker"])]
    return [
        {
            "type": "reasoning",
            "id": "rs_synthetic",
            "summary": [],
            "encrypted_content": config["opaque"],
        },
        *[
            {
                "type": "function_call",
                "id": f"fc_{index}",
                "call_id": f"call_read_{index}",
                "name": "exec_command",
                "arguments": config["arguments"],
                "status": "completed",
            }
            for index in range(config["count"])
        ],
    ]


def envelope(body: dict, output: list[dict], turn: int, status: str = "completed") -> dict:
    return {
        "id": f"resp_synthetic_{turn}",
        "object": "response",
        "created_at": 1800000000.0,
        "model": body["model"],
        "status": status,
        "output": deepcopy(output),
        "store": False,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": body.get("tools", []),
        "usage": {
            "input_tokens": 40,
            "output_tokens": 10,
            "total_tokens": 50,
            "input_tokens_details": {"cached_tokens": 5, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 3},
        }
        if status == "completed"
        else None,
    }


def event_bytes(body: dict, output: list[dict], turn: int) -> bytes:
    """Independent synthetic wire events; the production provider must parse these."""
    events: list[dict] = []

    def add(kind: str, **fields: Any) -> None:
        events.append({"type": kind, "sequence_number": len(events), **fields})

    add("response.created", response=envelope(body, [], turn, "in_progress"))
    add("response.in_progress", response=envelope(body, [], turn, "in_progress"))
    for index, item in enumerate(output):
        initial = deepcopy(item)
        if item["type"] == "function_call":
            initial.update(arguments="", status="in_progress")
        elif item["type"] == "reasoning":
            initial["encrypted_content"] = None
        else:
            initial.update(content=[], status="in_progress")
        add("response.output_item.added", output_index=index, item=initial)
        ref = {"output_index": index, "item_id": item["id"]}
        if item["type"] == "function_call":
            add("response.function_call_arguments.delta", **ref, delta=item["arguments"])
            add("response.function_call_arguments.done", **ref, arguments=item["arguments"])
        elif item["type"] == "message":
            part = item["content"][0]
            add("response.content_part.added", **ref, content_index=0, part={**part, "text": ""})
            add(
                "response.output_text.delta",
                **ref,
                content_index=0,
                delta=part["text"],
                logprobs=[],
            )
            add("response.output_text.done", **ref, content_index=0, text=part["text"], logprobs=[])
            add("response.content_part.done", **ref, content_index=0, part=part)
        add("response.output_item.done", output_index=index, item=item)
    add("response.completed", response=envelope(body, output, turn))
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def assert_native(body: dict, model: str) -> None:
    require(
        body.get("model") == model
        and body.get("store") is False
        and type(body.get("stream")) is bool
        and isinstance(body.get("input"), (list, str))
        and not {"messages", "allow_opaque", "allow_hosted", "consent"} & body.keys(),
        "native_upstream_contract_changed",
    )


def assert_replay(body: dict, config: dict) -> None:
    history = body["input"]
    require(isinstance(history, list), "native_history_missing")
    calls = [item for item in history if item.get("type") == "function_call"]
    outputs = [item for item in history if item.get("type") == "function_call_output"]
    require(len(calls) == len(outputs) == config["count"], "native_history_count")
    for index in range(config["count"]):
        require(
            calls[index]["call_id"] == f"call_read_{index}"
            and calls[index]["arguments"] == config["arguments"],
            "native_call_changed",
        )
        found = [item for item in outputs if item["call_id"] == f"call_read_{index}"]
        require(
            len(found) == 1
            and "Process exited with code 0\n" in found[0]["output"]
            and found[0]["output"].endswith("\nOutput:\n" + config["marker"] + "\n"),
            "actual_tool_result_missing",
        )
    reasoning = [item for item in history if item.get("type") == "reasoning"]
    require(
        len(reasoning) == 1 and reasoning[0].get("encrypted_content") == config["opaque"],
        "opaque_history_changed",
    )


class SyntheticUpstream:
    def __init__(self, config: dict):
        self.config = config
        self.probes: list[dict] = []
        self.turn = 0

    def handle(self, request):
        import httpx

        require(
            request.method == "POST"
            and str(request.url) == "https://api.openai.com/v1/responses"
            and request.headers.get("authorization") == "Bearer " + PROVIDER_KEY
            and not any(name.startswith("x-gateway7-") for name in request.headers),
            "fixed_native_endpoint_or_headers_changed",
        )
        body = json.loads(request.content)
        assert_native(body, self.config["model"])
        probe = body.get("instructions", "")
        if probe in (
            "synthetic-request-mask",
            "synthetic-argument-block",
            "synthetic-response-mask",
        ):
            self.probes.append(body)
            emit({"kind": "preflight_capture", "probe": probe, "body": body})
            if probe == "synthetic-argument-block":
                output = [
                    {
                        "type": "function_call",
                        "id": "fc_denied",
                        "call_id": "call_denied",
                        "name": "exec_command",
                        "status": "completed",
                        "arguments": json.dumps({"cmd": BLOCKED}),
                    }
                ]
            else:
                output = [
                    message(
                        REDACT + " " + CONTACT
                        if probe == "synthetic-response-mask"
                        else self.config["marker"]
                    )
                ]
            turn = 99
        else:
            require(
                body["stream"] is True
                and body.get("parallel_tool_calls") is True
                and "reasoning.encrypted_content" in body.get("include", [])
                and any(
                    t.get("type") == "function" and t.get("name") == "exec_command"
                    for t in body.get("tools", [])
                ),
                "codex_advertisement_changed",
            )
            require(self.turn < 2, "extra_codex_request")
            if self.turn == 1:
                assert_replay(body, self.config)
            self.turn += 1
            turn, output = self.turn, output_items(self.config, self.turn)
            emit({"kind": "capture", "turn": turn, "body": body})
        if body["stream"]:
            wire = event_bytes(body, output, turn)

            class Fragments(httpx.AsyncByteStream):
                async def __aiter__(self):
                    for offset in range(0, len(wire), 113):
                        yield wire[offset : offset + 113]

            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Fragments()
            )
        return httpx.Response(200, json=envelope(body, output, turn))


async def preflight(client, upstream: SyntheticUpstream, model: str) -> dict:
    headers = {"authorization": "Bearer " + CLIENT_TOKEN}
    base = {"model": model, "input": "Synthetic", "store": False}
    passed: dict[str, bool] = {}

    async def denied(name, body, status, code, *, authenticated=True):
        before = len(upstream.probes)
        before_turn = upstream.turn
        result = await client.post(
            "/v1/responses", json=body, headers=headers if authenticated else {}
        )
        require(
            result.status_code == status
            and result.json()["error"]["code"] == code
            and result.headers["content-type"].startswith("application/json")
            and "response.output_item.done" not in result.text,
            "preflight_" + name,
        )
        require(
            len(upstream.probes) == before and upstream.turn == before_turn,
            "denied_request_reached_provider",
        )
        passed[name] = True

    await denied("auth_denied", base, 401, "unauthorized", authenticated=False)
    await denied("model_denied", {**base, "model": "synthetic-forbidden"}, 403, "model_forbidden")
    await denied("request_denied", {**base, "input": BLOCKED}, 403, "policy_denied")
    await denied(
        "opaque_default_denied",
        {**base, "include": ["reasoning.encrypted_content"]},
        400,
        "invalid_request",
    )
    await denied(
        "hosted_default_denied", {**base, "tools": [{"type": "web_search"}]}, 400, "invalid_request"
    )
    result = await client.post(
        "/v1/responses",
        headers=headers,
        json={**base, "input": CONTACT, "instructions": "synthetic-request-mask"},
    )
    require(
        result.status_code == 200
        and upstream.probes[-1]["input"] == MASKED
        and result.json()["output"][0]["type"] == "message",
        "preflight_request_redacted",
    )
    passed["request_redacted"] = True
    before = len(upstream.probes)
    result = await client.post(
        "/v1/responses",
        headers=headers,
        json={
            **base,
            "stream": True,
            "instructions": "synthetic-argument-block",
            "tools": [
                {"type": "function", "name": "exec_command", "parameters": {"type": "object"}}
            ],
        },
    )
    require(
        result.status_code == 403
        and result.json()["error"]["code"] == "policy_denied"
        and len(upstream.probes) == before + 1
        and BLOCKED not in result.text
        and "response.output_item.done" not in result.text
        and result.headers["content-type"].startswith("application/json"),
        "preflight_response_arguments_denied",
    )
    passed["response_arguments_denied"] = True
    result = await client.post(
        "/v1/responses",
        headers=headers,
        json={**base, "stream": True, "instructions": "synthetic-response-mask"},
    )
    require(
        result.status_code == 200
        and result.headers["content-type"].startswith("text/event-stream"),
        "preflight_response_redacted_status",
    )
    events = [
        json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")
    ]
    expected = "[removed] " + MASKED
    require(
        events[-1]["type"] == "response.completed"
        and "".join(e["delta"] for e in events if e["type"] == "response.output_text.delta")
        == expected
        and events[-1]["response"]["output"][0]["content"][0]["text"] == expected
        and all(raw not in result.text for raw in (REDACT, "fixture@example.invalid", "+7 000")),
        "preflight_response_redacted_snapshots",
    )
    for event in events:
        kind = event["type"]
        if kind == "response.output_text.done":
            require(event["text"] == expected, "preflight_redacted_text_done")
        elif kind == "response.content_part.done":
            require(event["part"]["text"] == expected, "preflight_redacted_part_done")
        elif kind == "response.output_item.done":
            require(event["item"]["content"][0]["text"] == expected, "preflight_redacted_item_done")
    passed["response_redacted"] = True
    require(
        set(passed) == set(CHECKS) and len(upstream.probes) == 3 and upstream.turn == 0,
        "preflight_attempt_counts",
    )
    return passed


PREFLIGHT_ERROR_CATEGORIES = (
    "unauthorized",
    "model_forbidden",
    "not_found",
    "method_not_allowed",
    "policy_denied",
    "plugin_error",
    "timeout",
    "provider_error",
    "invalid_request",
    "body_too_large",
    "unavailable",
    "overloaded",
    "internal_error",
)


def preflight_failure(step: int, response: Any) -> dict:
    """Only source-authored categories and a bounded HTTP status may leave the peer."""
    record: dict[str, Any] = {
        "kind": "failure",
        "reason": "gateway_preflight_failed",
        "stage": CHECKS[step - 1] if type(step) is int and 1 <= step <= len(CHECKS) else "unknown",
        "status": None,
        "category": "unknown",
    }
    if response is None:
        return record
    try:
        status = response.status_code
        if type(status) is int and 100 <= status <= 599:
            record["status"] = status
    except BaseException:
        pass
    try:
        payload = response.json()
        error = payload.get("error") if type(payload) is dict else None
        code = error.get("code") if type(error) is dict else None
        if type(code) is str:
            for category in PREFLIGHT_ERROR_CATEGORIES:
                if code == category:
                    record["category"] = category
                    break
    except BaseException:
        pass
    return record


class _PreflightClient:
    """Track only the fixed request ordinal; pass requests and responses unchanged."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.step = 0
        self.response: Any = None

    async def post(self, *args, **kwargs):
        self.step += 1
        self.response = None
        self.response = await self.client.post(*args, **kwargs)
        return self.response


async def observed_preflight(client, upstream: SyntheticUpstream, model: str) -> dict:
    observation = _PreflightClient(client)
    try:
        return await preflight(observation, upstream, model)
    except BaseException:
        try:
            emit(preflight_failure(observation.step, observation.response))
        except BaseException:
            pass  # Diagnostics must not replace the primary failure or prevent cleanup.
        raise


async def serve(config: dict, frozen_files: dict[str, str]) -> None:
    root = Path(__file__).resolve().parent
    # Detect .pth/startup preloads before importing or using any product module.
    verify_gateway_imports(root, frozen_files)
    import httpx
    import uvicorn
    from gateway7.config import GatewayConfig
    from gateway7.providers import HTTPProvider

    app_module: Any = importlib.import_module("gateway7.app")
    verify_gateway_imports(root, frozen_files)
    upstream = SyntheticUpstream(config)
    os.environ["GATEWAY7_SYNTHETIC_PROVIDER"] = PROVIDER_KEY
    os.environ["GATEWAY7_SYNTHETIC_CLIENT"] = CLIENT_TOKEN
    original = app_module.build_provider

    def build(provider_config, key):
        require(key == PROVIDER_KEY, "synthetic_key_required")
        return HTTPProvider(provider_config, key, transport=httpx.MockTransport(upstream.handle))

    # Only construction is replaced in this owned process. No route, pipeline,
    # provider completion method, policy hook or production encoder is replaced.
    app_module.build_provider = build
    app = app_module.create_app(
        config=GatewayConfig.model_validate(gateway_config(config["model"]))
    )
    ready = False

    async def gated(scope, receive, send):
        if scope["type"] == "http":
            local = scope.get("client", ("",))[0] == "127.0.0.1"
            if not ready and (scope["path"] == "/health" or not local):
                await send({"type": "http.response.start", "status": 503, "headers": []})
                await send({"type": "http.response.body", "body": b"preflight"})
                return
            if not local and scope["path"] == "/v1/responses":
                headers = dict(scope["headers"])
                choices = {
                    "allow_opaque": headers.get(b"x-gateway7-allow-opaque") == b"true",
                    "allow_hosted_tools": headers.get(b"x-gateway7-allow-hosted-tools") == b"true",
                }
                require(
                    choices == config["consent"] and b"x-gateway7-stream-mode" not in headers,
                    "explicit_consent_or_default_stream_mode_changed",
                )
                emit(
                    {
                        "kind": "gateway_ingress",
                        "consent": choices,
                        "stream_mode": "default_checked",
                    }
                )
        await app(scope, receive, send)

    server = uvicorn.Server(
        uvicorn.Config(gated, host="0.0.0.0", port=8765, access_log=False, log_level="error")
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started or task.done():
                break
            await asyncio.sleep(0.02)
        require(server.started, "gateway_startup_failed")
        verify_gateway_imports(root, frozen_files)
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8765", trust_env=False, timeout=5
        ) as client:
            checks = await observed_preflight(client, upstream, config["model"])
        # Preflight also loads the native provider's lazy imports. Re-check the
        # complete loaded set before publishing readiness or Gateway evidence.
        verified = verify_gateway_imports(root, frozen_files)
        emit(
            {
                "kind": "gateway",
                "checks": checks,
                "preflight_upstream_requests": 3,
                "source_freeze_sha256": config["source_freeze_sha256"],
                "policies": gateway_config(config["model"])["middleware"],
                "transport": "httpx.MockTransport",
                "overlay_imports_verified": True,
                "overlay_modules": sorted(verified),
            }
        )
        ready = True
        async with asyncio.timeout(150):
            await task
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(3):
                await task
        finally:
            app_module.build_provider = original


def main() -> None:
    require(
        sys.platform == "linux" and Path(__file__).resolve().parent == Path("/opt/synthetic"),
        "container_only_peer",
    )
    require((3, 11) <= sys.version_info[:2] < (3, 14), "unsupported_python_runtime")
    verify_private_bytecode_cache()
    root = Path("/opt/synthetic")
    # Explicitly prefer the overlay, but never evict a cached product module to
    # disguise a preload: serve() checks every cached origin before using it.
    sys.path[:] = [str(root), *(entry for entry in sys.path if entry != str(root))]
    config = json.loads((root / "scenario.json").read_text())
    freeze = (root / "source-freeze.json").read_bytes()
    require(
        hashlib.sha256(freeze).hexdigest() == config["source_freeze_sha256"], "freeze_hash_mismatch"
    )
    frozen_files = json.loads(freeze)["files"]
    for name, digest in frozen_files.items():
        require(
            hashlib.sha256((root / name).read_bytes()).hexdigest() == digest,
            "packaged_source_changed",
        )
    guard = runtime_guard()
    emit(guard)
    require(
        all(value is True for key, value in guard.items() if key != "kind"), "peer_isolation_failed"
    )
    sys.addaudithook(forbid_external_sockets)
    asyncio.run(serve(config, frozen_files))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"kind": "failure", "reason": "gateway_peer_verification_failed"})
        raise SystemExit(1) from None

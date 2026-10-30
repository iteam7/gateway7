"""Verify an actual OpenCode V2 tool cycle through Gateway7 without provider spending.

The production OpenAI adapter is exercised against an injected fragmented SSE transport.
Only synthetic credentials and a temporary local text fixture are used.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any

import httpx
import uvicorn

from gateway7.config import GatewayConfig
from gateway7.providers import HTTPProvider

MARKER = "GATEWAY7_AGENT_OK"
CLIENT_TOKEN = "gateway7-synthetic-opencode-client"
PROVIDER_KEY = "gateway7-synthetic-opencode-provider"
BLOCKED_TERM = "GATEWAY7_BLOCKED_ARGUMENT"


class Fragments(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def __aiter__(self):
        # Deliberately split UTF-8/JSON/SSE records independently of event boundaries.
        for offset in range(0, len(self.body), 17):
            await asyncio.sleep(0)
            yield self.body[offset : offset + 17]


def fixture_transport(fixture: Path, captured: list[dict[str, Any]]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + PROVIDER_KEY
        body = json.loads(request.content)
        captured.append(body)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        results = [message for message in body["messages"] if message["role"] == "tool"]
        if results:
            assert len(results) == 1
            assert results[0]["tool_call_id"] == "call_gateway7_read"
            assert MARKER in results[0]["content"]
            content = {"content": MARKER}
            finish = "stop"
        else:
            read = next(tool for tool in body["tools"] if tool["function"]["name"] == "read")
            assert "path" in read["function"]["parameters"]["properties"]
            # Tool arguments arrive across multiple deltas, as real providers send them.
            arguments = json.dumps({"path": str(fixture)})
            midpoint = len(arguments) // 2
            content = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_gateway7_read",
                        "type": "function",
                        "function": {"name": "read", "arguments": arguments[:midpoint]},
                    }
                ]
            }
            remainder = {
                "tool_calls": [{"index": 0, "function": {"arguments": arguments[midpoint:]}}]
            }
            finish = "tool_calls"
        envelope = {
            "id": "chatcmpl-gateway7-synthetic",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "gpt-4.1",
        }

        def event(delta: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
            return {
                **envelope,
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
            }

        events = [event({"role": "assistant"}), event(content)]
        if not results:
            events.append(event(remainder))
        events.extend(
            [
                event({}, finish),
                {
                    **envelope,
                    "choices": [],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                },
            ]
        )
        encoded = (
            "".join("data: " + json.dumps(item) + "\n\n" for item in events) + "data: [DONE]\n\n"
        ).encode()
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Fragments(encoded),
        )

    return httpx.MockTransport(respond)


def opencode_config(base_url: str) -> dict[str, Any]:
    # The V1-compatible syntax is accepted by the tested V2 CLI and maps to its
    # OpenAI-compatible Chat route. Model limits keep the gateway contract bounded.
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "gateway7/gpt-4.1",
        "small_model": "gateway7/gpt-4.1",
        "enabled_providers": ["gateway7"],
        "provider": {
            "gateway7": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Gateway7 synthetic",
                "options": {
                    "baseURL": base_url,
                    "apiKey": "{env:GATEWAY7_CLIENT_TOKEN}",
                    "parallelToolCalls": False,
                },
                "models": {
                    "gpt-4.1": {
                        "name": "Gateway7 fixture",
                        "limit": {"context": 32768, "output": 1024},
                        "tool_call": True,
                        "reasoning": False,
                        "temperature": False,
                    }
                },
            }
        },
        "agent": {
            "gateway7-smoke": {
                "mode": "primary",
                "model": "gateway7/gpt-4.1",
                "prompt": "Read the requested local file with read, then return its control string.",
                "tools": {"*": False, "read": True},
                "permission": {"*": "deny", "read": "allow"},
                "steps": 3,
            }
        },
        "permission": {"*": "deny", "read": "allow"},
        "autoupdate": False,
        "share": "disabled",
        "plugin": [],
    }


def isolated_environment(directory: Path) -> dict[str, str]:
    environment = dict(os.environ)
    # The CLI prefers PWD over process.cwd(); a subprocess must use its actual cwd.
    environment.pop("PWD", None)
    for key in list(environment):
        if key.startswith("OPENCODE_") or key in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
        }:
            environment.pop(key)
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("OPENCODE_TEST_HOME", "home"),
    ):
        target = directory / name
        target.mkdir()
        environment[key] = str(target)
    environment["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
    environment["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
    environment["GATEWAY7_CLIENT_TOKEN"] = CLIENT_TOKEN
    return environment


def run_scenario(binary: str, directory: Path, *, denied: bool) -> dict[str, Any]:
    directory.mkdir()
    project = directory / "project"
    project.mkdir()
    filename = f"{BLOCKED_TERM}.txt" if denied else "agent-fixture.txt"
    fixture = project / filename
    fixture.write_text(MARKER + "\n", encoding="utf-8")
    captured: list[dict[str, Any]] = []
    config = GatewayConfig.model_validate(
        {
            "provider": {
                "kind": "openai",
                "model": "gpt-4.1",
                "key_env": "GATEWAY7_SMOKE_PROVIDER",
            },
            "auth": {
                "enabled": True,
                "clients": {"smoke": {"token_env": "GATEWAY7_SMOKE_CLIENT", "models": ["gpt-4.1"]}},
            },
            "limits": {"request_timeout_seconds": 30.0},
            "plugins": {
                "guard": {
                    "module": "gateway7.plugins.content_policy",
                    "settings": {"terms": [BLOCKED_TERM], "phase": "response", "action": "block"},
                }
            },
            "middleware": ["guard"],
        }
    )
    app_module = importlib.import_module("gateway7.app")
    original_builder = app_module.build_provider
    original_provider_env = os.environ.get("GATEWAY7_SMOKE_PROVIDER")
    original_client_env = os.environ.get("GATEWAY7_SMOKE_CLIENT")
    os.environ["GATEWAY7_SMOKE_PROVIDER"] = PROVIDER_KEY
    os.environ["GATEWAY7_SMOKE_CLIENT"] = CLIENT_TOKEN
    # Injection is only in this local verification process. The production config
    # keeps the fixed HTTPS OpenAI origin and never permits arbitrary upstream URLs.
    app_module.build_provider = lambda provider_config, key: HTTPProvider(
        provider_config, key, transport=fixture_transport(fixture, captured)
    )
    server = None
    thread = None
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    try:
        app = app_module.create_app(config=config)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="critical")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if client.get(base_url + "/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.03)
            else:
                raise AssertionError("Gateway failed to start")
        (project / "opencode.json").write_text(
            json.dumps(opencode_config(base_url + "/v1"), indent=2), encoding="utf-8"
        )
        command = [
            binary,
            "--standalone",
            "run",
            "--model",
            "gateway7/gpt-4.1",
            "--agent",
            "gateway7-smoke",
            "--format",
            "json",
            "--title",
            "Gateway7 synthetic tool cycle",
            f"Read {filename} using read, then return only the exact control string inside the file.",
        ]
        result = subprocess.run(
            command,
            cwd=project,
            env=isolated_environment(directory),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        calls = [event for event in events if event.get("type") == "tool_use"]
        texts = [event["part"]["text"] for event in events if event.get("type") == "text"]
        errors = [event for event in events if event.get("type") == "error"]
        policy_denials = sum(
            sample.value
            for family in app.state.metrics.registry.collect()
            for sample in family.samples
            if sample.name == "gateway7_middleware_steps_total"
            and sample.labels
            == {"middleware": "guard", "phase": "response", "outcome": "policy_denied"}
        )
        if denied:
            assert len(captured) == 1, "Denied tool call unexpectedly continued the agent cycle"
            assert not calls, "OpenCode executed a tool that the response policy denied"
            assert not texts, "OpenCode received final text from a policy-denied response"
            assert errors, "OpenCode did not report the policy denial"
            assert policy_denials == 1, "The failure did not originate in the response policy"
        else:
            assert result.returncode == 0, "OpenCode failed the normal tool cycle"
            assert not errors, "OpenCode reported an error during the normal tool cycle"
            assert len(captured) == 2, "Expected tool-call and final-answer provider requests"
            assert len(calls) == 1 and calls[0]["part"]["tool"] == "read"
            assert calls[0]["part"]["state"]["status"] == "completed"
            assert MARKER in calls[0]["part"]["state"]["output"]
            assert texts == [MARKER], "The final answer did not match the file's control string"
        return {
            "scenario": "policy_denies_before_tool_execution" if denied else "read_tool_round_trip",
            "passed": True,
            "provider_requests": len(captured),
            "provider_stream": all(body["stream"] is True for body in captured),
            "fragment_bytes": 17,
            "tools_executed": len(calls),
            "final_text": texts,
            "client_errors": len(errors),
            "response_policy_denials": int(policy_denials),
        }
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
            assert not thread.is_alive(), "Gateway server did not stop"
        app_module.build_provider = original_builder
        for key, original in (
            ("GATEWAY7_SMOKE_PROVIDER", original_provider_env),
            ("GATEWAY7_SMOKE_CLIENT", original_client_env),
        ):
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opencode", default="opencode2", help="Path to an installed OpenCode V2 CLI"
    )
    parser.add_argument(
        "--report", type=Path, help="Optional path for the synthetic verification report"
    )
    arguments = parser.parse_args()
    binary = shutil.which(arguments.opencode)
    if binary is None:
        raise SystemExit("OpenCode V2 executable was not found; install @opencode/cli first")
    binary = str(Path(binary).absolute())
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, timeout=10, check=True
    ).stdout.strip()
    if not version.startswith("opencode v2."):
        raise SystemExit("This smoke scenario requires OpenCode V2")
    with Path(binary).resolve().open("rb") as executable:
        digest = hashlib.file_digest(executable, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix="gateway7-opencode-") as temporary:
        directory = Path(temporary)
        report = {
            "opencode_version": version,
            "binary_sha256": digest,
            "external_provider_called": False,
            "scenarios": [
                run_scenario(binary, directory / "allowed", denied=False),
                run_scenario(binary, directory / "denied", denied=True),
            ],
        }
    output = json.dumps(report, indent=2)
    print(output)
    if arguments.report:
        arguments.report.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

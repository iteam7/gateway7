"""Run the synthetic acceptance checks against two real local HTTP processes."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Iterator

import httpx
import yaml

from demo.upstream import ANSWER, USAGE


SYNTHETIC_KEY = "gateway7-synthetic-demo-only"
PHONE_EXAMPLES = ("+7 900 000-00-00", "8 (900) 000-00-00", "+79000000000")
NON_PHONE_TEXT = "Order ORDER-2026-1001 shipped on 2026-10-08"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _hash_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


@contextmanager
def _server(
    command: list[str],
    url: str,
    env: dict[str, str],
    cwd: Path,
    logs: list[str],
) -> Iterator[None]:
    # Temporary files cannot fill a PIPE and deadlock a child during shutdown.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT
        )
        try:
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError("Demo service exited before becoming ready")
                    try:
                        if client.get(url + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                else:
                    raise AssertionError("Demo service did not become ready")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            output.seek(0)
            logs.append(output.read())


def _write_config(path: Path, config: dict) -> None:
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _gateway_command(config: Path, port: int) -> list[str]:
    return [
        sys.executable, "-m", "gateway7", "--config", str(config),
        "--host", "127.0.0.1", "--port", str(port),
    ]


def _failed_start(config: Path, env: dict[str, str], cwd: Path, logs: list[str]) -> str:
    try:
        result = subprocess.run(
            _gateway_command(config, _free_port()),
            cwd=cwd, env=env, capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError("Invalid configuration unexpectedly started a service") from None
    output = result.stdout + result.stderr
    logs.append(output)
    assert result.returncode != 0, "Invalid configuration did not fail startup"
    assert "Traceback" not in output, "Startup failure exposed a traceback"
    return output


def run() -> None:
    repository = Path(__file__).resolve().parents[1]
    core_before = _hash_files(repository / "gateway7")
    logs: list[str] = []
    client_outputs: list[str] = []
    baseline = yaml.safe_load((repository / "config" / "demo.yaml").read_text(encoding="utf-8"))
    upstream_port = _free_port()
    upstream_url = f"http://127.0.0.1:{upstream_port}"
    baseline["provider"]["base_url"] = upstream_url

    with tempfile.TemporaryDirectory(prefix="gateway7-demo-") as temporary:
        sandbox = Path(temporary)
        config_path = sandbox / "gateway.yaml"
        _write_config(config_path, baseline)
        env = os.environ.copy()
        env.update({
            "FAKE_LLM_API_KEY": SYNTHETIC_KEY,
            "DEMO_PROVIDER_KEY": SYNTHETIC_KEY,
            "PYTHONPATH": os.pathsep.join((str(sandbox), str(repository))),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        })

        def exercise(config: dict, payload: dict) -> tuple[dict, dict]:
            _write_config(config_path, config)
            port = _free_port()
            url = f"http://127.0.0.1:{port}"
            with _server(_gateway_command(config_path, port), url, env, sandbox, logs):
                with httpx.Client(trust_env=False, timeout=12) as client:
                    response = client.post(url + "/chat", json=payload)
                    client_outputs.append(response.text)
                    assert response.status_code == 200, "Gateway request failed"
                    result = response.json()
                    inspection = client.get(upstream_url + "/requests")
                    inspection.raise_for_status()
                    record = inspection.json()["requests"][-1]
                    return result, record

        upstream_command = [
            sys.executable, "-m", "uvicorn", "demo.upstream:app",
            "--host", "127.0.0.1", "--port", str(upstream_port),
            "--no-access-log", "--log-level", "warning",
        ]
        with _server(upstream_command, upstream_url, env, sandbox, logs):
            with httpx.Client(trust_env=False, timeout=2) as client:
                for headers in ({}, {"authorization": "Bearer wrong-synthetic-value"}):
                    rejected = client.post(
                        upstream_url + "/chat",
                        json={"messages": [{"role": "user", "content": "ping"}]},
                        headers=headers,
                    )
                    client_outputs.append(rejected.text)
                    assert rejected.status_code == 401, "Fake upstream accepted an invalid key"
                assert client.get(upstream_url + "/requests").json() == {"requests": []}

            result, record = exercise(
                baseline,
                {"messages": [{"role": "user", "content": "Reply with the word pong"}]},
            )
            assert result["text"] == ANSWER and result["usage"] == USAGE
            assert isinstance(result.get("request_id"), str) and result["request_id"]
            assert record["key_accepted"] is True
            print(f"PASS US-01: {result['text']}; key_accepted=true; invalid keys rejected")

            _, record = exercise(
                baseline,
                {"messages": [{"role": "user", "content": "; ".join(PHONE_EXAMPLES)}]},
            )
            masked = record["body"]["messages"][0]["content"]
            assert masked == "[PHONE]; [PHONE]; [PHONE]"
            print(f"PASS US-02 AC-01: one message, three phone formats -> {masked}")

            payload = {"messages": [
                {"role": "user", "content": "Synthetic contact " + PHONE_EXAMPLES[0]},
                {"role": "assistant", "content": "Earlier reply " + PHONE_EXAMPLES[1]},
                {"role": "user", "content": "Latest contact " + PHONE_EXAMPLES[2]},
            ]}
            _, record = exercise(baseline, payload)
            serialized = json.dumps(record)
            assert all(phone not in serialized for phone in PHONE_EXAMPLES)
            assert [message["content"] for message in record["body"]["messages"]] == [
                "Synthetic contact [PHONE]", "Earlier reply [PHONE]", "Latest contact [PHONE]",
            ]
            print("PASS US-02 AC-02: three-message history -> [PHONE] in earlier and latest messages")
            _, record = exercise(
                baseline, {"messages": [{"role": "user", "content": NON_PHONE_TEXT}]}
            )
            assert record["body"]["messages"][0]["content"] == NON_PHONE_TEXT
            print(f"PASS US-02 AC-03: unchanged -> {record['body']['messages'][0]['content']}")

            before_install = _hash_files(sandbox)
            plugin_path = sandbox / "company_plugins" / "sample.py"
            plugin_path.parent.mkdir()
            shutil.copyfile(repository / "examples" / "sample_plugin.py", plugin_path)
            installed = deepcopy(baseline)
            installed["plugins"]["sample"] = {
                "module": "company_plugins.sample", "enabled": True,
                "required": False, "settings": {},
            }
            installed["middleware"] = ["mask", "sample"]
            ping = {"messages": [{"role": "user", "content": "ping"}]}
            _, record = exercise(installed, ping)
            assert record["body"]["messages"][0]["content"] == "ping[checked-by-sample]"
            after_install = _hash_files(sandbox)
            changed = {
                path for path in before_install.keys() | after_install.keys()
                if before_install.get(path) != after_install.get(path)
            }
            assert changed == {"gateway.yaml", "company_plugins/sample.py"}
            assert _hash_files(repository / "gateway7") == core_before
            print("PASS US-03 install: only company_plugins/sample.py and gateway.yaml changed; core unchanged")
            print(f"  upstream saw: {record['body']['messages'][0]['content']}")

            disabled = deepcopy(installed)
            disabled["plugins"]["sample"]["enabled"] = False
            _, record = exercise(disabled, ping)
            assert record["body"]["messages"][0]["content"] == "ping"
            print(f"PASS US-03 disable: after restart upstream saw {record['body']['messages'][0]['content']}")

            ordered = deepcopy(baseline)
            for name, marker in (("alpha", "[A]"), ("beta", "[B]")):
                ordered["plugins"][name] = {
                    "module": "company_plugins.sample", "enabled": True,
                    "required": False, "settings": {"marker": marker},
                }
            ordered["middleware"] = ["mask", "alpha", "beta"]
            result, record = exercise(ordered, ping)
            assert record["body"]["messages"][0]["content"] == "ping[A][B]"
            assert result["text"] == ANSWER + "[B][A]"
            ordered["middleware"] = ["mask", "beta", "alpha"]
            result, record = exercise(ordered, ping)
            assert record["body"]["messages"][0]["content"] == "ping[B][A]"
            assert result["text"] == ANSWER + "[A][B]"
            print("PASS middleware order: requests follow configuration; responses unwind in reverse")
            print("  request: ping[A][B] -> ping[B][A]; response suffix: [B][A] -> [A][B]")

            shutil.copyfile(repository / "examples" / "guard_plugin.py", plugin_path.with_name("guard.py"))
            composed = deepcopy(installed)
            composed["plugins"]["guard"] = {
                "module": "company_plugins.guard", "enabled": True,
                "required": True, "settings": {},
            }
            composed["middleware"] = ["mask", "guard", "sample"]
            result, record = exercise(composed, {"messages": [
                {"role": "user", "content": "ping " + PHONE_EXAMPLES[0]},
            ]})
            assert record["body"]["messages"][0]["content"] == "ping [PHONE][checked-by-sample]"
            assert result["text"] == ANSWER + "[checked-by-sample]"
            print("PASS composition: phone mask -> policy guard -> sample -> provider -> sample -> guard -> mask")
            print("  upstream: ping [PHONE][checked-by-sample]; answer suffix: [checked-by-sample]")
            for line in logs[-1].splitlines():
                if f"request_id={result['request_id']} " in line:
                    print("  trace: " + line)

            def failure(config: dict, text: str, status: int, code: str, calls: int = 0) -> None:
                _write_config(config_path, config)
                port = _free_port()
                url = f"http://127.0.0.1:{port}"
                with _server(_gateway_command(config_path, port), url, env, sandbox, logs):
                    with httpx.Client(trust_env=False, timeout=12) as client:
                        before = len(client.get(upstream_url + "/requests").json()["requests"])
                        response = client.post(url + "/chat", json={"messages": [
                            {"role": "user", "content": text},
                        ]})
                        client_outputs.append(response.text)
                        assert response.status_code == status
                        result = response.json()
                        assert result["error"]["code"] == code
                        assert result["request_id"] == response.headers["x-request-id"]
                        after = len(client.get(upstream_url + "/requests").json()["requests"])
                        assert after - before == calls
                        assert "synthetic-demo-exception" not in response.text
                        assert "checked-by-sample" not in response.text
                print(f"PASS failure: {code}; HTTP {status}; upstream calls={calls}")
                for line in logs[-1].splitlines():
                    if f"request_id={result['request_id']} " in line:
                        print("  trace: " + line)

            failure(composed, "BLOCK-ME-TEST " + PHONE_EXAMPLES[0], 403, "policy_denied")
            faulty = deepcopy(installed)
            faulty["plugins"]["fault"] = {
                "module": "demo.fault_plugin", "enabled": True,
                "required": True, "settings": {"mode": "error", "phase": "request"},
            }
            faulty["middleware"] = ["mask", "fault", "sample"]
            failure(faulty, "synthetic failure", 500, "plugin_error")
            faulty["plugins"]["fault"]["settings"]["mode"] = "timeout"
            faulty["limits"]["hook_timeout_seconds"] = 0.05
            failure(faulty, "synthetic timeout", 504, "timeout")
            faulty["plugins"]["fault"]["settings"] = {"mode": "error", "phase": "response"}
            failure(faulty, "synthetic response failure", 500, "plugin_error", calls=1)

            _write_config(config_path, baseline)
            missing_key_env = env.copy()
            missing_key_env.pop("FAKE_LLM_API_KEY")
            output = _failed_start(config_path, missing_key_env, sandbox, logs)
            assert "FAKE_LLM_API_KEY" in output
            print("PASS startup: missing provider key fails with a safe diagnostic")
            for enabled in (True, False):
                absent = deepcopy(baseline)
                absent["plugins"]["missing"] = {
                    "module": "company_plugins.does_not_exist", "enabled": enabled,
                    "required": False, "settings": {},
                }
                _write_config(config_path, absent)
                output = _failed_start(config_path, env, sandbox, logs)
                assert "missing" in output or "company_plugins.does_not_exist" in output
            print("PASS startup: a missing plugin fails even when its configuration is disabled")

    assert _hash_files(repository / "gateway7") == core_before
    assert all(SYNTHETIC_KEY not in output for output in logs + client_outputs)
    assert all(phone not in output for phone in PHONE_EXAMPLES for output in logs)
    print("PASS redaction: no provider key in captured logs or client responses; no raw phones in logs")
    print("PENDING US-01 AC-05: real Claude response requires a separate authorized live run")


def main() -> int:
    try:
        run()
    except Exception:
        # These checks may handle credentials in inherited environments: keep failure output safe.
        print("FAIL deterministic demo: acceptance check failed; run pytest for diagnostics", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

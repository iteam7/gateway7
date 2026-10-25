"""The installed CLI validates offline and runs its demo outside the source cwd."""

import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from gateway7.cli import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def restore_logger():
    logger = logging.getLogger("gateway7")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers, logger.level, logger.propagate = handlers, level, propagate


def test_help_lists_launch_and_validation_commands(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert all(command in output for command in ("serve", "validate", "chat", "demo"))


def test_validate_needs_no_key_and_does_not_start_provider(monkeypatch, tmp_path, capsys):
    path = tmp_path / "valid.yaml"
    path.write_text("provider:\n  kind: claude\n  model: configured-test-model\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["validate", "--config", str(path)]) == 0
    assert "Configuration valid: provider=claude" in capsys.readouterr().out


def test_invalid_validation_redacts_values(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text("provider:\n  secret: synthetic-secret-value\n", encoding="utf-8")
    assert main(["validate", "--config", str(path)]) == 1
    output = capsys.readouterr().err
    assert "synthetic-secret-value" not in output and "Traceback" not in output


def test_no_configuration_gives_actionable_error(monkeypatch, capsys):
    monkeypatch.delenv("GATEWAY_CONFIG", raising=False)
    assert main([]) == 1
    assert "gateway7 demo" in capsys.readouterr().err


def test_legacy_start_missing_key_is_safe(tmp_path, monkeypatch, capsys):
    path = tmp_path / "gateway.yaml"
    path.write_text("provider:\n  key_env: GATEWAY7_CLI_MISSING_KEY\n", encoding="utf-8")
    monkeypatch.delenv("GATEWAY7_CLI_MISSING_KEY", raising=False)
    assert main(["--config", str(path)]) == 1
    output = capsys.readouterr().err
    assert "GATEWAY7_CLI_MISSING_KEY" in output and "Traceback" not in output


@pytest.mark.parametrize("arguments", [
    ["serve", "--port", "0"], ["demo", "--port", "65536"],
    ["chat", "--message", "hello", "--max-tokens", "0"],
])
def test_invalid_cli_limits_exit_two(arguments):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


def test_chat_rejects_url_credentials_without_leaking_them(capsys):
    assert main(["chat", "--message", "hello", "--url", "http://user:secret-value@localhost"]) == 1
    output = capsys.readouterr().err
    assert "secret-value" not in output


def test_demo_chat_and_metrics_work_outside_repository(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as logs:
        process = subprocess.Popen(
            [sys.executable, "-m", "gateway7", "demo", "--port", str(port)],
            cwd=tmp_path, env=env, stdout=logs, stderr=subprocess.STDOUT,
        )
        child_pids = []
        try:
            with httpx.Client(trust_env=False, timeout=1) as client:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    assert process.poll() is None, "Demo exited during startup"
                    try:
                        if client.get(url + "/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                else:
                    pytest.fail("Demo did not start")
                child_file = Path(f"/proc/{process.pid}/task/{process.pid}/children")
                if child_file.exists():
                    child_pids = child_file.read_text().split()
                result = subprocess.run(
                    [sys.executable, "-m", "gateway7", "chat", "--url", url],
                    input="Synthetic user@example.com +79000000000 SECRET-TEST", text=True,
                    capture_output=True, cwd=tmp_path, env=env, timeout=10,
                )
                assert result.returncode == 0, result.stderr
                answer = json.loads(result.stdout)
                assert answer["text"] == "pong — Synthetic [EMAIL] [PHONE] [removed]"
                assert answer["usage"] == {"input_tokens": 12, "output_tokens": 4}
                denied = client.post(url + "/chat", json={"messages": [{"role": "user", "content": "BLOCK-ME-TEST"}]})
                assert denied.status_code == 403
                metrics = client.get(url + "/metrics").text
                assert 'gateway7_provider_calls_total{outcome="complete",provider="fake"} 1.0' in metrics
                assert "user@example.com" not in metrics and "79000000000" not in metrics
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            logs.seek(0)
            output = logs.read()
            assert "Traceback" not in output and "user@example.com" not in output
            assert all(not Path(f"/proc/{pid}").exists() for pid in child_pids)


@pytest.mark.skipif(os.name == "nt", reason="Windows terminate() is an immediate kill, not SIGTERM")
def test_sigterm_during_demo_startup_reaps_synthetic_child(tmp_path):
    marker = tmp_path / "waiting"
    launcher = tmp_path / "startup.py"
    launcher.write_text(
        "import asyncio\nfrom pathlib import Path\nfrom gateway7 import cli\n"
        "async def delayed_get(self, *args, **kwargs):\n"
        f"    Path({str(marker)!r}).write_text('waiting')\n"
        "    await asyncio.sleep(30)\n"
        "cli.httpx.AsyncClient.get = delayed_get\n"
        "raise SystemExit(cli.main(['demo']))\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as logs:
        process = subprocess.Popen([sys.executable, str(launcher)], cwd=tmp_path, env=env,
                                   stdout=logs, stderr=subprocess.STDOUT)
        child_pids = []
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not marker.exists():
                assert process.poll() is None
                time.sleep(0.025)
            assert marker.exists(), "Demo did not reach the startup wait"
            child_file = Path(f"/proc/{process.pid}/task/{process.pid}/children")
            if child_file.exists():
                child_pids = child_file.read_text().split()
                assert child_pids
            process.terminate()
            assert process.wait(timeout=10) == 0
            assert all(not Path(f"/proc/{pid}").exists() for pid in child_pids)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            logs.seek(0)
            assert "Traceback" not in logs.read()

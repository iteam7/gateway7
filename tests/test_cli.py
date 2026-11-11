"""The installed CLI validates offline and runs its demo outside the source cwd."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import ModuleType

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from gateway7 import cli
from gateway7.analytics import Analytics
from gateway7.app import create_app
from gateway7.cli import main
from gateway7.config import GatewayConfig
from gateway7.plugin_api import API_VERSION, PluginDescriptor
from gateway7.telemetry import Telemetry

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
    path.write_text(
        "provider:\n  kind: claude\n  model: configured-test-model\nauth:\n  enabled: true\n  clients:\n    test:\n      token_env: GATEWAY7_CLI_TOKEN\n      models: [configured-test-model]\n",
        encoding="utf-8",
    )
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


@pytest.mark.parametrize(
    "arguments",
    [
        ["serve", "--port", "0"],
        ["demo", "--port", "65536"],
        ["chat", "--message", "hello", "--max-tokens", "0"],
    ],
)
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
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PYTHONUNBUFFERED": "1",
        "GATEWAY7_TOKEN": "gateway7-synthetic-client-token",
    }
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as logs:
        process = subprocess.Popen(
            [sys.executable, "-m", "gateway7", "demo", "--port", str(port)],
            cwd=tmp_path,
            env=env,
            stdout=logs,
            stderr=subprocess.STDOUT,
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
                    input="Synthetic user@example.com +79000000000 SECRET-TEST",
                    text=True,
                    capture_output=True,
                    cwd=tmp_path,
                    env=env,
                    timeout=10,
                )
                assert result.returncode == 0, result.stderr
                answer = json.loads(result.stdout)
                assert answer["text"] == "pong — Synthetic [EMAIL] [PHONE] [removed]"
                assert answer["usage"] == {"input_tokens": 12, "output_tokens": 4}
                unauthorized = client.post(
                    url + "/chat", json={"messages": [{"role": "user", "content": "Allowed"}]}
                )
                assert unauthorized.status_code == 401
                denied = client.post(
                    url + "/chat",
                    headers={"Authorization": "Bearer gateway7-synthetic-client-token"},
                    json={"messages": [{"role": "user", "content": "BLOCK-ME-TEST"}]},
                )
                assert denied.status_code == 403
                metrics = client.get(url + "/metrics").text
                assert (
                    'gateway7_provider_calls_total{outcome="complete",provider="fake"} 1.0'
                    in metrics
                )
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
        process = subprocess.Popen(
            [sys.executable, str(launcher)],
            cwd=tmp_path,
            env=env,
            stdout=logs,
            stderr=subprocess.STDOUT,
        )
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


@pytest.mark.parametrize("model", ["allowed-model", "vendor/model:revision", "é" * 512])
async def test_chat_sends_environment_bearer_and_optional_model_without_leaking_token(
    monkeypatch, capsys, model
):
    from gateway7 import cli

    key = "gateway7-synthetic-cli-client"
    monkeypatch.setenv("SYNTHETIC_CLI_CLIENT", key)
    original_client = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer " + key
        assert key not in request.content.decode() and key not in str(request.url)
        assert json.loads(request.content)["model"] == model
        return httpx.Response(
            200,
            json={
                "text": "Synthetic answer",
                "usage": None,
                "finish_reason": "length",
                "request_id": "synthetic",
            },
        )

    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert (
        await cli._chat(
            "http://127.0.0.1:8000",
            "Synthetic input",
            32,
            token_env="SYNTHETIC_CLI_CLIENT",
            model=model,
        )
        == 0
    )
    output = capsys.readouterr()
    assert json.loads(output.out) == {"text": "Synthetic answer", "usage": None}
    assert key not in output.out + output.err and len(seen) == 1


def test_chat_rejects_bad_token_value_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setenv("GATEWAY7_TOKEN", "synthetic secret with spaces")
    assert main(["chat", "--message", "synthetic"]) == 1
    output = capsys.readouterr()
    assert "synthetic secret with spaces" not in output.out + output.err


@pytest.mark.parametrize(
    "model", ["", "model name", "model\x00", "model\u200b", "\ud800", "é" * 513]
)
def test_chat_rejects_invalid_model_before_http_with_static_error(monkeypatch, capsys, model):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid model reached HTTP client creation")

    monkeypatch.setattr("gateway7.cli.httpx.AsyncClient", forbidden)
    assert main(["chat", "--message", "Synthetic input", "--model", model]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Gateway startup failed: --model must be a valid model identifier\n"


def test_interrupted_chat_input_exits_130_without_output(monkeypatch, capsys):
    class InterruptedInput:
        def read(self, _limit):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stdin", InterruptedInput())
    assert main(["chat"]) == 130
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("command", ["serve", "demo"])
def test_server_keyboard_interrupt_remains_an_orderly_exit(command, monkeypatch, capsys):
    from gateway7 import cli

    cleaned_up = []

    async def interrupted(*_args):
        try:
            raise KeyboardInterrupt
        finally:
            cleaned_up.append(True)

    monkeypatch.setattr(cli, "_" + command, interrupted)
    arguments = [command, "--config", "synthetic.yaml"] if command == "serve" else [command]
    assert main(arguments) == 0
    assert cleaned_up == [True]
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.skipif(os.name == "nt", reason="Uses POSIX SIGINT delivery to a CLI subprocess")
def test_sigint_during_chat_closes_connection_and_exits_130(tmp_path):
    token = "gateway7-synthetic-interrupted-chat"
    message = "Synthetic unfinished request"
    environment = {**os.environ, "PYTHONPATH": str(ROOT), "GATEWAY7_TOKEN": token}
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gateway7",
                "chat",
                "--url",
                f"http://127.0.0.1:{port}",
                "--message",
                message,
            ],
            cwd=tmp_path,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            connection, _address = listener.accept()
            with connection:
                connection.settimeout(10)
                request = bytearray()
                while b"\r\n\r\n" not in request:
                    chunk = connection.recv(4096)
                    assert chunk, "CLI closed before sending its request"
                    request.extend(chunk)
                headers, body = bytes(request).split(b"\r\n\r\n", 1)
                content_length = next(
                    int(line.split(b":", 1)[1])
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                while len(body) < content_length:
                    chunk = connection.recv(4096)
                    assert chunk, "CLI closed before completing its request body"
                    body += chunk
                assert json.loads(body)["messages"][0]["content"] == message
                assert b"authorization: Bearer " + token.encode() in headers
                # Keep the HTTP response incomplete so chat is interrupted before success.
                connection.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: 1024\r\n\r\n" + b'{"text": "unfinished'
                )
                process.send_signal(signal.SIGINT)
                stdout, stderr = process.communicate(timeout=10)
                assert process.returncode == 130
                assert stdout == ""
                assert "Traceback" not in stderr and token not in stderr and message not in stderr
                try:
                    assert connection.recv(1) == b"", "Interrupted CLI left its connection open"
                except ConnectionResetError:
                    pass  # Closing with unread response bytes may reset the TCP connection.
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


async def test_cancelled_secret_file_startup_that_returns_still_finishes_cleanup(
    monkeypatch, tmp_path
):
    values = {
        "GATEWAY7_SYNTHETIC_CANCEL_STARTUP_KEY": "synthetic-cancel-startup-provider-key",
        "GATEWAY7_SYNTHETIC_CANCEL_STARTUP_TOKEN": "synthetic-cancel-startup-client-token",
    }
    for name in values:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "synthetic-private.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    path.chmod(0o600)
    started = asyncio.Event()
    returned = asyncio.Event()
    shutdown_started = asyncio.Event()
    release_shutdown = asyncio.Event()
    provider_closed = asyncio.Event()
    lifespan_tasks = []
    cancellations = []
    events = []

    class Settings(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    class StartupPlugin:
        async def startup(self):
            assert {name: os.environ.get(name) for name in values} == values
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                returned.set()

        async def shutdown(self):
            assert all(name not in os.environ for name in values)
            shutdown_started.set()
            while not release_shutdown.is_set():
                try:
                    await release_shutdown.wait()
                except asyncio.CancelledError:
                    pass
            events.append("shutdown")

        async def handle(self, request, context, call_next):
            return await call_next(request)

    class Provider:
        async def aclose(self):
            assert all(name not in os.environ for name in values)
            events.append("provider_close")
            provider_closed.set()

    class Server:
        def __init__(self, configuration):
            assert configuration.lifespan == "off"

        async def serve(self):
            pytest.fail("Cancelled startup reached the HTTP server")

    module = ModuleType("test_gateway7_cli_cancelled_startup")
    module.PLUGIN = PluginDescriptor("synthetic-startup", API_VERSION, Settings, lambda _: StartupPlugin())
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = GatewayConfig.model_validate({
        "provider": {"key_env": "GATEWAY7_SYNTHETIC_CANCEL_STARTUP_KEY"},
        "auth": {"enabled": True, "clients": {
            "synthetic": {"token_env": "GATEWAY7_SYNTHETIC_CANCEL_STARTUP_TOKEN"},
        }},
        "plugins": {"startup": {"module": module.__name__}},
        "middleware": ["startup"],
    })
    app = create_app(config=config, telemetry=Telemetry.disabled(), analytics=Analytics.disabled())
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def tracked_lifespan(application):
        lifespan_tasks.append(asyncio.current_task())
        try:
            async with original_lifespan(application):
                yield
        finally:
            lifespan_tasks.append(asyncio.current_task())

    app.router.lifespan_context = tracked_lifespan
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: app)
    monkeypatch.setattr(cli, "_ManagedServer", Server)
    monkeypatch.setattr("gateway7.app.build_provider", lambda *args, **kwargs: Provider())

    async def run():
        try:
            await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
        except asyncio.CancelledError as error:
            cancellations.append(error)
            raise

    previous_tasks = asyncio.all_tasks()
    task = asyncio.create_task(run())
    original_cancellation = object()
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel(original_cancellation)
        await asyncio.wait_for(returned.wait(), timeout=1)
        await asyncio.wait_for(shutdown_started.wait(), timeout=1)
        assert all(name not in os.environ for name in values)
        assert not task.done() and not provider_closed.is_set()
        task.cancel("second cancellation during cleanup")
        release_shutdown.set()
        finished, _ = await asyncio.wait({task}, timeout=1)
        assert task in finished, "Cancelled startup did not finish its owned cleanup"
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value is cancellations[0]
        assert caught.value.args == (original_cancellation,)
        assert events == ["shutdown", "provider_close"] and provider_closed.is_set()
        assert len(lifespan_tasks) == 2 and lifespan_tasks[0] is lifespan_tasks[1]
        assert all(name not in os.environ for name in values)
        assert asyncio.all_tasks() == previous_tasks
    finally:
        # Also reap the old implementation when its pending finish signal makes
        # the regression fail, so a failing test cannot leave a lifecycle job.
        release_shutdown.set()
        if not task.done():
            if lifespan_tasks and not lifespan_tasks[0].done():
                lifespan_tasks[0].cancel()
            task.cancel()
        await asyncio.gather(task, *lifespan_tasks, return_exceptions=True)
        assert provider_closed.is_set() and all(name not in os.environ for name in values)
        assert asyncio.all_tasks() == previous_tasks

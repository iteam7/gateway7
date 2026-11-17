"""The authoring dev service owns its real loopback HTTP processes and credentials."""

import json
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
import yaml

from gateway7.scaffold import create_plugin_project


def _request(origin, path, token=None, body=None, *, early=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if early:
        headers["X-Gateway7-Stream-Mode"] = "early"
    request = urllib.request.Request(
        origin + path, None if body is None else json.dumps(body).encode(), headers
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def _start(project, *, port=0):
    environment = {
        **os.environ,
        "OPENAI_API_KEY": "SYNTHETIC_PARENT_KEY_MUST_NOT_BE_INHERITED",
        "COMPANY_PRIVATE_VALUE": "SYNTHETIC_PARENT_VALUE_MUST_NOT_BE_INHERITED",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "gateway7", "plugin", "dev", str(project), "--port", str(port)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    received = queue.Queue()

    def reader():
        for line in process.stdout:
            received.put(line.strip())

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return process, received, thread


def _ready(process, lines):
    result = []
    try:
        for _ in range(4):
            result.append(lines.get(timeout=35))
    except queue.Empty:
        _stop(process)
        pytest.fail("Plugin development server did not announce readiness")
    assert result[0].startswith("Plugin development gateway: http://127.0.0.1:")
    assert result[1].startswith("Owned synthetic upstream: http://127.0.0.1:")
    token = re.search(r"gateway7-synthetic-client-[A-Za-z0-9_-]+", result[3]).group()
    return result[0].split(": ", 1)[1], result[1].split(": ", 1)[1], token


def _stop(process):
    if process.poll() is None:
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            pytest.fail("Plugin dev did not stop after interruption")
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()


def _assert_port_released(origin):
    port = int(origin.rsplit(":", 1)[1])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with socket.socket() as client:
            client.settimeout(0.1)
            if client.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.05)
    pytest.fail("An owned development server remained reachable after cleanup")


def _attempts(origin):
    status, text = _request(origin, "/metrics")
    assert status == 200
    return sum(
        float(value)
        for value in re.findall(
            r"^gateway7_provider_calls_total\{[^\n]+\} ([0-9.eE+\-]+)$", text, re.M
        )
    )


@pytest.mark.parametrize("template", ["guard", "redact"])
def test_dev_current_project_http_profiles_and_owned_cleanup(tmp_path, template):
    project = create_plugin_project("authoring_http", tmp_path, template)
    config_path = project / "gateway.yaml"
    config = yaml.safe_load(config_path.read_text())
    database = tmp_path / "must-not-be-created.sqlite"
    config["provider"] = {
        "kind": "openai",
        "model": "real-model-not-used",
        "transport": {"module": "must_not_import_transport", "settings": {}},
    }
    config["auth"] = {
        "enabled": True,
        "operator_token_env": "REAL_OPERATOR_MUST_NOT_RESOLVE",
        "management_db": str(database),
        "clients": {},
    }
    config_path.write_text(yaml.safe_dump(config))
    plugin = project / "gateway7_plugin_authoring_http" / "plugin.py"
    plugin.write_text(
        'import os\nassert "OPENAI_API_KEY" not in os.environ\nassert "COMPANY_PRIVATE_VALUE" not in os.environ\n'
        + plugin.read_text()
    )
    original = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    process, lines, reader = _start(project)
    gateway = upstream = None
    try:
        gateway, upstream, token = _ready(process, lines)
        assert _request(gateway, "/health")[0] == 200
        assert _request(gateway, "/v1/models", token)[0] == 200
        status, answer = _request(
            gateway,
            "/chat",
            token,
            {"model": "synthetic-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert status == 200 and json.loads(answer)["text"] == "pong — hello"
        tools = {
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        }
        status, answer = _request(gateway, "/v1/chat/completions", token, tools)
        assert status == 200
        call = json.loads(answer)["choices"][0]["message"]["tool_calls"][0]
        assert call["function"] == {"name": "echo", "arguments": "{}"} and call["id"]
        status, answer = _request(
            gateway, "/v1/responses", token, {"model": "synthetic-model", "input": "hello"}
        )
        assert (
            status == 200
            and json.loads(answer)["output"][0]["content"][0]["text"] == "pong — hello"
        )
        for path, body in [
            (
                "/v1/chat/completions",
                {
                    "model": "synthetic-model",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            ),
            ("/v1/responses", {"model": "synthetic-model", "stream": True, "input": "hello"}),
        ]:
            before = _attempts(gateway)
            status, answer = _request(gateway, path, token, body, early=True)
            if template == "guard":
                assert status == 200, answer
                assert "pong" in answer and "hello" in answer
                assert (
                    "[DONE]" if path.endswith("completions") else "response.completed"
                ) in answer
            else:
                assert status == 400 and _attempts(gateway) == before
        before = _attempts(gateway)
        status, answer = _request(
            gateway,
            "/chat",
            token,
            {"model": "synthetic-model", "messages": [{"role": "user", "content": "PRIVATE-TEST"}]},
        )
        if template == "guard":
            assert status == 403 and _attempts(gateway) == before
        else:
            assert status == 200 and json.loads(answer)["text"] == "pong — [removed]"
        assert not database.exists()
        assert original == {
            str(path.relative_to(project)): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }
    finally:
        _stop(process)
        reader.join(timeout=2)
    assert process.returncode == 0
    _assert_port_released(gateway)
    _assert_port_released(upstream)


def test_dev_startup_failure_does_not_overwrite_project_or_other_listener(tmp_path):
    project = create_plugin_project("occupied", tmp_path)
    original = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        process, lines, reader = _start(project, port=occupied.getsockname()[1])
        try:
            assert process.wait(timeout=15) == 2
        finally:
            _stop(process)
            reader.join(timeout=2)
    assert original == {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }


@pytest.mark.skipif(os.name == "nt", reason="POSIX controlling-terminal interruption")
def test_dev_terminal_ctrl_c_reaps_child_and_closes_both_listeners(tmp_path):
    import pty
    import select

    project = create_plugin_project("terminal", tmp_path, "guard")
    child, terminal = pty.fork()
    if child == 0:
        os.execv(sys.executable, [sys.executable, "-m", "gateway7", "plugin", "dev", str(project)])
    data = b""
    reaped = False
    origins = []
    try:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and b"gateway7-synthetic-client-" not in data:
            if select.select([terminal], [], [], 0.2)[0]:
                data += os.read(terminal, 8192)
        origins = re.findall(rb"(?:gateway|upstream): (http://127\.0\.0\.1:\d+)", data)
        assert len(origins) == 2, data.decode(errors="replace")
        os.write(terminal, b"\x03")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            ended, status = os.waitpid(child, os.WNOHANG)
            if ended:
                reaped = True
                assert os.waitstatus_to_exitcode(status) == 0
                break
            time.sleep(0.05)
        assert reaped, "Terminal Ctrl-C did not complete the dev supervisor"
        for origin in origins:
            _assert_port_released(origin.decode())
    finally:
        if not reaped:
            os.kill(child, signal.SIGTERM)
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline:
                ended, _ = os.waitpid(child, os.WNOHANG)
                if ended:
                    reaped = True
                    break
                time.sleep(0.05)
            if not reaped:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
        os.close(terminal)

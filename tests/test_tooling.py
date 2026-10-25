"""Scaffold and offline execution work with isolated processes and synthetic data."""

import json
import os
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

import pytest
import yaml

from gateway7.cli import main
from gateway7.errors import StartupError
from gateway7.offline import MAX_FILE_BYTES, load_fixtures, run_offline
from gateway7.scaffold import create_plugin_project


def test_generated_project_passes_offline_and_mismatch_exits_one(tmp_path, capsys):
    assert main(["plugin", "init", "sample", "--directory", str(tmp_path)]) == 0
    project = tmp_path / "sample"
    assert (project / "pyproject.toml").is_file()
    assert (project / "gateway7_plugin_sample" / "plugin.py").is_file()
    capsys.readouterr()
    arguments = [
        "plugin",
        "test",
        "--config",
        str(project / "gateway.yaml"),
        "--fixtures",
        str(project / "fixtures.json"),
        "--json",
    ]
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is True and report["total"] == 2 and report["failed"] == 0
    response = next(check for check in report["cases"][0]["checks"] if check["field"] == "response")
    assert response["actual"]["text"] == response["expected"]["text"] == "Answer [removed]"
    fixtures = json.loads((project / "fixtures.json").read_text())
    fixtures["cases"][0]["expected"]["response"]["text"] = "Deliberately wrong expected value"
    (project / "fixtures.json").write_text(json.dumps(fixtures))
    assert main(arguments) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["failed"] == 1 and report["cases"][0]["passed"] is False
    response = next(check for check in report["cases"][0]["checks"] if check["field"] == "response")
    assert response["actual"]["text"] == "Answer [removed]"
    assert response["expected"]["text"] == "Deliberately wrong expected value"


@pytest.mark.parametrize(
    "name", ["../escape", "a/b", "a.b", "a-b", "class", "_private", "Upper", "a" * 49, "con"]
)
def test_scaffold_rejects_unsafe_or_nonportable_identifiers_without_output(name, tmp_path):
    with pytest.raises(StartupError):
        create_plugin_project(name, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("existing", ["file", "directory", "symlink"])
def test_scaffold_never_overwrites_existing_target(existing, tmp_path):
    target = tmp_path / "sample"
    if existing == "file":
        target.write_text("keep me")
    elif existing == "directory":
        target.mkdir()
        (target / "keep").write_text("keep me")
    else:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "keep").write_text("keep me")
        try:
            target.symlink_to(elsewhere, target_is_directory=True)
        except OSError:
            pytest.skip("Symlinks unavailable")
    with pytest.raises(StartupError, match="already exists"):
        create_plugin_project("sample", tmp_path)
    if existing == "file":
        assert target.read_text() == "keep me"
    else:
        assert (target / "keep").read_text() == "keep me"
        assert len(list(target.iterdir())) == 1


def test_offline_real_provider_config_uses_no_credentials_and_suppresses_plugin_output(
    tmp_path, monkeypatch, capsys
):
    project = create_plugin_project("sample", tmp_path)
    config = yaml.safe_load((project / "gateway.yaml").read_text())
    config["provider"] = {
        "kind": "claude",
        "model": "configured-test-model",
        "key_env": "SYNTHETIC_PROVIDER_SECRET",
    }
    config["auth"] = {
        "enabled": True,
        "clients": {
            "test": {"token_env": "SYNTHETIC_GATEWAY_SECRET", "models": ["configured-test-model"]}
        },
    }
    (project / "gateway.yaml").write_text(yaml.safe_dump(config))
    module = project / "gateway7_plugin_sample" / "plugin.py"
    module.write_text(
        "import os, sys\n"
        "assert 'SYNTHETIC_PROVIDER_SECRET' not in os.environ\n"
        "assert 'SYNTHETIC_GATEWAY_SECRET' not in os.environ\n"
        "print('PLUGIN-NOISE-' * 10000)\n"
        "print('PLUGIN-STDERR', file=sys.stderr)\n" + module.read_text()
    )
    monkeypatch.setenv("SYNTHETIC_PROVIDER_SECRET", "synthetic-provider-secret")
    monkeypatch.setenv("SYNTHETIC_GATEWAY_SECRET", "synthetic-gateway-secret")
    assert (
        main(
            [
                "plugin",
                "test",
                "--config",
                str(project / "gateway.yaml"),
                "--fixtures",
                str(project / "fixtures.json"),
                "--json",
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["passed"] and not output.err
    assert "PLUGIN-NOISE" not in output.out and "synthetic-provider-secret" not in output.out


def test_network_is_blocked_during_import_factory_startup_and_handler(tmp_path):
    project = create_plugin_project("sample", tmp_path)
    module = project / "gateway7_plugin_sample" / "plugin.py"
    original = module.read_text()
    probe = (
        "import socket\n"
        "def probe():\n"
        "    with socket.socket() as connection:\n"
        "        try:\n"
        "            connection.connect(('127.0.0.1', 9))\n"
        "        except PermissionError:\n"
        "            return\n"
        "        raise AssertionError('network guard missing')\n"
        "probe()\n"
    )
    source = probe + original
    source = source.replace(
        "    async def handle(",
        "    async def startup(self):\n        probe()\n\n    async def handle(",
    )
    source = source.replace(
        "        processed = request.model_copy",
        "        probe()\n        processed = request.model_copy",
    )
    source = source.replace(
        "    return LiteralMask(settings)", "    probe()\n    return LiteralMask(settings)"
    )
    module.write_text(source)
    code, report = run_offline(project / "gateway.yaml", project / "fixtures.json")
    assert code == 0 and report["passed"]


def test_httpx_network_attempt_cannot_leave_offline_worker(tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"synthetic")

        def log_message(self, *_arguments):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        project = create_plugin_project("sample", tmp_path)
        module = project / "gateway7_plugin_sample" / "plugin.py"
        source = module.read_text().replace(
            "        processed = request.model_copy",
            "        import httpx\n        async with httpx.AsyncClient(trust_env=False) as client:\n            try:\n"
            f"                await client.get('http://127.0.0.1:{server.server_port}', timeout=1)\n"
            "            except httpx.ConnectError:\n                pass\n            else:\n                raise AssertionError('network guard missing')\n        processed = request.model_copy",
        )
        module.write_text(source)
        code, report = run_offline(project / "gateway.yaml", project / "fixtures.json")
        assert code == 0 and report["passed"]
        assert requests == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_offline_wall_clock_limit_terminates_noncooperative_plugin(tmp_path):
    project = create_plugin_project("sample", tmp_path)
    module = project / "gateway7_plugin_sample" / "plugin.py"
    module.write_text("while True:\n    pass\n")
    started = time.monotonic()
    code, report = run_offline(project / "gateway.yaml", project / "fixtures.json", timeout=1)
    assert code == 2 and "wall-clock" in report["error"]
    assert time.monotonic() - started < 5


def test_offline_checks_request_response_denial_and_provider_failure(tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "plugins": {
                    "guard": {
                        "module": "gateway7.plugins.content_policy",
                        "settings": {"terms": ["BLOCK-ME-TEST"], "action": "block"},
                    }
                },
                "middleware": ["guard"],
            }
        )
    )
    fixtures = tmp_path / "fixtures.json"
    ordinary = {"messages": [{"role": "user", "content": "safe"}]}
    fixtures.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "name": "request denied",
                        "request": {"messages": [{"role": "user", "content": "BLOCK-ME-TEST"}]},
                        "expected": {"provider_calls": 0, "error": "policy_denied"},
                    },
                    {
                        "name": "response denied",
                        "request": ordinary,
                        "provider_response": {"text": "BLOCK-ME-TEST"},
                        "expected": {
                            "provider_calls": 1,
                            "request": ordinary,
                            "error": "policy_denied",
                        },
                    },
                    {
                        "name": "provider failure",
                        "request": ordinary,
                        "provider_error": True,
                        "expected": {
                            "provider_calls": 1,
                            "request": ordinary,
                            "error": "provider_error",
                        },
                    },
                ],
            }
        )
    )
    code, report = run_offline(config, fixtures)
    assert code == 0 and report["total"] == 3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version=True),
        lambda data: data.update(schema_version=2),
        lambda data: data["cases"][0]["expected"].update(provider_calls=True),
        lambda data: data["cases"].append(data["cases"][0]),
        lambda data: data["cases"][0]["expected"].update(error="policy_denied"),
        lambda data: data["cases"][0].update(unknown="synthetic-secret-value"),
    ],
)
def test_fixture_schema_rejects_invalid_contract_without_echoing_values(tmp_path, mutation):
    project = create_plugin_project("sample", tmp_path)
    fixture = project / "fixtures.json"
    data = json.loads(fixture.read_text())
    mutation(data)
    fixture.write_text(json.dumps(data))
    with pytest.raises(StartupError) as caught:
        load_fixtures(fixture)
    assert "synthetic-secret-value" not in str(caught.value)


def test_fixture_file_is_bounded_and_duplicate_keys_rejected(tmp_path):
    fixture = tmp_path / "fixtures.json"
    for raw in [b" " * (MAX_FILE_BYTES + 1), b'{"schema_version":1,"schema_version":1,"cases":[]}']:
        fixture.write_bytes(raw)
        with pytest.raises(StartupError):
            load_fixtures(fixture)


def test_human_report_includes_expected_actual_and_invalid_json_mode_is_structured(
    tmp_path, capsys
):
    project = create_plugin_project("sample", tmp_path)
    assert (
        main(
            [
                "plugin",
                "test",
                "--config",
                str(project / "gateway.yaml"),
                "--fixtures",
                str(project / "fixtures.json"),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "expected:" in output and "actual:" in output and "2/2 cases passed" in output
    assert (
        main(
            [
                "plugin",
                "test",
                "--config",
                str(tmp_path / "missing"),
                "--fixtures",
                str(project / "fixtures.json"),
                "--json",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is False and "error" in report


@pytest.mark.skipif(
    os.name == "nt", reason="Windows terminate is an immediate kill, not a POSIX signal"
)
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_interrupted_offline_parent_reports_failure_and_reaps_worker(tmp_path, signum):
    project = create_plugin_project("sample", tmp_path)
    marker = project / "worker.pid"
    module = project / "gateway7_plugin_sample" / "plugin.py"
    module.write_text(
        "import os\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "while True:\n    pass\n"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-m",
            "gateway7",
            "plugin",
            "test",
            "--config",
            str(project / "gateway.yaml"),
            "--fixtures",
            str(project / "fixtures.json"),
            "--json",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker_pid = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not marker.exists():
            assert process.poll() is None
            time.sleep(0.025)
        assert marker.exists(), "Offline worker did not start"
        worker_pid = int(marker.read_text())
        process.send_signal(signum)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 2
        report = json.loads(stdout)
        assert report["passed"] is False and "interrupted" in report["error"]
        assert "Traceback" not in stderr
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if worker_pid is not None:
            try:
                os.killpg(worker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_keyboard_interrupt_before_worker_cannot_report_success(monkeypatch, capsys):
    from gateway7 import cli

    def interrupted(*_arguments):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_offline", interrupted)
    assert (
        main(
            ["plugin", "test", "--config", "gateway.yaml", "--fixtures", "fixtures.json", "--json"]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is False and "interrupted" in report["error"]

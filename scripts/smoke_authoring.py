"""Verify authoring and a normal plugin installation beside an installed gateway wheel."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.request

from openai import DefaultHttpx2Client, OpenAI, PermissionDeniedError
import yaml

TOKEN = "gateway7-synthetic-authoring-client"
PROVIDER_KEY = "gateway7-synthetic-authoring-provider"


def port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_ready(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        assert process.poll() is None, "Installed service stopped during startup"
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.05)
    raise AssertionError("Installed service did not become ready")


def metrics(url: str) -> tuple[float, str]:
    with urllib.request.urlopen(url + "/metrics", timeout=2) as response:
        text = response.read().decode()
    values = re.findall(r"^gateway7_provider_calls_total\{[^\n]+\} ([0-9.eE+\-]+)$", text, re.M)
    return sum(float(value) for value in values), text


def stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", required=True, help="Python in the normally installed gateway wheel environment"
    )
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    # Preserve the virtualenv executable path even when it is a symlink.
    python = os.path.abspath(args.python)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    with tempfile.TemporaryDirectory(prefix="gateway7-authoring-") as temporary:
        directory = Path(temporary)
        project = directory / "smoke_mask"
        cli = [python, "-m", "gateway7"]

        def command(*arguments: str, expected_code: int = 0) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [*cli, *arguments],
                cwd=directory,
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            assert result.returncode == expected_code, (
                f"Command failed: {arguments[0]}, exit={result.returncode}; {result.stderr}"
            )
            return result

        command("plugin", "init", "smoke_mask", "--directory", str(directory))
        config_path = project / "gateway.yaml"
        fixture_path = project / "fixtures.json"
        result = command(
            "plugin",
            "test",
            "--config",
            str(config_path),
            "--fixtures",
            str(fixture_path),
            "--json",
        )
        report = json.loads(result.stdout)
        assert report["schema_version"] == 1 and report["passed"] is True
        assert report["total"] >= 2 and report["failed"] == 0

        failing = json.loads(fixture_path.read_text())
        failing["cases"][0]["expected"]["response"]["text"] = (
            "Deliberately incorrect synthetic expectation"
        )
        failed_path = directory / "failing-fixtures.json"
        failed_path.write_text(json.dumps(failing))
        result = command(
            "plugin",
            "test",
            "--config",
            str(config_path),
            "--fixtures",
            str(failed_path),
            "--json",
            expected_code=1,
        )
        report = json.loads(result.stdout)
        assert report["passed"] is False and report["failed"] >= 1
        checks = [check for case in report["cases"] for check in case["checks"]]
        assert any(
            check["passed"] is False and check["actual"] != check["expected"] for check in checks
        )

        invalid_path = directory / "invalid-fixtures.json"
        invalid_path.write_text('{"schema_version": 0}')
        result = command(
            "plugin",
            "test",
            "--config",
            str(config_path),
            "--fixtures",
            str(invalid_path),
            "--json",
            expected_code=2,
        )
        assert isinstance(json.loads(result.stdout)["error"], str)

        # A normal wheel-backed installation, never an editable source path.
        subprocess.run(
            [args.uv, "pip", "install", "--python", python, "--no-deps", str(project)],
            cwd=directory,
            env=environment,
            check=True,
            timeout=120,
        )
        imported = subprocess.run(
            [
                python,
                "-I",
                "-c",
                "import gateway7_plugin_smoke_mask.plugin as p; print(p.__file__)",
            ],
            cwd=directory,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        module_path = Path(imported.stdout.strip()).resolve()
        assert not module_path.is_relative_to(project)
        command("validate", "--config", str(config_path))

        upstream_port, gateway_port = port(), port()
        config = yaml.safe_load(config_path.read_text())
        config["provider"] = {
            "kind": "fake",
            "base_url": f"http://127.0.0.1:{upstream_port}",
            "model": "fake",
            "key_env": "GATEWAY7_DEMO_KEY",
        }
        config["auth"] = {
            "enabled": True,
            "clients": {
                "smoke": {"token_env": "GATEWAY7_SMOKE_TOKEN", "models": ["fake"]},
            },
        }
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))
        environment["GATEWAY7_DEMO_KEY"] = PROVIDER_KEY
        environment["GATEWAY7_SMOKE_TOKEN"] = TOKEN
        with (directory / "services.log").open("w") as log:
            upstream = subprocess.Popen(
                [
                    python,
                    "-m",
                    "uvicorn",
                    "gateway7.demo:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(upstream_port),
                    "--no-access-log",
                ],
                cwd=directory,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_ready(f"http://127.0.0.1:{upstream_port}/health", upstream)
                gateway = subprocess.Popen(
                    [*cli, "serve", "--config", str(config_path), "--port", str(gateway_port)],
                    cwd=directory,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    url = f"http://127.0.0.1:{gateway_port}"
                    wait_ready(url + "/ready", gateway)
                    with OpenAI(
                        base_url=url + "/v1",
                        api_key=TOKEN,
                        max_retries=0,
                        timeout=5,
                        http_client=DefaultHttpx2Client(trust_env=False, follow_redirects=False),
                    ) as client:
                        assert [model.id for model in client.models.list().data] == ["fake"]
                        answer = client.chat.completions.create(
                            model="fake",
                            messages=[{"role": "user", "content": "PRIVATE-TEST"}],
                        )
                        text = answer.choices[0].message.content
                        assert (
                            text is not None and "[removed]" in text and "PRIVATE-TEST" not in text
                        )
                        before, _ = metrics(url)
                        try:
                            client.chat.completions.create(
                                model="forbidden-model",
                                messages=[{"role": "user", "content": "ping"}],
                            )
                        except PermissionDeniedError:
                            pass
                        else:
                            raise AssertionError("Forbidden model reached the installed server")
                        after, exposed = metrics(url)
                        assert before == after == 1
                        assert TOKEN not in exposed and PROVIDER_KEY not in exposed
                finally:
                    stop(gateway)
            finally:
                stop(upstream)
        print(
            "Generated plugin: offline pass/fail reports, normal install, validation and authorized SDK HTTP passed"
        )


if __name__ == "__main__":
    main()

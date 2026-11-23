"""Exercise authoring from an installed wheel, outside its checkout, on every supported OS."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request


def request(url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    operation = urllib.request.Request(
        url, None if body is None else json.dumps(body).encode(), headers
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(operation, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def stop(process, *, interrupt=False):
    if process.poll() is None:
        if interrupt:
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        else:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise AssertionError("Owned service did not stop") from None


def released(origin):
    port = int(origin.rsplit(":", 1)[1])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with socket.socket() as client:
            client.settimeout(0.1)
            if client.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.05)
    raise AssertionError("Owned development listener survived shutdown")


def wait_ready(origin, process):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        assert process.poll() is None, "Owned installed service stopped during startup"
        try:
            if request(origin + "/health")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.05)
    raise AssertionError("Installed service did not become ready")


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def dev_flow(cli, project, environment, *, template):
    process = subprocess.Popen(
        [*cli, "plugin", "dev", str(project)],
        cwd=project.parent,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    lines = queue.Queue()

    def read_lines():
        for line in process.stdout:
            lines.put(line.strip())

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()
    origins = []
    try:
        announced = [lines.get(timeout=35) for _ in range(4)]
        for marker, line in zip(
            ("Plugin development gateway: ", "Owned synthetic upstream: "), announced[:2]
        ):
            assert line.startswith(marker + "http://127.0.0.1:")
            origins.append(line[len(marker) :])
        token = re.search(r"gateway7-synthetic-client-[A-Za-z0-9_-]+", announced[3]).group()
        for text, expected in [
            ("hello", "pong — hello"),
            ("PRIVATE-TEST", None if template == "guard" else "pong — [removed]"),
        ]:
            status, response = request(
                origins[0] + "/chat",
                token,
                {"messages": [{"role": "user", "content": text}], "model": "synthetic-model"},
            )
            assert status == (403 if expected is None else 200), response
            if expected:
                assert json.loads(response)["text"] == expected
        if template == "guard":
            status, _ = request(
                origins[0] + "/chat",
                token,
                {"messages": [{"role": "user", "content": "SOURCE-ONLY"}]},
            )
            assert status == 403, "Dev must use edited project source rather than installed wheel"
    except queue.Empty:
        raise AssertionError("Installed dev command did not announce startup") from None
    finally:
        stop(process, interrupt=True)
        if process.stdout:
            process.stdout.close()
        reader.join(timeout=2)
    assert process.returncode == 0, (
        f"Ctrl-C should cleanly stop the dev supervisor (exit code {process.returncode})"
    )
    for origin in origins:
        released(origin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", required=True, help="Python containing the installed gateway wheel"
    )
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    python = os.path.abspath(args.python)
    cli = [python, "-I", "-m", "gateway7"]
    # Builds retain only the OS/cache/TLS/proxy settings they need, never live
    # model, gateway or telemetry credentials from the invoking environment.
    names = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TMP",
        "TEMP",
        "HOME",
        "USERPROFILE",
        "UV_CACHE_DIR",
        "UV_NATIVE_TLS",
        "UV_SYSTEM_CERTS",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    environment = {name: os.environ[name] for name in names if name in os.environ}
    environment["OPENAI_API_KEY"] = "SYNTHETIC_PARENT_KEY_MUST_NOT_REACH_PLUGIN"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="gateway7-authoring-") as temporary:
        root = Path(temporary)

        def command(*arguments, expected_code=0, cwd=root):
            result = subprocess.run(
                [*cli, *arguments],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode == expected_code, (
                f"Command {arguments[:2]} returned {result.returncode}: {result.stdout} {result.stderr}"
            )
            return result

        for template, count in [("guard", 12), ("redact", 10)]:
            name = "smoke_" + template
            command("plugin", "init", name, "--template", template, "--directory", str(root))
            project = root / name
            # Install only the documented dev group: never resolve the generated
            # project's unpublished Gateway7 requirement from a package index.
            subprocess.run(
                [args.uv, "pip", "install", "--python", python, "--group", "dev"],
                cwd=project,
                env=environment,
                check=True,
                timeout=120,
            )

            def dev_checks():
                for arguments in (
                    ("ruff", "format", "--check", "."),
                    ("ruff", "check", "."),
                    ("mypy",),
                ):
                    subprocess.run(
                        [python, "-m", *arguments],
                        cwd=project,
                        env=environment,
                        check=True,
                        timeout=60,
                    )

            dev_checks()
            inspection = json.loads(command("plugin", "inspect", str(project), "--json").stdout)
            assert inspection["schema_version"] == 2
            report = json.loads(command("plugin", "test", str(project), "--json").stdout)
            assert report["passed"] is True and report["total"] == count
            assert len(report["capabilities"]["tested_profiles"]) == (
                5 if template == "guard" else 3
            )
            subprocess.run(
                [python, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=project,
                env=environment,
                check=True,
                timeout=30,
            )
            source = project / ("gateway7_plugin_" + name) / "plugin.py"
            if template == "guard":
                fixtures = project / "fixtures.json"
                suite = json.loads(fixtures.read_text())
                suite["cases"].append(
                    {
                        "name": "new synthetic rule",
                        "profile": "chat",
                        "request": {"messages": [{"role": "user", "content": "SYNTHETIC-BLOCK"}]},
                        "provider_response": {"text": "Ordinary answer"},
                        "expected": {"provider_calls": 0, "error": "policy_denied"},
                    }
                )
                fixtures.write_text(json.dumps(suite), encoding="utf-8")
                red = json.loads(
                    command("plugin", "test", str(project), "--json", expected_code=1).stdout
                )
                assert red["failed"] == 1
                source.write_text(
                    source.read_text().replace(
                        "hits = text.count(settings.term)",
                        'hits = text.count(settings.term) + text.count("SYNTHETIC-BLOCK")',
                    ),
                    encoding="utf-8",
                )
                assert json.loads(command("plugin", "test", str(project), "--json").stdout)[
                    "passed"
                ]
            dev_checks()
            # Normal installation is proven separately from explicit source-mode test/dev.
            subprocess.run(
                [args.uv, "build", "--wheel", "--out-dir", str(project / "dist"), str(project)],
                cwd=root,
                env=environment,
                check=True,
                timeout=120,
            )
            wheel = next((project / "dist").glob("*.whl"))
            subprocess.run(
                [args.uv, "pip", "install", "--python", python, "--no-deps", str(wheel)],
                cwd=root,
                env=environment,
                check=True,
                timeout=120,
            )
            installed = subprocess.run(
                [
                    python,
                    "-I",
                    "-c",
                    f"import gateway7_plugin_{name}.plugin as p; print(p.__file__)",
                ],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            assert not Path(installed.stdout.strip()).resolve().is_relative_to(project)
            command("validate", "--config", str(project / "gateway.yaml"))
            # A different local rule must affect dev but never the installed wheel.
            if template == "guard":
                source.write_text(
                    source.read_text().replace(
                        'text.count("SYNTHETIC-BLOCK")',
                        'text.count("SYNTHETIC-BLOCK") + text.count("SOURCE-ONLY")',
                    ),
                    encoding="utf-8",
                )
            source.write_text(
                'import os\nassert "OPENAI_API_KEY" not in os.environ\n' + source.read_text(),
                encoding="utf-8",
            )
            before = {
                str(p.relative_to(project)): p.read_bytes()
                for p in project.rglob("*")
                if p.is_file()
            }
            dev_flow(cli, project, environment, template=template)
            assert before == {
                str(p.relative_to(project)): p.read_bytes()
                for p in project.rglob("*")
                if p.is_file()
            }
            # Hide source and run the ordinary installed gateway from a neutral cwd.
            package = project / ("gateway7_plugin_" + name)
            package.rename(project / "hidden-source")
            upstream_port, gateway_port = free_port(), free_port()
            private = root / (name + "-installed.yaml")
            private.write_text(
                f"provider:\n  kind: fake\n  model: fake\n  base_url: http://127.0.0.1:{upstream_port}\n"
                "  key_env: GATEWAY7_DEMO_KEY\nauth:\n  enabled: true\n  clients:\n    smoke:\n"
                "      token_env: GATEWAY7_SMOKE_TOKEN\nplugins:\n  sample:\n"
                f"    module: gateway7_plugin_{name}.plugin\n    required: true\n"
                "    settings:\n      term: PRIVATE-TEST\nmiddleware: [sample]\n",
                encoding="utf-8",
            )
            service_env = {
                **environment,
                "GATEWAY7_DEMO_KEY": "gateway7-synthetic-provider-smoke",
                "GATEWAY7_SMOKE_TOKEN": "gateway7-synthetic-client-smoke",
            }
            upstream = subprocess.Popen(
                [
                    python,
                    "-I",
                    "-m",
                    "uvicorn",
                    "gateway7.demo:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(upstream_port),
                    "--no-access-log",
                ],
                cwd=root,
                env=service_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            gateway = None
            try:
                wait_ready(f"http://127.0.0.1:{upstream_port}", upstream)
                gateway = subprocess.Popen(
                    [*cli, "serve", "--config", str(private), "--port", str(gateway_port)],
                    cwd=root,
                    env=service_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                origin = f"http://127.0.0.1:{gateway_port}"
                wait_ready(origin, gateway)
                status, response = request(
                    origin + "/chat",
                    service_env["GATEWAY7_SMOKE_TOKEN"],
                    {"messages": [{"role": "user", "content": "SOURCE-ONLY"}]},
                )
                assert status == 200 and json.loads(response)["text"] == "pong — SOURCE-ONLY"
                status, response = request(
                    origin + "/chat",
                    service_env["GATEWAY7_SMOKE_TOKEN"],
                    {"messages": [{"role": "user", "content": "PRIVATE-TEST"}]},
                )
                assert status == (403 if template == "guard" else 200)
                if template == "redact":
                    assert json.loads(response)["text"] == "pong — [removed]"
            finally:
                if gateway is not None:
                    stop(gateway)
                stop(upstream)
            released(f"http://127.0.0.1:{gateway_port}")
            released(f"http://127.0.0.1:{upstream_port}")
            print(
                f"Installed authoring: {template}, Ruff/mypy, red/green, profiles, source dev, wheel HTTP, cleanup PASS"
            )


if __name__ == "__main__":
    main()

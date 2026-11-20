"""Own a disposable loopback gateway for one explicitly selected plugin project."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

from gateway7.errors import StartupError
from gateway7.offline import _cancellation_signals, _terminate_worker
from gateway7.plugin_project import load_project


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _terminate_worker(process)


def run_plugin_dev(project: str | Path = ".", *, port: int = 0) -> int:
    """Run current project source in an owned child; never touch production config."""
    try:
        selected = load_project(project)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError
    except (StartupError, OSError, ValueError):
        print("Plugin dev: invalid project or port; run 'gateway7 plugin inspect PROJECT'.")
        return 2
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
        if name in os.environ
    }
    environment.update(
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        PYTHONDONTWRITEBYTECODE="1",
        GATEWAY7_DEV_PROVIDER_TOKEN="gateway7-synthetic-provider-" + secrets.token_urlsafe(24),
        GATEWAY7_DEV_CLIENT_TOKEN="gateway7-synthetic-client-" + secrets.token_urlsafe(24),
    )
    try:
        with _cancellation_signals() as cancellation:
            with tempfile.TemporaryDirectory(prefix="gateway7-plugin-dev-") as temporary:
                status_file = Path(temporary) / "status.json"
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-m",
                        "gateway7._plugin_dev_worker",
                        str(selected.root),
                        str(port),
                        str(status_file),
                    ],
                    cwd=temporary,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=os.name != "nt",
                )
                try:
                    deadline = time.monotonic() + 30
                    status = None
                    while not cancellation.requested and process.poll() is None:
                        if status_file.exists():
                            with status_file.open("rb") as source:
                                raw = source.read(16385)
                            if len(raw) > 16384:
                                raise ValueError
                            status = json.loads(raw)
                            break
                        if time.monotonic() >= deadline:
                            print(
                                "Plugin dev: startup timed out; run inspect/test and check startup hooks."
                            )
                            return 2
                        time.sleep(0.05)
                    if cancellation.requested:
                        return 0
                    if status is None or status.get("status") != "ready":
                        print(
                            "Plugin dev: startup failed; run 'gateway7 plugin inspect PROJECT' and 'gateway7 plugin test PROJECT'; allow loopback sockets or use --port 0."
                        )
                        return 2
                    origin = status["gateway_url"]
                    token = environment["GATEWAY7_DEV_CLIENT_TOKEN"]
                    print("Plugin development gateway: " + origin, flush=True)
                    print("Owned synthetic upstream: " + status["upstream_url"], flush=True)
                    print(
                        "Current project source; synthetic credentials and responses only. Ctrl-C stops both servers.",
                        flush=True,
                    )
                    command = f"gateway7 chat --url {origin} --model synthetic-model --message 'Hello synthetic'"
                    if os.name == "nt":
                        print(
                            f'$env:GATEWAY7_TOKEN="{token}"; {command}; Remove-Item Env:GATEWAY7_TOKEN',
                            flush=True,
                        )
                    else:
                        print(f"GATEWAY7_TOKEN={token} {command}", flush=True)
                    while process.poll() is None and not cancellation.requested:
                        time.sleep(0.1)
                    return 0 if cancellation.requested or process.returncode == 0 else 2
                finally:
                    _stop(process)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("Plugin dev could not start or complete; inspect the project and retry.")
        return 2

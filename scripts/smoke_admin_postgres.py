"""Check PostgreSQL administration over real HTTP in an isolated Compose project.

Uses only disposable synthetic credentials and the packaged synthetic upstream.
The project, containers and database volume are removed even when a check fails.
Run after building gateway7:local; no production service or database is contacted.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def _request(
    origin: str,
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    operator_write: bool = False,
    revision: int | None = None,
) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if operator_write:
        headers["X-Gateway7-Operator"] = "true"
        if revision is not None:
            headers["If-Match"] = str(revision)
    request = urllib.request.Request(
        origin + path,
        None if body is None else json.dumps(body).encode(),
        headers,
        method=method,
    )
    # Ignore machine-wide proxies for this local, disposable stack.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read(2_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(2_000_000)


def _ready(origin: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            status, _ = _request(origin, "/ready")
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Isolated PostgreSQL gateway did not become ready")


def check_postgres_admin() -> None:
    project = "gateway7-admin-smoke-" + secrets.token_hex(6)
    operator = "gateway7-synthetic-operator-" + secrets.token_hex(16)
    password = "gateway7-synthetic-database-" + secrets.token_hex(16)
    provider = "gateway7-synthetic-provider-" + secrets.token_hex(16)
    user_id = "synthetic_admin_" + secrets.token_hex(8)
    issued_tokens: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gateway7-admin-smoke-") as directory:
        fixture = Path(directory)
        config = fixture / "gateway.json"
        config.write_text(
            json.dumps(
                {
                    "provider": {
                        "kind": "fake",
                        "base_url": "http://127.0.0.1:8001",
                        "key_env": "GATEWAY7_DEMO_KEY",
                        "model": "fake",
                        "allowed_models": ["fake", "alternate"],
                    },
                    "auth": {
                        "enabled": True,
                        "operator_token_env": "GATEWAY7_OPERATOR_TOKEN",
                        "management_database_url_env": "GATEWAY7_DATABASE_URL",
                        "clients": {},
                    },
                    "plugins": {
                        "email": {"module": "gateway7.plugins.email_mask"},
                        "phone": {"module": "gateway7.plugins.phone_mask"},
                    },
                    "middleware": ["email"],
                }
            ),
            encoding="utf-8",
        )
        # The unprivileged image needs to read the mounted synthetic config.
        config.chmod(0o644)
        override = fixture / "smoke.yaml"
        override.write_text(
            """services:
  gateway:
    # Keep the synthetic provider on loopback, as production validation requires.
    network_mode: service:smoke-upstream
    ports: !reset []
    depends_on:
      smoke-upstream:
        condition: service_healthy
    environment:
      TELEMETRY_ENABLED: "false"
      ANALYTICS_ENABLED: "false"
  smoke-upstream:
    image: gateway7:local
    ports: ["127.0.0.1::8000"]
    entrypoint: ["python", "-m", "uvicorn", "gateway7.demo:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log", "--log-level", "warning"]
    command: []
    environment:
      GATEWAY7_DEMO_KEY: ${GATEWAY7_DEMO_KEY}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).close()"]
      interval: 1s
      timeout: 3s
      retries: 30
      start_period: 1s
    read_only: true
    tmpfs: ["/tmp:size=16m,mode=1777"]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    mem_limit: 256m
""",
            encoding="utf-8",
        )
        environment = {
            **os.environ,
            "GATEWAY_CONFIG_FILE": str(config),
            "GATEWAY_KEY_ENV": "GATEWAY7_DEMO_KEY",
            "GATEWAY7_DEMO_KEY": provider,
            "GATEWAY7_OPERATOR_TOKEN": operator,
            "GATEWAY7_POSTGRES_PASSWORD": password,
            # Override any caller's actual database configuration.
            "GATEWAY7_DATABASE_URL": "postgresql://gateway7@postgres:5432/gateway7",
        }
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--file",
            str(ROOT / "compose.yaml"),
            "--file",
            str(ROOT / "compose.admin.yaml"),
            "--file",
            str(override),
        ]

        def compose(*arguments: str, timeout: int = 180) -> str:
            result = subprocess.run(
                [*command, *arguments],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode:
                # Keep diagnostics private and redact the synthetic capabilities;
                # never print expanded Compose environment values into CI logs.
                logs = subprocess.run(
                    [
                        *command,
                        "logs",
                        "--no-color",
                        "--tail",
                        "30",
                        "gateway",
                        "postgres",
                        "smoke-upstream",
                    ],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                details = result.stderr + "\n" + logs.stdout + logs.stderr
                for secret in [
                    operator,
                    password,
                    provider,
                    environment["GATEWAY7_DATABASE_URL"],
                    *issued_tokens,
                ]:
                    details = details.replace(secret, "[redacted]")
                descriptor, diagnostic_path = tempfile.mkstemp(
                    prefix="gateway7-admin-smoke-failure-", suffix=".txt"
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as diagnostic:
                    diagnostic.write(details)
                print(f"Private redacted Compose diagnostics: {diagnostic_path}", flush=True)
                raise RuntimeError(
                    f"Isolated PostgreSQL Compose operation failed ({arguments[0]}, exit {result.returncode})"
                )
            return result.stdout.strip()

        def api(
            path: str,
            *,
            expected: int = 200,
            credential: str | None = operator,
            method: str = "GET",
            body: dict[str, Any] | None = None,
            write: bool = False,
        ) -> dict[str, Any]:
            revision = None
            if write:
                status, state = _request(origin, "/operator/state", token=operator)
                assert status == 200
                revision = json.loads(state)["revision"]
            status, response = _request(
                origin,
                path,
                token=credential,
                method=method,
                body=body,
                operator_write=write,
                revision=revision,
            )
            assert status == expected, (
                f"Admin smoke {method} {path.split('?')[0]} returned HTTP {status}; expected {expected}"
            )
            return {} if not response else json.loads(response)

        def chat(credential: str, *, model: str = "fake", expected: int = 200) -> None:
            response = api(
                "/chat",
                credential=credential,
                expected=expected,
                method="POST",
                body={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "SYNTHETIC_ADMIN_SMOKE_MESSAGE synthetic@example.invalid +7 999 123-45-67",
                        }
                    ],
                },
            )
            if expected == 200:
                assert "[EMAIL]" in response["text"] and "[PHONE]" in response["text"]

        def usage(expected_attempts: int) -> dict[str, Any]:
            report = api("/operator/usage?" + urllib.parse.urlencode({"client_id": user_id}))
            assert report["scope"] == "persistent" and report["reset_on_restart"] is False
            assert report["clients"][user_id]["provider_attempts"] == expected_attempts
            assert all(row["client_id"] == user_id for row in report["rows"])
            return report

        def no_secret_projection() -> None:
            state = api("/operator/state")
            report = api("/operator/usage")
            projection = json.dumps([state, report])
            assert "SYNTHETIC_ADMIN_SMOKE_MESSAGE" not in projection
            for secret in [operator, password, provider, *issued_tokens]:
                assert secret not in projection, "Credential leaked into operator state or usage"

        try:
            print("Checking isolated PostgreSQL admin startup...", flush=True)
            compose(
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
                "--no-build",
                "gateway",
                "postgres",
                "smoke-upstream",
            )
            binding = compose("port", "smoke-upstream", "8000")
            assert binding.startswith("127.0.0.1:"), "Admin smoke must bind only to loopback"
            origin = "http://" + binding
            _ready(origin)
            status, _ = _request(origin, "/operator/console")
            assert status == 200
            api("/operator/state", credential=None, expected=401)
            state = api("/operator/state")
            assert state["configuration"]["management_enabled"] is True and state["clients"] == []
            policy = {
                "enabled": True,
                "models": ["fake"],
                "limits": {"max_concurrent_requests": 2, "requests_per_minute": 100},
                "additional_middleware": ["phone"],
            }
            api("/operator/clients", expected=422, method="POST", body={"id": user_id, **policy})
            created = api(
                "/operator/clients",
                expected=201,
                method="POST",
                body={"id": user_id, **policy},
                write=True,
            )
            token = created["token"]
            issued_tokens.append(token)
            assert created["client"]["credential_active"] is True
            assert created["client"]["effective_middleware"] == ["email", "phone"]
            api("/operator/state", credential=token, expected=401)
            # Verify administration writes reached the actual PostgreSQL service.
            count = compose(
                "exec",
                "--no-TTY",
                "postgres",
                "psql",
                "--username",
                "gateway7",
                "--dbname",
                "gateway7",
                "--tuples-only",
                "--no-align",
                "--command",
                f"SELECT count(*) FROM gateway7_admin.clients WHERE id='{user_id}'",
            )
            assert count == "1", "Created user was not persisted in PostgreSQL"
            chat(token)
            chat(token, model="alternate", expected=403)
            policy["models"] = ["alternate"]
            api("/operator/clients/" + user_id, method="PUT", body=policy, write=True)
            chat(token, expected=403)
            chat(token, model="alternate")
            policy.update(models=["fake"], enabled=False)
            api("/operator/clients/" + user_id, method="PUT", body=policy, write=True)
            chat(token, expected=401)
            policy["enabled"] = True
            api("/operator/clients/" + user_id, method="PUT", body=policy, write=True)
            rotated = api("/operator/clients/" + user_id + "/token", method="POST", write=True)[
                "token"
            ]
            issued_tokens.append(rotated)
            chat(token, expected=401)
            chat(rotated)
            api(
                "/operator/clients/" + user_id + "/token", expected=204, method="DELETE", write=True
            )
            chat(rotated, expected=401)
            reissued = api("/operator/clients/" + user_id + "/token", method="POST", write=True)[
                "token"
            ]
            issued_tokens.append(reissued)
            chat(reissued)
            usage(4)
            no_secret_projection()
            print(
                "Checking PostgreSQL user/token/policy/usage persistence across restarts...",
                flush=True,
            )
            compose("restart", "gateway")
            _ready(origin)
            assert api("/operator/state")["clients"][0]["limits"] == policy["limits"]
            usage(4)
            chat(reissued)
            compose("stop", "gateway")
            compose("restart", "postgres")
            compose("up", "--detach", "--wait", "--wait-timeout", "120", "--no-build", "gateway")
            _ready(origin)
            report = usage(5)
            assert report["clients"][user_id]["known_input_tokens"] == 60
            assert report["clients"][user_id]["known_output_tokens"] == 20
            days = sorted(row["day"] for row in report["rows"])
            filters = urllib.parse.urlencode(
                {
                    "client_id": user_id,
                    "model": "fake",
                    "start": days[0] + "T00:00:00Z",
                    "end": (
                        datetime.fromisoformat(days[-1]).replace(tzinfo=timezone.utc)
                        + timedelta(days=1)
                    ).isoformat(),
                }
            )
            filtered = api("/operator/usage?" + filters)
            assert filtered["clients"][user_id]["provider_attempts"] == 4
            status, export = _request(origin, "/operator/usage/export?" + filters, token=operator)
            assert status == 200
            rows = list(csv.DictReader(io.StringIO(export.decode())))
            assert rows and all(
                row["client_id"] == user_id and row["model"] == "fake" for row in rows
            )
            assert len(rows) == 4 and all(row["status"] == "complete" for row in rows)
            for secret in [
                operator,
                password,
                provider,
                *issued_tokens,
                "SYNTHETIC_ADMIN_SMOKE_MESSAGE",
            ]:
                assert secret.encode() not in export, (
                    "Credential or content leaked into usage export"
                )
            api("/operator/clients/" + user_id, expected=204, method="DELETE", write=True)
            chat(reissued, expected=401)
            assert api("/operator/state")["clients"] == []
            usage(5)
            api(
                "/operator/clients",
                expected=422,
                method="POST",
                body={"id": user_id, **policy},
                write=True,
            )
            no_secret_projection()
            print(
                "PostgreSQL admin HTTP lifecycle, live enforcement, credential controls, restarts, historical usage and export passed",
                flush=True,
            )
        finally:
            compose("down", "--volumes", "--remove-orphans", timeout=120)


if __name__ == "__main__":
    check_postgres_admin()

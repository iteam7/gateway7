"""Render the real Compose merge without a daemon or provider credentials."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def compose_environment(tmp_path):
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is not installed")
    docker_config = tmp_path / "docker-config"
    docker_config.mkdir()
    # Do not inherit operator keys, proxy values, Docker configuration or .env.
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "DOCKER_CONFIG": str(docker_config),
        "COMPOSE_ANSI": "never",
        "COMPOSE_PROJECT_NAME": "gateway7-live-config-test",
        "GATEWAY_CONFIG_FILE": str(ROOT / "config" / "openai.yaml"),
        "GATEWAY_KEY_ENV": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "gateway7-synthetic-provider-key",
        "GATEWAY7_CLIENT_TOKEN": "gateway7-synthetic-client-token",
    }
    version = subprocess.run(
        [docker, "compose", "version"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if version.returncode != 0:
        pytest.skip("Docker Compose plugin is not installed")
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = [
        docker,
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.live.yaml"),
        "config",
        "--format",
        "json",
    ]
    return command, environment


@pytest.mark.parametrize(
    ("proxy_variable", "proxy_url"),
    [
        (None, None),
        (None, "http://127.0.0.1:18080"),
        ("COMPANY_PROXY_URL", "https://127.0.0.1:18443"),
    ],
)
def test_live_compose_selects_openai_and_forwards_only_selected_proxy(
    compose_environment, tmp_path, proxy_variable, proxy_url
):
    command, environment = compose_environment
    if proxy_variable is not None:
        environment["GATEWAY_PROXY_ENV"] = proxy_variable
    selected_proxy = proxy_variable or "GATEWAY7_PROXY_URL"
    if proxy_url is not None:
        environment[selected_proxy] = proxy_url
    result = subprocess.run(
        command,
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, "Docker Compose could not render the live configuration"
    gateway = json.loads(result.stdout)["services"]["gateway"]
    assert gateway["command"] == [
        "serve",
        "--config",
        "/etc/gateway7/gateway.yaml",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    assert gateway["environment"]["OPENAI_API_KEY"] == environment["OPENAI_API_KEY"]
    assert gateway["environment"]["GATEWAY7_CLIENT_TOKEN"] == environment["GATEWAY7_CLIENT_TOKEN"]
    assert gateway["environment"].get("ANTHROPIC_API_KEY") is None
    assert gateway["environment"].get(selected_proxy) == proxy_url
    if proxy_variable is not None:
        assert gateway["environment"].get("GATEWAY7_PROXY_URL") is None
    configuration = next(
        volume for volume in gateway["volumes"] if volume["target"] == "/etc/gateway7/gateway.yaml"
    )
    assert configuration["source"] == str(ROOT / "config" / "openai.yaml")
    assert configuration["read_only"] is True

"""Render real Compose files and isolated synthetic dotenv input without a daemon."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def compose_cli(tmp_path):
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
    return docker, environment


@pytest.fixture
def compose_environment(compose_cli, tmp_path):
    docker, environment = compose_cli
    environment.update(
        {
            "GATEWAY_CONFIG_FILE": str(ROOT / "config" / "openai.yaml"),
            "GATEWAY_KEY_ENV": "OPENAI_API_KEY",
            "OPENAI_API_KEY": "gateway7-synthetic-provider-key",
            "GATEWAY7_CLIENT_TOKEN": "gateway7-synthetic-client-token",
        }
    )
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


@pytest.fixture
def dotenv_project(compose_cli, tmp_path):
    docker, environment = compose_cli
    project = tmp_path / "project"
    project.mkdir()
    for filename in ("compose.yaml", "compose.live.yaml"):
        shutil.copyfile(ROOT / filename, project / filename)
    shutil.copytree(ROOT / "config", project / "config")
    # Fill only the two required values in the real example. This is not an
    # operator's .env, and every value is a deliberately synthetic fixture.
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    example = example.replace(
        "OPENAI_API_KEY=\n", "OPENAI_API_KEY=gateway7-synthetic-dotenv-provider-key\n"
    ).replace(
        "GATEWAY7_CLIENT_TOKEN=\n", "GATEWAY7_CLIENT_TOKEN=gateway7-synthetic-dotenv-client-token\n"
    )
    example += "\nUNRELATED_PRIVATE_VALUE=synthetic-not-forwarded\n"
    example += "ANTHROPIC_API_KEY=synthetic-unselected-claude-key\n"
    example += "GEMINI_API_KEY=synthetic-unselected-gemini-key\n"
    (project / ".env").write_text(example, encoding="utf-8")
    return docker, environment, project


def render_compose(command, environment, project):
    result = subprocess.run(
        command,
        env=environment,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, "Docker Compose could not render the test configuration"
    return json.loads(result.stdout)["services"]["gateway"]


def mounted_configuration(gateway):
    return next(
        volume for volume in gateway["volumes"] if volume["target"] == "/etc/gateway7/gateway.yaml"
    )


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
    gateway = render_compose(command, environment, tmp_path)
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
    configuration = mounted_configuration(gateway)
    assert configuration["source"] == str(ROOT / "config" / "openai.yaml")
    assert configuration["read_only"] is True


def test_plain_compose_loads_example_dotenv_and_selects_live_openai(dotenv_project):
    docker, environment, project = dotenv_project
    gateway = render_compose(
        [docker, "compose", "config", "--format", "json"], environment, project
    )

    assert gateway["command"][0] == "serve"
    assert gateway["environment"] == {
        "OPENAI_API_KEY": "gateway7-synthetic-dotenv-provider-key",
        "GATEWAY7_CLIENT_TOKEN": "gateway7-synthetic-dotenv-client-token",
        "GATEWAY7_PROXY_URL": "",
    }
    configuration = mounted_configuration(gateway)
    assert configuration["source"] == str(project / "config" / "openai.yaml")
    assert configuration["read_only"] is True
    assert all(Path(volume["source"]).name != ".env" for volume in gateway["volumes"])


def test_unfilled_dotenv_stays_live_instead_of_falling_back_to_demo(dotenv_project):
    docker, environment, project = dotenv_project
    shutil.copyfile(ROOT / ".env.example", project / ".env")
    gateway = render_compose(
        [docker, "compose", "config", "--format", "json"], environment, project
    )

    assert gateway["command"][0] == "serve"
    assert gateway["environment"]["OPENAI_API_KEY"] == ""
    assert gateway["environment"]["GATEWAY7_CLIENT_TOKEN"] == ""
    assert mounted_configuration(gateway)["source"] == str(project / "config" / "openai.yaml")


def test_quoted_dotenv_literals_are_preserved_and_config_output_escapes_dollars(dotenv_project):
    docker, environment, project = dotenv_project
    env_file = project / ".env"
    env_file.write_text(
        env_file.read_text(encoding="utf-8")
        .replace(
            "OPENAI_API_KEY=gateway7-synthetic-dotenv-provider-key",
            "OPENAI_API_KEY='synthetic-provider-$literal#key'",
        )
        .replace(
            "GATEWAY7_CLIENT_TOKEN=gateway7-synthetic-dotenv-client-token",
            "GATEWAY7_CLIENT_TOKEN='synthetic-client-$literal#token'",
        ),
        encoding="utf-8",
    )
    resolved = subprocess.run(
        [docker, "compose", "config", "--environment"],
        env=environment,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resolved.returncode == 0, "Docker Compose could not resolve the test environment"
    fixture_values = {}
    for line in resolved.stdout.splitlines():
        key, _, value = line.partition("=")
        if key in {"OPENAI_API_KEY", "GATEWAY7_CLIENT_TOKEN"}:
            fixture_values[key] = value
    assert fixture_values.get("OPENAI_API_KEY") == "synthetic-provider-$literal#key"
    assert fixture_values.get("GATEWAY7_CLIENT_TOKEN") == "synthetic-client-$literal#token"

    gateway = render_compose(
        [docker, "compose", "config", "--format", "json"], environment, project
    )

    # Config serialization escapes $ to $$ for reuse as Compose input:
    # https://github.com/docker/compose/blob/v2.39.4/cmd/compose/config.go#L184
    assert gateway["environment"]["OPENAI_API_KEY"] == "synthetic-provider-$$literal#key"
    assert gateway["environment"]["GATEWAY7_CLIENT_TOKEN"] == "synthetic-client-$$literal#token"


@pytest.mark.parametrize(
    ("provider", "key_variable"),
    [("openai", "OPENAI_API_KEY"), ("claude", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY")],
)
def test_process_variables_override_dotenv_and_can_select_another_provider(
    dotenv_project, provider, key_variable
):
    docker, environment, project = dotenv_project
    environment.update(
        {
            "GATEWAY_CONFIG_FILE": f"./config/{provider}.yaml",
            "GATEWAY_KEY_ENV": key_variable,
            key_variable: "synthetic-process-provider-key",
            "GATEWAY7_CLIENT_TOKEN": "synthetic-process-client-token",
        }
    )
    gateway = render_compose(
        [docker, "compose", "config", "--format", "json"], environment, project
    )

    assert gateway["command"][0] == "serve"
    assert gateway["environment"] == {
        key_variable: "synthetic-process-provider-key",
        "GATEWAY7_CLIENT_TOKEN": "synthetic-process-client-token",
        "GATEWAY7_PROXY_URL": "",
    }
    assert mounted_configuration(gateway)["source"] == str(project / "config" / f"{provider}.yaml")


def test_explicit_base_file_keeps_demo_even_with_live_dotenv(dotenv_project):
    docker, environment, project = dotenv_project
    gateway = render_compose(
        [docker, "compose", "-f", "compose.yaml", "config", "--format", "json"],
        environment,
        project,
    )

    assert gateway["command"] == ["demo", "--host", "0.0.0.0", "--port", "8000"]
    assert not gateway.get("environment")
    assert not gateway.get("volumes")


def test_plain_compose_without_dotenv_keeps_original_demo(dotenv_project):
    docker, environment, project = dotenv_project
    (project / ".env").unlink()
    gateway = render_compose(
        [docker, "compose", "config", "--format", "json"], environment, project
    )

    assert gateway["command"] == ["demo", "--host", "0.0.0.0", "--port", "8000"]
    assert not gateway.get("environment")

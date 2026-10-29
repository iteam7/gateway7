"""CLI validation and offline fixtures do not initialize provider transports."""

import json
import logging
import os
import socket
import sys
from types import ModuleType

import httpx
from pydantic import BaseModel, ConfigDict
import pytest
import yaml

from gateway7.cli import main
from gateway7.scaffold import create_plugin_project
from gateway7.transport_api import TransportDescriptor


PROXY_ENV = "GATEWAY7_CLI_PROXY_SECRET"
PROXY_SECRET = "http://synthetic-user:synthetic-proxy-password@proxy.invalid:3128"
BUILTIN = "gateway7.transports.http_proxy"
PROVIDER_KEY = "gateway7-synthetic-cli-provider-key"
CLIENT_TOKEN = "gateway7-synthetic-cli-client-token"


@pytest.fixture(autouse=True)
def restore_gateway_logger():
    logger = logging.getLogger("gateway7")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers, logger.level, logger.propagate = handlers, level, propagate


def config_with_transport(transport):
    return {
        "provider": {
            "kind": "openai",
            "model": "gpt-4.1-mini",
            "key_env": "GATEWAY7_CLI_MISSING_PROVIDER_KEY",
            "transport": transport,
        },
        "auth": {
            "enabled": True,
            "clients": {
                "demo": {
                    "token_env": "GATEWAY7_CLI_MISSING_CLIENT_TOKEN",
                    "models": ["gpt-4.1-mini"],
                }
            },
        },
    }


def write_config(tmp_path, transport):
    path = tmp_path / "gateway.yaml"
    path.write_text(yaml.safe_dump(config_with_transport(transport)), encoding="utf-8")
    return path


@pytest.mark.parametrize("proxy_value", [None, "not a proxy URL", PROXY_SECRET])
def test_validate_builtin_transport_reads_no_proxy_value_and_creates_no_client(
    proxy_value, tmp_path, monkeypatch, capsys
):
    path = write_config(tmp_path, {"module": BUILTIN, "settings": {"url_env": PROXY_ENV}})
    if proxy_value is None:
        monkeypatch.delenv(PROXY_ENV, raising=False)
    else:
        monkeypatch.setenv(PROXY_ENV, proxy_value)
    monkeypatch.delenv("GATEWAY7_CLI_MISSING_PROVIDER_KEY", raising=False)
    monkeypatch.delenv("GATEWAY7_CLI_MISSING_CLIENT_TOKEN", raising=False)
    original_getitem = type(os.environ).__getitem__

    def guarded_getitem(environment, key):
        if key == PROXY_ENV:
            raise AssertionError("Validation read the proxy environment")
        return original_getitem(environment, key)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Validation initialized HTTP or attempted networking")

    monkeypatch.setattr(type(os.environ), "__getitem__", guarded_getitem)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    assert main(["validate", "--config", str(path)]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == "Configuration valid: provider=openai; middleware=0"
    assert output.err == ""
    assert PROXY_SECRET not in output.out


def test_validate_custom_descriptor_does_not_call_its_factory(tmp_path, monkeypatch, capsys):
    calls = []

    class Settings(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    def create(settings: Settings) -> httpx.AsyncBaseTransport:
        calls.append(settings)
        raise AssertionError("Validation called the transport factory")

    module = ModuleType("synthetic_cli_transport")
    module.TRANSPORT = TransportDescriptor(
        id="cli_probe", api_version=1, settings_model=Settings, create=create
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    path = write_config(tmp_path, {"module": module.__name__})
    assert main(["validate", "--config", str(path)]) == 0
    assert calls == []
    assert "Configuration valid: provider=openai" in capsys.readouterr().out


@pytest.mark.parametrize(
    "transport",
    [
        PROXY_SECRET,
        {"module": PROXY_SECRET},
        {"module": BUILTIN, "url": PROXY_SECRET},
        {"module": BUILTIN, "settings": {"url": PROXY_SECRET}},
        {"module": BUILTIN, "settings": {"url_env": PROXY_SECRET}},
    ],
)
def test_validate_rejects_inline_proxy_values_without_echoing_them(transport, tmp_path, capsys):
    path = write_config(tmp_path, transport)
    assert main(["validate", "--config", str(path)]) == 1
    output = capsys.readouterr()
    assert "Gateway startup failed:" in output.err
    assert "synthetic-user" not in output.out + output.err
    assert "synthetic-proxy-password" not in output.out + output.err
    assert "Traceback" not in output.out + output.err


@pytest.fixture
def startup_credentials_and_server_guard(monkeypatch):
    monkeypatch.setenv("GATEWAY7_CLI_MISSING_PROVIDER_KEY", PROVIDER_KEY)
    monkeypatch.setenv("GATEWAY7_CLI_MISSING_CLIENT_TOKEN", CLIENT_TOKEN)
    server_calls = []

    async def forbidden(*_args, **_kwargs):
        server_calls.append(True)
        raise AssertionError("Invalid transport reached the HTTP server")

    monkeypatch.setattr("gateway7.cli._ManagedServer.serve", forbidden)
    return server_calls


def assert_safe_startup_output(capsys):
    output = capsys.readouterr()
    text = output.out + output.err
    assert "Gateway startup failed:" in output.err
    for forbidden in (
        "synthetic-user",
        "synthetic-proxy-password",
        "synthetic-query-secret",
        PROVIDER_KEY,
        CLIENT_TOKEN,
        "Traceback",
        "factory-crash",
    ):
        assert forbidden not in text


def test_serve_rejects_bad_proxy_environment_without_secret_or_traceback(
    tmp_path, monkeypatch, capsys, startup_credentials_and_server_guard
):
    path = write_config(tmp_path, {"module": BUILTIN, "settings": {"url_env": PROXY_ENV}})
    monkeypatch.setenv(PROXY_ENV, PROXY_SECRET + "/?private=synthetic-query-secret")
    assert main(["serve", "--config", str(path)]) == 1
    assert startup_credentials_and_server_guard == []
    assert_safe_startup_output(capsys)


def test_serve_sanitizes_transport_factory_exception(
    tmp_path, monkeypatch, capsys, startup_credentials_and_server_guard
):
    calls = []

    class Settings(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    def create(settings: Settings) -> httpx.AsyncBaseTransport:
        calls.append(settings)
        raise RuntimeError("factory-crash " + PROXY_SECRET + "/?private=synthetic-query-secret")

    module = ModuleType("synthetic_failing_transport")
    module.TRANSPORT = TransportDescriptor(
        id="cli_failure", api_version=1, settings_model=Settings, create=create
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    path = write_config(tmp_path, {"module": module.__name__})
    assert main(["serve", "--config", str(path)]) == 1
    assert len(calls) == 1
    assert startup_credentials_and_server_guard == []
    assert_safe_startup_output(capsys)


def test_offline_transport_is_not_imported_secrets_are_removed_and_socket_guard_remains(
    tmp_path, monkeypatch, capsys
):
    project = create_plugin_project("sample", tmp_path)
    marker = project / "transport-imported"
    (project / "forbidden_transport.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n"
        "raise AssertionError('Offline execution imported a transport')\n",
        encoding="utf-8",
    )
    source = yaml.safe_load((project / "gateway.yaml").read_text())
    source.update(
        config_with_transport({"module": "forbidden_transport", "settings": {"url_env": PROXY_ENV}})
    )
    (project / "gateway.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
    guarded_variables = (
        PROXY_ENV,
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    )
    for variable in guarded_variables:
        monkeypatch.setenv(variable, PROXY_SECRET)
    module = project / "gateway7_plugin_sample" / "plugin.py"
    module.write_text(
        "import os, socket\n"
        f"assert all(name not in os.environ for name in {guarded_variables!r})\n"
        "with socket.socket() as probe:\n"
        "    try:\n"
        "        probe.connect(('127.0.0.1', 9))\n"
        "    except PermissionError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('Offline network guard was bypassed')\n" + module.read_text(),
        encoding="utf-8",
    )
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
    assert report["passed"] is True and report["total"] == 2
    assert not marker.exists()
    assert PROXY_SECRET not in output.out + output.err


def test_offline_rejects_malformed_transport_shape_without_echoing_values(tmp_path, capsys):
    project = create_plugin_project("sample", tmp_path)
    source = yaml.safe_load((project / "gateway.yaml").read_text())
    source["provider"]["transport"] = {"module": BUILTIN, "url": PROXY_SECRET}
    (project / "gateway.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
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
        == 2
    )
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["passed"] is False and "error" in report
    assert PROXY_SECRET not in output.out + output.err
    assert "synthetic-proxy-password" not in output.out + output.err

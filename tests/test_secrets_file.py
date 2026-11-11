"""Explicit synthetic secret files affect credential startup, never serving."""

import asyncio
from contextlib import asynccontextmanager
import importlib
import json
import logging
import os
from types import SimpleNamespace

import anyio
from fastapi import FastAPI
import pytest

from gateway7 import cli
from gateway7.config import GatewayConfig
from gateway7.errors import StartupError

KEY = "GATEWAY7_SYNTHETIC_FILE_KEY"
TOKEN = "GATEWAY7_SYNTHETIC_FILE_TOKEN"
PROXY = "GATEWAY7_SYNTHETIC_FILE_PROXY"
VALUES = {
    KEY: "synthetic-file-provider-key",
    TOKEN: "synthetic-file-client-token",
    PROXY: "http://synthetic-user:synthetic-password@proxy.invalid:3128",
}
BUILTIN = "gateway7.transports.http_proxy"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in VALUES:
        monkeypatch.delenv(name, raising=False)
    logger = logging.getLogger("gateway7")
    previous = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers, logger.level, logger.propagate = previous


@pytest.fixture
def config():
    return GatewayConfig.model_validate(
        {
            "provider": {
                "key_env": KEY,
                "transport": {"module": BUILTIN, "settings": {"url_env": PROXY}},
            },
            "auth": {
                "enabled": True,
                "clients": {"synthetic": {"token_env": TOKEN, "models": ["fake"]}},
            },
        }
    )


def secret_file(tmp_path, content=None):
    path = tmp_path / "synthetic-private.json"
    path.write_bytes(json.dumps(VALUES).encode() if content is None else content)
    path.chmod(0o600)
    return path


def fake_app(monkeypatch, lifespan):
    app = SimpleNamespace(router=SimpleNamespace(lifespan_context=lifespan))
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: app)
    return app


def fake_server(monkeypatch, serve):
    class Server:
        def __init__(self, config):
            assert config.lifespan == "off"

        async def serve(self):
            await serve()

    monkeypatch.setattr(cli, "_ManagedServer", Server)


async def test_actual_startup_resolves_credentials_once_before_environment_restoration(
    monkeypatch, tmp_path, config
):
    module = importlib.import_module("gateway7.app")
    path = secret_file(tmp_path)
    events = []

    class Provider:
        async def aclose(self):
            assert all(name not in os.environ for name in VALUES)
            events.append("close")

    def build_provider(specification, key, **kwargs):
        assert specification is config.provider and key == VALUES[KEY]
        assert dict((name, os.environ[name]) for name in VALUES) == VALUES
        events.append("credentials")
        return Provider()

    def create_transport(_validated):
        assert os.environ[PROXY] == VALUES[PROXY]
        events.append("transport")
        return None

    monkeypatch.setattr(module, "build_provider", build_provider)
    monkeypatch.setattr(module, "create_transport", create_transport)

    async def serve():
        assert all(name not in os.environ for name in VALUES)
        events.append("serve")

    fake_server(monkeypatch, serve)
    await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert events == ["transport", "credentials", "serve", "close"]
    assert all(name not in os.environ for name in VALUES)


@pytest.mark.parametrize("use_file", [False, True])
async def test_anyio_task_group_lifespan_enters_and_exits_in_same_task(
    monkeypatch, tmp_path, config, use_file
):
    path = secret_file(tmp_path)
    tasks = []
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        async with anyio.create_task_group():
            tasks.append(asyncio.current_task())
            assert os.environ.get(KEY) == (VALUES[KEY] if use_file else None)
            events.append("startup")
            yield
            tasks.append(asyncio.current_task())
        events.append("shutdown")

    app = FastAPI(lifespan=lifespan)
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: app)

    async def serve():
        assert all(name not in os.environ for name in VALUES)
        events.append("serve")

    fake_server(monkeypatch, serve)
    previous_tasks = asyncio.all_tasks()
    await cli._serve(
        None,
        "127.0.0.1",
        8000,
        config=config,
        secrets_file=str(path) if use_file else None,
    )
    assert events == ["startup", "serve", "shutdown"]
    assert len(tasks) == 2 and tasks[0] is tasks[1]
    assert asyncio.all_tasks() == previous_tasks


@pytest.mark.parametrize("existing", ["", "synthetic-existing-value"])
async def test_environment_wins_including_empty_values(monkeypatch, tmp_path, config, existing):
    monkeypatch.setenv(KEY, existing)
    path = secret_file(tmp_path)
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        assert os.environ[KEY] == existing
        assert os.environ[TOKEN] == VALUES[TOKEN]
        events.append("startup")
        yield
        events.append("shutdown")

    fake_app(monkeypatch, lifespan)

    async def serve():
        assert os.environ[KEY] == existing
        assert TOKEN not in os.environ and PROXY not in os.environ
        events.append("serve")

    fake_server(monkeypatch, serve)
    await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert os.environ[KEY] == existing
    assert events == ["startup", "serve", "shutdown"]


@pytest.mark.parametrize("failure", ["startup", "serve", "cancel_startup", "cancel_serve"])
async def test_environment_restored_after_failures_and_cancellation(
    monkeypatch, tmp_path, config, failure
):
    path = secret_file(tmp_path)
    events = []
    error = asyncio.CancelledError if failure.startswith("cancel") else RuntimeError
    serving = []

    @asynccontextmanager
    async def lifespan(_app):
        assert os.environ[KEY] == VALUES[KEY]
        try:
            if failure.endswith("startup"):
                raise error("synthetic failure")
            yield
        finally:
            events.append("shutdown")

    fake_app(monkeypatch, lifespan)

    async def serve():
        serving.append(True)
        assert all(name not in os.environ for name in VALUES)
        raise error("synthetic failure")

    fake_server(monkeypatch, serve)
    with pytest.raises(error):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert all(name not in os.environ for name in VALUES)
    assert events == ["shutdown"]
    assert serving == ([] if failure.endswith("startup") else [True])


@pytest.mark.parametrize("existing", ["", "synthetic-existing-proxy-value"])
async def test_cancelled_startup_restores_environment_before_resistant_cleanup_finishes(
    monkeypatch, tmp_path, config, existing
):
    path = secret_file(tmp_path)
    monkeypatch.setenv(PROXY, existing)
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()
    startup_tasks = []
    cleanup_environment = []
    cancellations = []
    serving = []
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        startup_tasks.append(asyncio.current_task())
        assert os.environ[KEY] == VALUES[KEY] and os.environ[TOKEN] == VALUES[TOKEN]
        assert os.environ[PROXY] == existing
        events.append("startup")
        started.set()
        try:
            await asyncio.Event().wait()
            yield
        finally:
            cleanup_environment.append({name: os.environ.get(name) for name in VALUES})
            cleanup_started.set()
            while not release_cleanup.is_set():
                try:
                    await release_cleanup.wait()
                except asyncio.CancelledError:
                    pass
            events.append("cleanup")
            cleanup_finished.set()

    app = FastAPI(lifespan=lifespan)
    monkeypatch.setattr(cli, "create_app", lambda *args, **kwargs: app)

    async def serve():
        serving.append(True)

    fake_server(monkeypatch, serve)

    async def run():
        try:
            await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
        except asyncio.CancelledError as error:
            cancellations.append(error)
            raise

    previous_tasks = asyncio.all_tasks()
    task = asyncio.create_task(run())
    first_cancellation = object()
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel(first_cancellation)
        await asyncio.wait_for(cleanup_started.wait(), timeout=1)
        task.cancel("second cancellation")
        await asyncio.sleep(0)
        assert KEY not in os.environ and TOKEN not in os.environ
        assert os.environ[PROXY] == existing
        assert cleanup_environment == [{KEY: None, TOKEN: None, PROXY: existing}]
        assert not task.done() and not cleanup_finished.is_set()
        assert serving == []
    finally:
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError) as error:
            await task
        assert error.value is cancellations[0]
        assert error.value.args == (first_cancellation,)
        assert cleanup_finished.is_set() and events == ["startup", "cleanup"]
        assert len(startup_tasks) == 1 and startup_tasks[0].done()
        assert asyncio.all_tasks() == previous_tasks
        assert KEY not in os.environ and TOKEN not in os.environ
        assert os.environ[PROXY] == existing and serving == []


@pytest.mark.parametrize(
    "content",
    [
        b'{"synthetic-private-key-name": "synthetic-private-value"}',
        b"[]",
        b"null",
        b"{invalid-json",
        b"\xff",
        ('{"%s":"first","%s":"second"}' % (KEY, KEY)).encode(),
        json.dumps({KEY: {"nested": "synthetic-private-value"}}).encode(),
        json.dumps({KEY: ["synthetic-private-value"]}).encode(),
        json.dumps({KEY: 123}).encode(),
        json.dumps({KEY: True}).encode(),
        json.dumps({KEY: None}).encode(),
        json.dumps({KEY: ""}).encode(),
        json.dumps({KEY: "synthetic\u0000value"}).encode(),
        json.dumps({KEY: "synthetic\ud800value"}).encode(),
        json.dumps({TOKEN: "short"}).encode(),
        json.dumps({PROXY: "invalid-proxy"}).encode(),
        ('{"%s": NaN}' % KEY).encode(),
        ('{"%s": Infinity}' % KEY).encode(),
        b"[" * 1100 + b"]" * 1100,
        b" " * 65537,
    ],
)
async def test_complete_file_validation_precedes_any_environment_change_even_when_shadowed(
    monkeypatch, tmp_path, config, content, capsys
):
    path = secret_file(tmp_path, content)
    for name in VALUES:
        monkeypatch.setenv(name, "synthetic-existing-value")
    original = type(os.environ).__setitem__

    def forbidden_write(environment, name, value):
        if name in VALUES:
            pytest.fail("Invalid file changed the environment")
        return original(environment, name, value)

    with monkeypatch.context() as guard:
        guard.setattr(type(os.environ), "__setitem__", forbidden_write)
        with pytest.raises(StartupError) as error:
            await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert str(error.value) == "Invalid secrets file"
    assert all(os.environ[name] == "synthetic-existing-value" for name in VALUES)
    assert capsys.readouterr() == ("", "")


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode checks")
@pytest.mark.parametrize("kind", ["missing", "mode", "symlink", "fifo", "directory", "owner"])
async def test_unsafe_files_are_rejected_before_opening_or_starting(
    monkeypatch, tmp_path, config, kind
):
    path = secret_file(tmp_path)
    if kind == "missing":
        path = tmp_path / "missing-synthetic-private.json"
    elif kind == "mode":
        path.chmod(0o640)
    elif kind == "symlink":
        link = tmp_path / "synthetic-link"
        link.symlink_to(path)
        path = link
    elif kind == "fifo":
        path = tmp_path / "synthetic-fifo"
        os.mkfifo(path, mode=0o600)
    elif kind == "directory":
        path = tmp_path
    elif kind == "owner":
        monkeypatch.setattr(os, "geteuid", lambda: path.stat().st_uid + 1)

    def forbidden_open(*args, **kwargs):
        pytest.fail("Unsafe file reached open")

    monkeypatch.setattr(os, "open", forbidden_open)
    with pytest.raises(StartupError, match="^Cannot read private secrets file$"):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))


async def test_bounded_read_accepts_exact_limit(monkeypatch, tmp_path, config):
    content = json.dumps(VALUES).encode()
    path = secret_file(tmp_path, content + b" " * (65536 - len(content)))

    @asynccontextmanager
    async def lifespan(_app):
        assert os.environ[KEY] == VALUES[KEY]
        yield

    fake_app(monkeypatch, lifespan)

    async def serve():
        assert KEY not in os.environ

    fake_server(monkeypatch, serve)
    await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))


@pytest.mark.skipif(os.name != "posix", reason="POSIX nonblocking and symlink flags")
@pytest.mark.parametrize("replacement", ["regular", "symlink", "fifo"])
async def test_file_replacement_between_stat_and_open_is_rejected(
    monkeypatch, tmp_path, config, replacement
):
    path = secret_file(tmp_path)
    original_open = os.open

    def replace_then_open(filename, flags):
        assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
        other = tmp_path / "replacement"
        if replacement == "regular":
            other.write_text("{}", encoding="utf-8")
            other.chmod(0o600)
        elif replacement == "symlink":
            other.symlink_to(tmp_path / "nonexistent-synthetic-file")
        else:
            os.mkfifo(other, mode=0o600)
        other.replace(path)
        return original_open(filename, flags)

    monkeypatch.setattr(os, "open", replace_then_open)
    with pytest.raises(StartupError, match="^Cannot read private secrets file$"):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert all(name not in os.environ for name in VALUES)


async def test_growth_beyond_stat_size_still_uses_bounded_read(monkeypatch, tmp_path, config):
    path = secret_file(tmp_path, b" " * 65537)
    original_stat = os.fstat

    def stale_size(fd):
        metadata = original_stat(fd)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_uid=metadata.st_uid,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=0,
        )

    monkeypatch.setattr(os, "fstat", stale_size)
    with pytest.raises(StartupError, match="^Invalid secrets file$"):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))


async def test_partial_environment_installation_failure_restores_previous_state(
    monkeypatch, tmp_path, config
):
    path = secret_file(tmp_path)
    original = type(os.environ).__setitem__

    def fail_second_write(environment, name, value):
        if name == TOKEN:
            raise OSError("Synthetic environment failure")
        return original(environment, name, value)

    @asynccontextmanager
    async def forbidden_lifespan(_app):
        pytest.fail("Partial environment installation reached startup")
        yield

    fake_app(monkeypatch, forbidden_lifespan)
    monkeypatch.setattr(type(os.environ), "__setitem__", fail_second_write)
    with pytest.raises(OSError, match="Synthetic environment failure"):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert all(name not in os.environ for name in VALUES)


async def test_empty_existing_provider_environment_fails_without_file_fallback(
    monkeypatch, tmp_path, config
):
    monkeypatch.setenv(KEY, "")
    path = secret_file(tmp_path)
    with pytest.raises(StartupError, match="missing or empty"):
        await cli._serve(None, "127.0.0.1", 8000, config=config, secrets_file=str(path))
    assert os.environ[KEY] == ""
    assert TOKEN not in os.environ and PROXY not in os.environ


async def test_no_file_preserves_existing_lifecycle_without_secret_or_early_config_read(
    monkeypatch,
):
    events = []

    def forbidden(*args, **kwargs):
        pytest.fail("Environment-only serve read a secrets file or loaded config early")

    @asynccontextmanager
    async def lifespan(_app):
        events.append("startup")
        yield
        events.append("shutdown")

    fake_app(monkeypatch, lifespan)

    async def serve():
        events.append("serve")

    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(cli, "_read_secrets_file", forbidden)
    fake_server(monkeypatch, serve)
    await cli._serve("synthetic.yaml", "127.0.0.1", 8000)
    assert events == ["startup", "serve", "shutdown"]


@pytest.mark.parametrize("module", ["synthetic_custom_transport", None])
async def test_only_builtin_proxy_reference_is_eligible(monkeypatch, tmp_path, config, module):
    source = config.model_dump()
    source["provider"]["transport"] = (
        None if module is None else {"module": module, "settings": {"url_env": PROXY}}
    )
    custom = GatewayConfig.model_validate(source)
    path = secret_file(tmp_path, json.dumps({PROXY: VALUES[PROXY]}).encode())
    with pytest.raises(StartupError, match="^Invalid secrets file$"):
        await cli._serve(None, "127.0.0.1", 8000, config=custom, secrets_file=str(path))


async def test_configuration_loaded_once_and_passed_to_existing_app_seam(
    monkeypatch, tmp_path, config
):
    path = secret_file(tmp_path)
    loads = []

    def load(path):
        loads.append(path)
        return config

    @asynccontextmanager
    async def lifespan(_app):
        yield

    app = fake_app(monkeypatch, lifespan)

    def create(config_path, *, config):
        assert config_path == "synthetic.yaml"
        assert config is not None
        return app

    async def serve():
        pass

    monkeypatch.setattr(cli, "load_config", load)
    monkeypatch.setattr(cli, "create_app", create)
    fake_server(monkeypatch, serve)
    await cli._serve("synthetic.yaml", "127.0.0.1", 8000, secrets_file=str(path))
    assert loads == ["synthetic.yaml"]


def test_cli_errors_are_static_and_redacted(monkeypatch, tmp_path, config, capsys):
    path = secret_file(tmp_path, b'{"synthetic-private-key-name":"synthetic-private-value"}')
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    assert cli.main(["serve", "--config", "synthetic.yaml", "--secrets-file", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Gateway startup failed: Invalid secrets file\n"


@pytest.mark.parametrize("command", ["validate", "plugin_init", "plugin_test"])
def test_nonserving_commands_do_not_load_secret_file(
    monkeypatch, tmp_path, config, capsys, command
):
    monkeypatch.setattr(cli, "load_config", lambda _path: config)

    def forbidden(*args, **kwargs):
        pytest.fail("Validation read a secrets file")

    monkeypatch.setattr(cli, "_read_secrets_file", forbidden)
    if command == "validate":
        arguments = ["validate", "--config", "synthetic.yaml"]
    elif command == "plugin_init":
        monkeypatch.setattr(cli, "create_plugin_project", lambda *args: tmp_path / "synthetic")
        arguments = ["plugin", "init", "synthetic"]
    else:
        monkeypatch.setattr(cli, "run_offline", lambda *args: (0, {"passed": True}))
        arguments = [
            "plugin",
            "test",
            "--config",
            "synthetic.yaml",
            "--fixtures",
            "synthetic.json",
            "--json",
        ]
    assert cli.main(arguments) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("legacy", [False, True])
def test_serve_flag_preserves_config_environment_and_legacy_invocation(monkeypatch, legacy, capsys):
    monkeypatch.setenv("GATEWAY_CONFIG", "synthetic.yaml")
    seen = []

    async def serve(path, host, port, *, config=None, secrets_file=None):
        seen.append((path, host, port, config, secrets_file))

    monkeypatch.setattr(cli, "_serve", serve)
    arguments = ["--secrets-file", "synthetic-private.json"]
    assert cli.main(arguments if legacy else ["serve", *arguments]) == 0
    assert seen == [("synthetic.yaml", "127.0.0.1", 8000, None, "synthetic-private.json")]
    assert capsys.readouterr() == ("", "")

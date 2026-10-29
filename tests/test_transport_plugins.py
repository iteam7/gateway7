"""Transport seams use synthetic resources and never contact a real provider."""

import asyncio
import ssl
import sys
from dataclasses import replace
from types import ModuleType

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gateway7.app import create_app
from gateway7.config import GatewayConfig, ProviderConfig, TransportConfig, load_config
from gateway7.errors import StartupError
from gateway7.plugin_api import PluginDescriptor
from gateway7.providers import build_provider
from gateway7.transport_api import API_VERSION, TransportDescriptor
from gateway7.transport_loader import create_transport, validate_transport_config
from gateway7.transports import http_proxy

SECRET = "synthetic-proxy-password-143"
KEY = "synthetic-provider-key-143"


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    count: int = Field(default=1, ge=1)


class TrackingTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []
        self.closes = 0

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b'{"text":"synthetic answer"}'))

    async def aclose(self):
        self.closes += 1


def install_transport(monkeypatch, factory, *, descriptor=None):
    name = "test_gateway7_transport"
    module = ModuleType(name)
    module.TRANSPORT = descriptor or TransportDescriptor("test", API_VERSION, Settings, factory)
    monkeypatch.setitem(sys.modules, name, module)
    return TransportConfig(module=name)


def app_config(transport, **options):
    return GatewayConfig.model_validate(
        {"provider": {"key_env": "GATEWAY7_TEST_KEY", "transport": transport}, **options}
    )


def test_absent_transport_keeps_direct_path_without_import_or_factory(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("The direct default must not import a transport plugin")

    monkeypatch.setattr("gateway7.transport_loader.importlib.import_module", forbidden)
    assert ProviderConfig().transport is None
    assert validate_transport_config(None) is None
    assert create_transport(None) is None


def test_validation_is_separate_from_factory_and_uses_strict_frozen_settings(monkeypatch):
    calls = []
    resource = TrackingTransport()

    def factory(settings):
        calls.append(settings)
        return resource

    config = install_transport(monkeypatch, factory)
    validated = validate_transport_config(config)
    assert validated.settings.count == 1
    assert calls == []
    with pytest.raises(ValidationError):
        validated.settings.count = 2
    assert create_transport(validated) is resource
    assert calls == [validated.settings]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "unsafe/" + SECRET},
        {"api_version": True},
        {"api_version": 2},
        {"settings_model": object},
        {"settings_model": BaseModel},
        {"create": None},
        {"create": lambda: TrackingTransport()},
    ],
)
def test_invalid_descriptors_are_rejected_without_factory_or_details(monkeypatch, changes):
    descriptor = TransportDescriptor("test", 1, Settings, lambda _: pytest.fail("factory ran"))
    config = install_transport(monkeypatch, None, descriptor=replace(descriptor, **changes))
    with pytest.raises(StartupError) as error:
        validate_transport_config(config)
    assert SECRET not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize("settings", [{"count": "1"}, {"count": 0}, {"url": SECRET}])
def test_invalid_settings_fail_before_factory_without_values(monkeypatch, settings):
    config = install_transport(monkeypatch, lambda _: pytest.fail("factory ran"))
    config = config.model_copy(update={"settings": settings})
    with pytest.raises(StartupError, match="Invalid provider transport settings") as error:
        validate_transport_config(config)
    assert SECRET not in str(error.value)


def test_async_factory_is_rejected_and_returned_coroutine_is_closed(monkeypatch):
    async def factory(_):
        pytest.fail("async factory ran")

    config = install_transport(monkeypatch, factory)
    with pytest.raises(StartupError, match="descriptor"):
        validate_transport_config(config)

    coroutine = factory(Settings())
    config = install_transport(monkeypatch, lambda _: coroutine)
    with pytest.raises(StartupError, match="synchronous factory"):
        create_transport(validate_transport_config(config))
    assert coroutine.cr_frame is None


@pytest.mark.parametrize("failure", ["raise", "invalid_result"])
def test_factory_failure_is_sanitized(monkeypatch, failure):
    def factory(_):
        if failure == "raise":
            raise RuntimeError(SECRET)
        return {"url": SECRET}

    config = install_transport(monkeypatch, factory)
    with pytest.raises(StartupError) as error:
        create_transport(validate_transport_config(config))
    assert SECRET not in str(error.value)
    assert error.value.__cause__ is None


def test_transport_configuration_rejects_inline_proxy_url_safely(tmp_path):
    config = tmp_path / "invalid.yaml"
    config.write_text(
        "provider:\n  transport:\n    module: gateway7.transports.http_proxy\n"
        f"    url: http://user:{SECRET}@proxy.example\n",
        encoding="utf-8",
    )
    with pytest.raises(StartupError) as error:
        load_config(config)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "socks5://proxy.example:1080",
        "file:///proxy",
        "http://",
        "http://:80",
        "http://proxy.example:",
        "http://proxy.example:0",
        "http://proxy.example:65536",
        "http://proxy.example:word",
        "http://proxy.example/a",
        "http://proxy.example?",
        "http://proxy.example#",
        "http://proxy.example\n",
        "http://proxy\texample",
        "http://proxy.example\\escape",
        "http://user%0a:password@proxy.example",
        "http://user:pass%7f@proxy.example",
        "http://user:%oops@proxy.example",
        "http://user:pass@other@proxy.example",
        "http://:pass@proxy.example",
        "http://bad_host.example",
        "http://-proxy.example",
        "http://proxy..example",
        "http://proxy.example..",
        "http://999.1.1.1",
        "http://[invalid]:80",
        "http://[::1",
        "http://[::1%zone]:80",
        "http://" + "a" * 4096,
    ],
)
def test_invalid_proxy_url_is_rejected_before_transport_creation(monkeypatch, url):
    if url is None:
        monkeypatch.delenv("TEST_PROXY_URL", raising=False)
    else:
        monkeypatch.setenv("TEST_PROXY_URL", url)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: pytest.fail("transport created"))
    with pytest.raises(StartupError) as error:
        http_proxy.create(http_proxy.Settings(url_env="TEST_PROXY_URL"))
    assert str(error.value) == "HTTP proxy transport initialization failed"
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "url",
    [
        "http://proxy.example",
        "http://proxy.example:80/",
        "http://127.0.0.1:8080",
        "http://[::1]:8080",
        "https://proxy.example:8443",
        "https://user:" + SECRET + "@proxy.example:443",
    ],
)
async def test_proxy_factory_uses_only_explicit_url_and_verified_tls(monkeypatch, url):
    monkeypatch.setenv("TEST_PROXY_URL", url)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "synthetic-unusable-ambient-proxy")
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.setenv(name, "/synthetic/nonexistent/certificates")
    captured = []
    contexts = []
    inners = []
    real_context = httpx.create_ssl_context

    def context(**kwargs):
        contexts.append(kwargs)
        return real_context(**kwargs)

    def transport(**kwargs):
        captured.append(kwargs)
        inner = TrackingTransport()
        inners.append(inner)
        return inner

    monkeypatch.setattr(httpx, "create_ssl_context", context)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    resource = http_proxy.create(http_proxy.Settings(url_env="TEST_PROXY_URL"))
    assert isinstance(resource, httpx.AsyncBaseTransport)
    assert captured == []  # Startup resolves configuration, not request connection pools.
    for _ in range(2):
        response = await resource.handle_async_request(
            httpx.Request("POST", "https://api.openai.com")
        )
        await response.aclose()
    await resource.aclose()
    assert len(captured) == 2
    assert len(inners) == 2 and all(inner.closes == 1 for inner in inners)
    options = captured[0]
    assert isinstance(options["verify"], ssl.SSLContext)
    assert options["verify"].verify_mode == ssl.CERT_REQUIRED
    assert options["verify"].check_hostname
    assert options["verify"] is captured[1]["verify"]
    assert options["trust_env"] is False
    assert options["retries"] == 0
    proxy = options["proxy"]
    assert isinstance(proxy, httpx.Proxy)
    assert SECRET not in repr(proxy) and "user" not in repr(proxy)
    if url.startswith("https:"):
        assert contexts == [{"verify": True, "trust_env": False}] * 2
        assert proxy.ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert proxy.ssl_context.check_hostname
        assert proxy.ssl_context is not options["verify"]
    else:
        assert contexts == [{"verify": True, "trust_env": False}]
        assert proxy.ssl_context is None


@pytest.mark.parametrize("close_failure", [False, True])
async def test_stream_and_outer_close_race_retains_resource_through_repeated_cancellation(
    monkeypatch, close_failure
):
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    initial_tasks = set(asyncio.all_tasks())

    class SlowClose(TrackingTransport):
        async def aclose(self):
            self.closes += 1
            entered.set()
            await release.wait()
            finished.set()
            if close_failure:
                raise RuntimeError("synthetic close failure")

    inner = SlowClose()
    monkeypatch.setenv("TEST_PROXY_URL", "http://proxy.example")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: inner)
    outer = http_proxy.create(http_proxy.Settings(url_env="TEST_PROXY_URL"))
    response = await outer.handle_async_request(httpx.Request("POST", "https://api.openai.com"))
    stream_close = asyncio.create_task(response.aclose())
    await entered.wait()
    outer_close = asyncio.create_task(outer.aclose())
    for _ in range(2):
        stream_close.cancel("original close cancellation")
        await asyncio.sleep(0)
    assert not stream_close.done()
    assert not outer_close.done()
    assert inner.closes == 1 and not finished.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError, match="original close cancellation"):
        await stream_close
    if close_failure:
        for close in (outer_close, response.stream.aclose(), outer.aclose()):
            with pytest.raises(RuntimeError, match="synthetic close failure"):
                await close
    else:
        await outer_close
        await response.stream.aclose()
        await outer.aclose()
    assert inner.closes == 1 and finished.is_set()
    with pytest.raises(httpx.TransportError, match="transport is closed"):
        await outer.handle_async_request(httpx.Request("POST", "https://api.openai.com"))
    assert set(asyncio.all_tasks()) == initial_tasks


async def test_cancelled_failed_request_keeps_original_error_until_owned_cleanup_finishes(
    monkeypatch,
):
    entered = asyncio.Event()
    release = asyncio.Event()

    class FailingTransport(TrackingTransport):
        async def handle_async_request(self, request):
            raise httpx.ProxyError("synthetic original failure")

        async def aclose(self):
            self.closes += 1
            entered.set()
            await release.wait()

    inner = FailingTransport()
    monkeypatch.setenv("TEST_PROXY_URL", "http://proxy.example")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: inner)
    outer = http_proxy.create(http_proxy.Settings(url_env="TEST_PROXY_URL"))
    request = asyncio.create_task(
        outer.handle_async_request(httpx.Request("POST", "https://api.openai.com"))
    )
    await entered.wait()
    request.cancel()
    await asyncio.sleep(0)
    request.cancel()
    outer_close = asyncio.create_task(outer.aclose())
    await asyncio.sleep(0)
    assert not request.done() and not outer_close.done()
    release.set()
    with pytest.raises(httpx.ProxyError, match="synthetic original failure"):
        await request
    await outer_close
    assert inner.closes == 1


@pytest.mark.parametrize("fail_request", [False, True])
async def test_trace_composition_restores_extension_and_closes_stream_and_pool(
    monkeypatch, fail_request
):
    observed = []
    raw = TrackingTransport()  # Only its asynchronous close contract is needed here.

    async def original_trace(name, info):
        observed.append(name)

    class TracedTransport(TrackingTransport):
        async def handle_async_request(self, request):
            await request.extensions["trace"](
                "connection.connect_tcp.complete", {"return_value": raw}
            )
            if fail_request:
                raise httpx.ProxyError("synthetic proxy failure")
            return await super().handle_async_request(request)

    inner = TracedTransport()
    monkeypatch.setenv("TEST_PROXY_URL", "http://proxy.example")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: inner)
    outer = http_proxy.create(http_proxy.Settings(url_env="TEST_PROXY_URL"))
    request = httpx.Request(
        "POST", "https://api.openai.com", extensions={"trace": original_trace, "test": "retained"}
    )
    if fail_request:
        with pytest.raises(httpx.ProxyError, match="synthetic proxy failure"):
            await outer.handle_async_request(request)
    else:
        response = await outer.handle_async_request(request)
        await response.aclose()
    await outer.aclose()
    assert observed == ["connection.connect_tcp.complete"]
    assert request.extensions == {"trace": original_trace, "test": "retained"}
    assert inner.closes == raw.closes == 1


async def test_provider_passes_transport_and_keeps_core_client_policy(monkeypatch):
    real_client = httpx.AsyncClient
    calls = []

    def client(**kwargs):
        calls.append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    transport = TrackingTransport()
    provider = build_provider(ProviderConfig(timeout_seconds=12), KEY, transport=transport)
    assert calls == [
        {"timeout": 12, "trust_env": False, "follow_redirects": False, "transport": transport}
    ]
    await provider.aclose()
    assert transport.closes == 1
    direct = build_provider(ProviderConfig(), KEY)
    assert calls[1] == {"timeout": 30, "trust_env": False, "follow_redirects": False}
    await direct.aclose()


def test_app_creates_once_reuses_transport_and_client_closes_once(monkeypatch):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", KEY)
    resource = TrackingTransport()
    creations = []

    def factory(settings):
        creations.append(settings)
        return resource

    config = app_config(install_transport(monkeypatch, factory))
    with TestClient(create_app(config=config)) as client:
        for _ in range(2):
            response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
            assert response.status_code == 200
        assert resource.closes == 0
    assert len(creations) == 1
    assert len(resource.requests) == 2
    assert all(request.headers["authorization"] == "Bearer " + KEY for request in resource.requests)
    assert resource.closes == 1


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_client_construction_failure_closes_accepted_transport_once(monkeypatch, failure):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", KEY)
    resource = TrackingTransport()
    config = app_config(install_transport(monkeypatch, lambda _: resource))

    def fail(**kwargs):
        assert kwargs["transport"] is resource
        raise failure(SECRET)

    monkeypatch.setattr(httpx, "AsyncClient", fail)
    app = create_app(config=config)
    expected = asyncio.CancelledError if failure is asyncio.CancelledError else StartupError
    with pytest.raises(expected) as error:
        async with app.router.lifespan_context(app):
            pytest.fail("Failed initialization became ready")
    assert resource.closes == 1
    assert not app.state.ready
    if failure is RuntimeError:
        assert SECRET not in str(error.value)
        assert error.value.__cause__ is None


@pytest.mark.parametrize("cancel_startup", [False, True])
async def test_plugin_startup_failure_or_cancellation_closes_transport(monkeypatch, cancel_startup):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", KEY)
    resource = TrackingTransport()
    transport = install_transport(monkeypatch, lambda _: resource)
    entered = asyncio.Event()
    stops = []

    class Middleware:
        async def handle(self, request, context, call_next):
            return await call_next(request)

        async def startup(self):
            entered.set()
            if cancel_startup:
                await asyncio.Event().wait()
            raise RuntimeError(SECRET)

        async def shutdown(self):
            stops.append("middleware")

    module = ModuleType("test_transport_startup_middleware")
    module.PLUGIN = PluginDescriptor("middleware", 2, Settings, lambda _: Middleware())
    monkeypatch.setitem(sys.modules, module.__name__, module)
    config = app_config(transport, plugins={"m": {"module": module.__name__}}, middleware=["m"])
    app = create_app(config=config)

    async def serve():
        async with app.router.lifespan_context(app):
            pytest.fail("Failed middleware startup became ready")

    task = asyncio.create_task(serve())
    await entered.wait()
    if cancel_startup:
        task.cancel("original cancellation")
    with pytest.raises(asyncio.CancelledError if cancel_startup else StartupError) as error:
        await task
    assert resource.closes == 1
    assert stops == ["middleware"]
    assert not app.state.ready
    assert SECRET not in str(error.value)


async def test_cancellation_during_initialization_cleanup_preserves_failure_and_closes(monkeypatch):
    monkeypatch.setenv("GATEWAY7_TEST_KEY", KEY)
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowClose(TrackingTransport):
        async def aclose(self):
            entered.set()
            await release.wait()
            await super().aclose()

    resource = SlowClose()
    config = app_config(install_transport(monkeypatch, lambda _: resource))

    def fail(**kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(httpx, "AsyncClient", fail)
    app = create_app(config=config)

    async def serve():
        async with app.router.lifespan_context(app):
            pytest.fail("Failed initialization became ready")

    task = asyncio.create_task(serve())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(StartupError):
        await task
    assert resource.closes == 1
    assert not app.state.ready

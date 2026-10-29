"""Real CONNECT sockets and TLS, confined to loopback with public test certificates."""

import asyncio
import base64
from contextlib import asynccontextmanager
import ipaddress
import json
from pathlib import Path
import socket
import ssl

import httpx
import pytest

from gateway7.config import ProviderConfig, TransportConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.models import ChatRequest, Message
from gateway7.providers import MAX_RESPONSE_BYTES, build_provider
from gateway7.transport_loader import create_transport, validate_transport_config


FIXTURES = Path(__file__).parent / "fixtures" / "proxy"
KEY = "gateway7-synthetic-proxy-provider-key"
PROXY_USER = "synthetic-proxy-user"
PROXY_PASSWORD = "synthetic-proxy-password"
MODEL = "configured-test-model"
HOSTS = {
    "openai": "api.openai.com",
    "claude": "api.anthropic.com",
    "gemini": "generativelanguage.googleapis.com",
}
REQUEST = ChatRequest(
    messages=[
        Message(role="system", content="synthetic system"),
        Message(role="user", content="synthetic hello"),
        Message(role="assistant", content="synthetic reply"),
        Message(role="user", content="synthetic next"),
    ],
    max_tokens=32,
)


def reply(kind):
    if kind == "openai":
        data = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
    elif kind == "claude":
        data = {
            "content": [{"type": "text", "text": "pong"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
    else:
        data = {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "pong"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 3,
                "thoughtsTokenCount": 1,
            },
        }
    return json.dumps(data).encode()


def server_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        FIXTURES / "synthetic-server.pem", FIXTURES / "synthetic-server-key.pem"
    )
    return context


def trusted_context():
    context = ssl.create_default_context(cafile=str(FIXTURES / "synthetic-ca.pem"))
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    return context


@pytest.fixture(autouse=True)
def credentials_stay_out_of_logs(caplog):
    caplog.set_level("INFO")
    yield
    for secret in (KEY, PROXY_USER, PROXY_PASSWORD):
        assert secret not in caplog.text


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    """A regression must fail locally before it can resolve or connect externally."""
    getaddrinfo = socket.getaddrinfo
    connect = socket.socket.connect
    attempts = []
    forbidden = []

    def local_getaddrinfo(host, *args, **kwargs):
        if host not in ("localhost", b"localhost", "127.0.0.1", b"127.0.0.1", "::1", b"::1"):
            forbidden.append(host)
            raise AssertionError("External DNS is forbidden in proxy tests")
        return getaddrinfo(host, *args, **kwargs)

    def local_connect(sock, address):
        if isinstance(address, tuple):
            if not ipaddress.ip_address(address[0]).is_loopback:
                forbidden.append(address)
                raise AssertionError("External connections are forbidden in proxy tests")
            attempts.append(address)
        return connect(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", local_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    yield attempts
    assert forbidden == []


@pytest.fixture
def test_ca(monkeypatch):
    """Change only trust roots; retain real HTTPX transports, TLS and CONNECT."""
    transport = httpx.AsyncHTTPTransport
    contexts = []

    def with_test_ca(**kwargs):
        production_context = kwargs["verify"]
        assert isinstance(production_context, ssl.SSLContext)
        assert production_context.verify_mode == ssl.CERT_REQUIRED
        assert production_context.check_hostname
        assert kwargs["trust_env"] is False
        assert kwargs["retries"] == 0
        destination = trusted_context()
        contexts.append(destination)
        kwargs["verify"] = destination
        proxy = kwargs["proxy"]
        if proxy.url.scheme == "https":
            assert proxy.ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert proxy.ssl_context.check_hostname
            assert proxy.ssl_context is not production_context
            proxy_context = trusted_context()
            assert proxy_context is not destination
            contexts.append(proxy_context)
            kwargs["proxy"] = httpx.Proxy(
                proxy.url, auth=proxy.auth, headers=proxy.headers, ssl_context=proxy_context
            )
        else:
            assert proxy.ssl_context is None
        return transport(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", with_test_ca)
    return contexts


async def read_request(reader):
    raw = await reader.readuntil(b"\r\n\r\n")
    lines = raw.decode("ascii").split("\r\n")
    headers = dict(line.split(": ", 1) for line in lines[1:] if line)
    headers = {name.lower(): value for name, value in headers.items()}
    body = await reader.readexactly(int(headers.get("content-length", "0")))
    return lines[0], headers, body, raw


class LocalProxy:
    """One controlled target and proxy, with observable close events and no DNS forwarding."""

    def __init__(self, *, kind="openai", https=False, mode="reply", body=None, status=200):
        self.kind, self.https, self.mode = kind, https, mode
        self.body = reply(kind) if body is None else body
        self.status = status
        self.connects, self.requests, self.tunnel_bytes = [], [], bytearray()
        self.tasks, self.writers, self.errors = [], [], []
        self.blocked = asyncio.Event()
        self.other_ready = asyncio.Event()
        self.release_other = asyncio.Event()
        self.target_closed = asyncio.Event()
        self.proxy_closed = asyncio.Event()
        self.sni = []

    def accept(self, handler, closed):
        def callback(reader, writer):
            self.writers.append(writer)

            async def run():
                try:
                    await handler(reader, writer)
                except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
                    pass  # Peer cancellation and deliberate protocol failures close sockets.
                except Exception as error:
                    self.errors.append(error)
                finally:
                    writer.close()
                    try:
                        await asyncio.wait_for(writer.wait_closed(), 2)
                    except (ConnectionError, TimeoutError, ssl.SSLError):
                        pass
                    closed.set()

            self.tasks.append(asyncio.create_task(run()))

        return callback

    async def __aenter__(self):
        context = server_context()
        context.set_servername_callback(lambda _socket, name, _context: self.sni.append(name))
        self.target_context = context
        self.target = await asyncio.start_server(
            self.accept(self.handle_target, self.target_closed),
            "127.0.0.1",
            0,
            ssl=None if self.mode in ("handshake", "direct") else context,
        )
        self.target_port = self.target.sockets[0].getsockname()[1]
        self.proxy_context = server_context()
        self.proxy = await asyncio.start_server(
            self.accept(self.handle_proxy, self.proxy_closed),
            "127.0.0.1",
            0,
            ssl=self.proxy_context if self.https and self.mode != "proxy_handshake" else None,
        )
        self.proxy_port = self.proxy.sockets[0].getsockname()[1]
        scheme = "https" if self.https else "http"
        self.url = f"{scheme}://{PROXY_USER}:{PROXY_PASSWORD}@127.0.0.1:{self.proxy_port}"
        return self

    async def __aexit__(self, *_):
        self.proxy.close()
        self.target.close()
        for writer in self.writers:
            writer.close()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(
            asyncio.gather(
                self.proxy.wait_closed(),
                self.target.wait_closed(),
                *self.tasks,
                return_exceptions=True,
            ),
            3,
        )
        assert self.errors == []

    async def handle_target(self, reader, writer):
        if self.mode == "handshake":
            if not self.blocked.is_set():
                assert await reader.read(1) == b"\x16"  # TLS ClientHello, before provider headers.
                self.blocked.set()
                await reader.read()
                return
            await writer.start_tls(self.target_context, ssl_handshake_timeout=3)
        request = await read_request(reader)
        self.requests.append(request)
        if self.mode in ("body", "concurrent") and len(self.requests) == 1:
            writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\n{\r\n")
            await writer.drain()
            self.blocked.set()
            await reader.read()  # Client cancellation must close this unfinished response.
            return
        if self.mode == "concurrent":
            self.other_ready.set()
            await self.release_other.wait()
        writer.write(
            f"HTTP/1.1 {self.status} Test\r\nContent-Length: {len(self.body)}\r\n"
            "Connection: close\r\nLocation: https://untrusted.invalid/\r\n\r\n".encode()
            + self.body
        )
        await writer.drain()

    async def handle_proxy(self, reader, writer):
        if self.mode == "proxy_handshake":
            if not self.blocked.is_set():
                assert await reader.read(1) == b"\x16"  # Outer TLS, before CONNECT exists.
                self.blocked.set()
                await reader.read()
                return
            await writer.start_tls(self.proxy_context, ssl_handshake_timeout=3)
        request = await read_request(reader)
        self.connects.append(request)
        assert request[0] == f"CONNECT {HOSTS[self.kind]}:443 HTTP/1.1"
        assert request[2] == b""
        if self.mode == "407":
            writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        if self.mode == "drop":
            return
        upstream_reader, upstream_writer = await asyncio.open_connection(
            "127.0.0.1", self.target_port
        )
        self.writers.append(upstream_writer)
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        async def relay(source, destination, *, observe=False):
            while data := await source.read(65536):
                if observe:
                    self.tunnel_bytes.extend(data)
                destination.write(data)
                await destination.drain()

        relays = [
            asyncio.create_task(relay(reader, upstream_writer, observe=True)),
            asyncio.create_task(relay(upstream_reader, writer)),
        ]
        try:
            done, _ = await asyncio.wait(relays, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in relays:
                task.cancel()
            await asyncio.gather(*relays, return_exceptions=True)
            upstream_writer.close()
            await upstream_writer.wait_closed()


@asynccontextmanager
async def proxied_provider(monkeypatch, url, kind="openai"):
    monkeypatch.setenv("GATEWAY7_PROXY_TEST_URL", url)
    config = ProviderConfig(
        kind=kind,
        model=MODEL,
        timeout_seconds=3.0,
        transport=TransportConfig(
            module="gateway7.transports.http_proxy",
            settings={"url_env": "GATEWAY7_PROXY_TEST_URL"},
        ),
    )
    transport = create_transport(validate_transport_config(config.transport))
    provider = build_provider(config, KEY, transport=transport)
    try:
        yield provider
    finally:
        await provider.aclose()
        assert provider._client.is_closed


def assert_safe_error(error, reason, url):
    assert type(error) is ProviderError
    assert str(error) == "Provider request failed"
    assert error.reason is reason
    assert error.__suppress_context__
    for secret in (KEY, PROXY_USER, PROXY_PASSWORD, url, "untrusted.invalid"):
        assert secret not in str(error)


def assert_wire_request(proxy, kind):
    assert len(proxy.connects) == len(proxy.requests) == 1
    connect, connect_headers, _, raw_connect = proxy.connects[0]
    assert connect == f"CONNECT {HOSTS[kind]}:443 HTTP/1.1"
    expected_auth = base64.b64encode(f"{PROXY_USER}:{PROXY_PASSWORD}".encode()).decode()
    assert connect_headers["proxy-authorization"] == "Basic " + expected_auth
    assert KEY.encode() not in raw_connect + proxy.tunnel_bytes
    assert b"synthetic hello" not in raw_connect + proxy.tunnel_bytes
    line, headers, body, _ = proxy.requests[0]
    assert headers["host"] == HOSTS[kind]
    assert "proxy-authorization" not in headers
    assert PROXY_USER not in str(headers) and PROXY_PASSWORD not in str(headers)
    assert KEY.encode() not in body
    assert proxy.sni == [HOSTS[kind]]
    conversation = [message.model_dump() for message in REQUEST.messages[1:]]
    if kind == "openai":
        assert line == "POST /v1/chat/completions HTTP/1.1"
        assert headers["authorization"] == "Bearer " + KEY
        assert json.loads(body) == {
            "model": MODEL,
            "messages": [m.model_dump() for m in REQUEST.messages],
            "max_completion_tokens": 32,
            "stream": False,
            "store": False,
        }
    elif kind == "claude":
        assert line == "POST /v1/messages HTTP/1.1"
        assert headers["x-api-key"] == KEY
        assert headers["anthropic-version"] == "2023-06-01"
        assert json.loads(body) == {
            "model": MODEL,
            "messages": conversation,
            "system": "synthetic system",
            "max_tokens": 32,
        }
    else:
        assert line == f"POST /v1beta/models/{MODEL}:generateContent HTTP/1.1"
        assert headers["x-goog-api-key"] == KEY
        assert json.loads(body) == {
            "contents": [
                {"role": "user", "parts": [{"text": "synthetic hello"}]},
                {"role": "model", "parts": [{"text": "synthetic reply"}]},
                {"role": "user", "parts": [{"text": "synthetic next"}]},
            ],
            "systemInstruction": {"parts": [{"text": "synthetic system"}]},
            "generationConfig": {"maxOutputTokens": 32, "candidateCount": 1},
        }


@pytest.mark.parametrize("kind", ["openai", "claude", "gemini"])
async def test_real_connect_routes_each_adapter_and_separates_credentials(
    monkeypatch, test_ca, kind
):
    async with LocalProxy(kind=kind) as proxy:
        async with proxied_provider(monkeypatch, proxy.url, kind) as provider:
            answer = await provider.complete(REQUEST)
        assert answer.text == "pong" and answer.finish_reason == "stop"
        assert answer.usage == {"input_tokens": 12, "output_tokens": 4}
        assert_wire_request(proxy, kind)
        assert len(test_ca) == 1


async def test_https_proxy_uses_two_verified_tls_hops_ignoring_environment(monkeypatch, test_ca):
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://external-proxy.invalid:9")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/synthetic-poisoned-ca.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent/synthetic-poisoned-ca-dir")
    async with LocalProxy(https=True) as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            assert (await provider.complete(REQUEST)).text == "pong"
        assert_wire_request(proxy, "openai")
        assert len(test_ca) == 2 and test_ca[0] is not test_ca[1]
        assert all(c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname for c in test_ca)


@pytest.mark.parametrize("mode", ["407", "drop"])
async def test_proxy_failure_is_safe_without_retry_or_direct_fallback(monkeypatch, test_ca, mode):
    async with LocalProxy(mode=mode) as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            with pytest.raises(ProviderError) as caught:
                await provider.complete(REQUEST)
        assert_safe_error(caught.value, ProviderErrorReason.TRANSPORT, proxy.url)
        assert len(proxy.connects) == 1
        assert proxy.requests == [] and proxy.tunnel_bytes == b""


async def test_unavailable_proxy_is_attempted_once_without_fallback(
    monkeypatch, test_ca, loopback_only
):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))  # A reserved, non-listening port refuses connections.
        port = reserved.getsockname()[1]
        url = f"http://{PROXY_USER}:{PROXY_PASSWORD}@127.0.0.1:{port}"
        async with proxied_provider(monkeypatch, url) as provider:
            with pytest.raises(ProviderError) as caught:
                await provider.complete(REQUEST)
        assert_safe_error(caught.value, ProviderErrorReason.TRANSPORT, url)
        assert loopback_only == [("127.0.0.1", port)]


@pytest.mark.parametrize("mode", ["handshake", "body"])
async def test_cancellation_closes_tunnel_and_target_before_provider_shutdown(
    monkeypatch, test_ca, mode
):
    async with LocalProxy(mode=mode) as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            task = asyncio.create_task(provider.complete(REQUEST))
            try:
                await asyncio.wait_for(proxy.blocked.wait(), 3)
                task.cancel("synthetic proxy cancellation")
                with pytest.raises(asyncio.CancelledError, match="synthetic proxy cancellation"):
                    await asyncio.wait_for(task, 3)
                await asyncio.wait_for(proxy.proxy_closed.wait(), 3)
                await asyncio.wait_for(proxy.target_closed.wait(), 3)
                assert not provider._client.is_closed
                assert len(proxy.connects) == 1
                assert len(proxy.requests) == (1 if mode == "body" else 0)
                # A cancelled request must not close or poison the shared client.
                assert (await provider.complete(REQUEST)).text == "pong"
                assert len(proxy.connects) == 2
                assert len(proxy.requests) == (2 if mode == "body" else 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_cancelling_one_request_preserves_another_active_tunnel(monkeypatch, test_ca):
    async with LocalProxy(mode="concurrent") as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            first = asyncio.create_task(provider.complete(REQUEST))
            second = None
            try:
                await asyncio.wait_for(proxy.blocked.wait(), 3)
                second = asyncio.create_task(provider.complete(REQUEST))
                await asyncio.wait_for(proxy.other_ready.wait(), 3)
                assert len(proxy.connects) == len(proxy.requests) == 2
                first.cancel("cancel only the first request")
                with pytest.raises(asyncio.CancelledError, match="cancel only the first request"):
                    await asyncio.wait_for(first, 3)
                await asyncio.wait_for(proxy.proxy_closed.wait(), 3)
                await asyncio.wait_for(proxy.target_closed.wait(), 3)
                assert not provider._client.is_closed
                assert not second.done()
                proxy.release_other.set()
                assert (await asyncio.wait_for(second, 3)).text == "pong"
                assert len(proxy.connects) == len(proxy.requests) == 2
            finally:
                tasks = [first] if second is None else [first, second]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


async def test_cancellation_during_https_proxy_handshake_closes_socket_and_client_still_works(
    monkeypatch,
    test_ca,
):
    async with LocalProxy(https=True, mode="proxy_handshake") as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            task = asyncio.create_task(provider.complete(REQUEST))
            try:
                await asyncio.wait_for(proxy.blocked.wait(), 3)
                assert proxy.connects == [] and proxy.requests == []
                task.cancel("cancel before CONNECT")
                with pytest.raises(asyncio.CancelledError, match="cancel before CONNECT"):
                    await asyncio.wait_for(task, 3)
                await asyncio.wait_for(proxy.proxy_closed.wait(), 3)
                assert not proxy.target_closed.is_set()
                assert not provider._client.is_closed
                assert (await provider.complete(REQUEST)).text == "pong"
                assert_wire_request(proxy, "openai")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("extra", [0, 1], ids=["exact-limit", "overflow"])
async def test_response_limit_still_applies_through_real_tunnel(monkeypatch, test_ca, extra):
    body = reply("openai")
    body += b" " * (MAX_RESPONSE_BYTES + extra - len(body))
    async with LocalProxy(body=body) as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            if extra:
                with pytest.raises(ProviderError) as caught:
                    await provider.complete(REQUEST)
                assert_safe_error(caught.value, ProviderErrorReason.INVALID_RESPONSE, proxy.url)
            else:
                assert (await provider.complete(REQUEST)).text == "pong"
        assert len(proxy.connects) == len(proxy.requests) == 1


async def test_upstream_redirect_does_not_escape_proxy_or_repeat_request(monkeypatch, test_ca):
    async with LocalProxy(status=302, body=b"synthetic redirect") as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            with pytest.raises(ProviderError) as caught:
                await provider.complete(REQUEST)
        assert_safe_error(caught.value, ProviderErrorReason.REJECTED, proxy.url)
        assert len(proxy.connects) == len(proxy.requests) == 1


@pytest.mark.parametrize("https", [False, True], ids=["destination-tls", "proxy-tls"])
async def test_production_trust_rejects_synthetic_certificate(monkeypatch, https):
    async with LocalProxy(https=https) as proxy:
        async with proxied_provider(monkeypatch, proxy.url) as provider:
            with pytest.raises(ProviderError) as caught:
                await provider.complete(REQUEST)
            if not https:
                # CONNECT was accepted, so its EOF is observable even though
                # destination certificate rejection prevents the TLS callback.
                await asyncio.wait_for(proxy.proxy_closed.wait(), 3)
                assert not provider._client.is_closed
        assert_safe_error(caught.value, ProviderErrorReason.TRANSPORT, proxy.url)
        assert len(proxy.connects) == (0 if https else 1)
        assert proxy.requests == []


async def test_default_direct_transport_ignores_proxy_and_ca_environment(monkeypatch):
    body = json.dumps({"text": "direct pong", "usage": None}).encode()
    async with LocalProxy(mode="direct", body=body) as proxy:
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            monkeypatch.setenv(name, proxy.url)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/synthetic-poisoned-ca.pem")
        monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent/synthetic-poisoned-ca-dir")
        provider = build_provider(
            ProviderConfig(base_url=f"http://127.0.0.1:{proxy.target_port}"), KEY
        )
        try:
            assert (await provider.complete(REQUEST)).text == "direct pong"
        finally:
            await provider.aclose()
        assert proxy.connects == []
        assert len(proxy.requests) == 1
        line, headers, body, _ = proxy.requests[0]
        assert line == "POST /chat HTTP/1.1"
        assert headers["authorization"] == "Bearer " + KEY
        assert "proxy-authorization" not in headers
        assert json.loads(body) == REQUEST.model_dump(mode="json")

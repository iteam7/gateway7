"""Explicit HTTP(S) proxy configuration; no ambient proxy or CA discovery."""

import asyncio
import ipaddress
import os
import re
import ssl
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from gateway7.errors import StartupError
from gateway7.transport_api import API_VERSION, TransportDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    url_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)


class _RedactedProxy(httpx.Proxy):
    def __repr__(self) -> str:
        return "Proxy(<redacted>)"


async def _finish_close(task: asyncio.Task[None]) -> None:
    """A cancelled waiter must not cancel or lose the resource's one close task."""
    cancelled = None
    try:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as error:
                if cancelled is None:
                    cancelled = error
        task.result()
    finally:
        if cancelled is not None:
            raise cancelled


class _OwnedTransport:
    def __init__(self, transport: httpx.AsyncBaseTransport, owner: "_ProxyTransport") -> None:
        self.transport = transport
        self.owner = owner
        self.network_stream: Any = None
        self._closing: asyncio.Task[None] | None = None

    async def _close(self) -> None:
        try:
            try:
                if self.network_stream is not None:
                    # A cancelled TLS-to-proxy handshake can leave its raw
                    # stream outside httpcore's pool. The trace extension gives
                    # us ownership without reaching into pool internals.
                    await self.network_stream.aclose()
            finally:
                await self.transport.aclose()
        finally:
            # Retain ownership until the close attempt actually finishes.
            self.owner._active.discard(self)

    async def aclose(self) -> None:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        await _finish_close(self._closing)


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, owned: _OwnedTransport) -> None:
        self._stream = stream
        self._owned = owned
        self._closing: asyncio.Task[None] | None = None

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def _close(self) -> None:
        try:
            await self._stream.aclose()
        finally:
            await self._owned.aclose()

    async def aclose(self) -> None:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        await _finish_close(self._closing)


class _ProxyTransport(httpx.AsyncBaseTransport):
    """One configured transport; each request owns its complete proxy connection pool.

    httpcore 1.0.9 can leave CONNECT tunnels ACTIVE when TLS is cancelled. Keeping
    a pool for each request permits public-API cleanup without closing another
    request's connections. Proxy mode deliberately does not reuse connections.
    """

    def __init__(self, proxy: httpx.Proxy, context: ssl.SSLContext) -> None:
        self._proxy = proxy
        self._context = context
        self._active: set[_OwnedTransport] = set()
        self._closed = False
        self._closing: asyncio.Task[None] | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._closed:
            raise httpx.TransportError("Provider transport is closed")
        inner = httpx.AsyncHTTPTransport(
            proxy=self._proxy, verify=self._context, trust_env=False, retries=0
        )
        owned = _OwnedTransport(inner, self)
        self._active.add(owned)
        original_trace = request.extensions.get("trace")

        async def trace(name: str, info: dict[str, Any]) -> None:
            if name in (
                "connection.connect_tcp.complete",
                "connection.start_tls.complete",
                "proxy.start_tls.complete",
            ):
                owned.network_stream = info["return_value"]
            if original_trace is not None:
                await original_trace(name, info)

        # The HTTPX trace extension exposes completed connection streams, not
        # request bodies. Retain only the latest stream and never log trace data.
        request.extensions["trace"] = trace
        try:
            response = await inner.handle_async_request(request)
            assert isinstance(response.stream, httpx.AsyncByteStream)
            response.stream = _ResponseStream(response.stream, owned)
            return response
        except BaseException:
            try:
                await owned.aclose()
            except (Exception, asyncio.CancelledError):
                pass  # Cleanup must not replace the original failure/cancellation.
            raise
        finally:
            if original_trace is None:
                request.extensions.pop("trace", None)
            else:
                request.extensions["trace"] = original_trace

    async def _close(self) -> None:
        results = await asyncio.gather(
            *(owned.aclose() for owned in tuple(self._active)), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    async def aclose(self) -> None:
        self._closed = True
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        await _finish_close(self._closing)


def _proxy_url(value: str | None) -> str:
    try:
        if (
            not value
            or len(value) > 4096
            or not value.isascii()
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)
            or any(char in value for char in ("?", "#", "\\"))
            or re.search(r"%(?![0-9A-Fa-f]{2})", value)
        ):
            raise ValueError
        url = urlsplit(value)
        host = url.hostname
        authority = url.netloc.rsplit("@", 1)[-1]
        if (
            url.scheme not in ("http", "https")
            or not host
            or url.path not in ("", "/")
            or url.netloc.count("@") > 1
            or authority.endswith(":")
            or url.port == 0
        ):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (
                len(host) > 253
                or re.fullmatch(r"[0-9.]+", host)
                or any(
                    re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) is None
                    for label in (host[:-1] if host.endswith(".") else host).split(".")
                )
            ):
                raise ValueError from None
        for credential in (url.username, url.password):
            if credential is not None and any(
                byte < 32 or byte == 127 for byte in unquote_to_bytes(credential)
            ):
                raise ValueError
        if url.username == "":
            raise ValueError
        # Parsing twice must not silently target a different host or port.
        parsed = httpx.URL(value)
        if (
            parsed.host != host
            or parsed.port != url.port
            and not (parsed.port is None and url.port == {"http": 80, "https": 443}[url.scheme])
        ):
            raise ValueError
    except Exception:
        raise StartupError("Proxy URL environment variable is missing or invalid") from None
    return value


def create(settings: Settings) -> httpx.AsyncBaseTransport:
    try:
        url = _proxy_url(os.environ.get(settings.url_env))
        destination_context = httpx.create_ssl_context(verify=True, trust_env=False)
        # HTTPS proxies have a separate TLS connection from the destination.
        # An explicit context prevents httpcore from consulting SSL_CERT_FILE/DIR.
        proxy_context = (
            httpx.create_ssl_context(verify=True, trust_env=False)
            if urlsplit(url).scheme == "https"
            else None
        )
        proxy = _RedactedProxy(url, ssl_context=proxy_context)
        return _ProxyTransport(proxy, destination_context)
    except Exception:
        raise StartupError("HTTP proxy transport initialization failed") from None


TRANSPORT = TransportDescriptor(
    id="http_proxy", api_version=API_VERSION, settings_model=Settings, create=create
)

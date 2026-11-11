"""Account catalog discovery uses only injected transports and local ASGI calls."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
import gzip
import importlib
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from gateway7.app import create_app
from gateway7.config import GatewayConfig, ProviderConfig
from gateway7.errors import ProviderError, ProviderErrorReason
from gateway7.providers import CatalogModel, build_provider

KEY = "gateway7-synthetic-catalog-provider"
TOKEN = "gateway7-synthetic-catalog-client"
OTHER_TOKEN = "gateway7-synthetic-catalog-other"
AUTH = {"authorization": "Bearer " + TOKEN}
OPAQUE_MODEL = "ft:synthetic/account:model/" + "x" * 160
RECORD = {"id": OPAQUE_MODEL, "object": "model", "created": 42, "owned_by": "synthetic"}
DOCUMENT = {"object": "list", "data": [RECORD]}
PROVIDERS = importlib.import_module("gateway7.providers")


@asynccontextmanager
async def catalog_provider(handle, *, kind="openai"):
    provider = build_provider(
        ProviderConfig(kind=kind, model="configured-model"),
        KEY,
        transport=httpx.MockTransport(handle),
    )
    try:
        yield provider
    finally:
        await provider.aclose()


async def checkpoint():
    ready = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(ready.set_result, None)
    await ready


class CatalogStream(httpx.AsyncByteStream):
    def __init__(self, body=None, *, pause=False, hold_close=False, close_fails=False):
        self.body = json.dumps(DOCUMENT).encode() if body is None else body
        self.reading = asyncio.Event()
        self.release = asyncio.Event()
        self.closing = asyncio.Event()
        self.close_release = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_attempts = 0
        self.close_interrupted = False
        self.close_fails = close_fails
        if not pause:
            self.release.set()
        if not hold_close:
            self.close_release.set()

    async def __aiter__(self):
        self.reading.set()
        await self.release.wait()
        for offset in range(0, len(self.body), 4096):
            yield self.body[offset : offset + 4096]

    async def aclose(self):
        self.close_attempts += 1
        self.closing.set()
        try:
            await self.close_release.wait()
        except asyncio.CancelledError:
            self.close_interrupted = True
            raise
        self.closed.set()
        if self.close_fails:
            raise httpx.ReadError("SYNTHETIC_PRIVATE_CLOSE")


def streamed_catalog(stream, *, status=200, **headers):
    return httpx.Response(
        status, headers={"content-type": "application/json; charset=utf-8", **headers}, stream=stream
    )


async def test_catalog_reuses_production_client_origin_credentials_and_proxy_transport(monkeypatch):
    from gateway7.http_lifecycle import _OwnedCloseStream
    from gateway7.responses_provider import _OwnedCloseStream as native_close

    assert native_close is _OwnedCloseStream
    seen = []
    stream = CatalogStream()
    monkeypatch.setenv("HTTPS_PROXY", "http://synthetic-env-proxy.invalid:9")

    def handle(wire):
        seen.append(wire)
        assert wire.method == "GET"
        assert str(wire.url) == "https://api.openai.com/v1/models"
        assert wire.headers["authorization"] == "Bearer " + KEY
        assert not wire.content
        assert not any(name.startswith("x-gateway7-") for name in wire.headers)
        assert wire.extensions["timeout"]["read"] == 30.0
        return streamed_catalog(stream)

    async with catalog_provider(handle) as provider:
        client, transport = provider._client, provider._client._transport
        assert client._trust_env is False and client.follow_redirects is False
        assert not client._mounts
        result = await provider.get_models()
        assert result == (CatalogModel(OPAQUE_MODEL, 42, "synthetic"),)
        assert await provider.get_models() is result
        assert provider._client is client and client._transport is transport
        assert not client.is_closed
        with pytest.raises(FrozenInstanceError):
            result[0].id = "changed"
        assert not hasattr(result[0], "__dict__")
    assert len(seen) == stream.close_attempts == 1 and stream.closed.is_set()
    assert client.is_closed


async def test_catalog_ttl_is_account_instance_scoped_without_stale_fallback(monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(PROVIDERS, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    seen = []

    def handle(wire):
        seen.append(wire)
        if len(seen) == 3:
            return httpx.Response(503, content=b"SYNTHETIC_PRIVATE_UPSTREAM")
        return httpx.Response(200, json=DOCUMENT)

    async with catalog_provider(handle) as first, catalog_provider(handle) as second:
        result = await first.get_models()
        await second.get_models()
        clock[0] += 299.999
        assert await first.get_models() is result and len(seen) == 2
        clock[0] += 0.001
        with pytest.raises(ProviderError):
            await first.get_models()
        assert len(seen) == 3
        with pytest.raises(ProviderError):
            await first.get_models()
        assert len(seen) == 3
        clock[0] += 1.0
        assert await first.get_models() == result and len(seen) == 4


async def test_valid_empty_catalog_is_cached_as_success_not_confused_with_failure():
    seen = []

    def handle(wire):
        seen.append(wire)
        return httpx.Response(200, json={"object": "list", "data": []})

    async with catalog_provider(handle) as provider:
        assert await provider.get_models() == ()
        assert await provider.get_models() == ()
    assert len(seen) == 1


@pytest.mark.parametrize("kind", ["fake", "claude", "gemini"])
async def test_other_adapters_never_invent_a_discovery_api(kind):
    seen = []
    async with catalog_provider(lambda wire: seen.append(wire), kind=kind) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.REJECTED and not seen


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 429, 500, 503])
async def test_catalog_status_failures_are_sanitized_cached_and_not_retried(status):
    seen = []
    stream = CatalogStream(b"SYNTHETIC_PRIVATE_UPSTREAM " + KEY.encode())

    def handle(wire):
        seen.append(wire)
        return streamed_catalog(stream, status=status, location="https://untrusted.invalid")

    async with catalog_provider(handle) as provider:
        for _ in range(2):
            with pytest.raises(ProviderError, match="^Provider request failed$") as error:
                await provider.get_models()
            assert "SYNTHETIC_PRIVATE" not in repr(error.value)
            assert KEY not in repr(error.value) and error.value.__suppress_context__
    assert len(seen) == stream.close_attempts == 1 and stream.closed.is_set()


@pytest.mark.parametrize(
    "failure,reason",
    [
        (httpx.ConnectError, "transport"),
        (httpx.ReadTimeout, "timeout"),
        (httpx.DecodingError, "invalid_response"),
        (RuntimeError, "unknown"),
    ],
)
async def test_catalog_transport_failures_never_leak_raw_details_or_retry(failure, reason):
    seen = []

    def handle(wire):
        seen.append(wire)
        raise failure("SYNTHETIC_PRIVATE " + KEY + str(wire.url))

    async with catalog_provider(handle) as provider:
        for _ in range(2):
            with pytest.raises(ProviderError) as error:
                await provider.get_models()
            assert error.value.reason == reason
            assert str(error.value) == "Provider request failed"
            assert KEY not in repr(error.value)
    assert len(seen) == 1


@pytest.mark.parametrize(
    "fragment",
    [
        '{"duplicate":1,"duplicate":2}',
        "NaN",
        "Infinity",
        "-Infinity",
        "1e9999",
        '{"broken":[}',
        "[" * 64 + "null" + "]" * 64,
        '"\\ud800"',
        '{"\\ud800":1}',
    ],
    ids=["duplicate", "nan", "inf", "negative-inf", "overflow", "syntax", "depth", "surrogate", "key"],
)
async def test_entire_unknown_metadata_is_validated_before_projection(fragment):
    body = (json.dumps(DOCUMENT)[:-1] + ',"private_metadata":' + fragment + "}").encode()
    stream = CatalogStream(body)
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert stream.close_attempts == 1


@pytest.mark.parametrize(
    "change",
    [
        {"id": None}, {"id": 1}, {"id": True}, {"id": ""}, {"id": "bad id"},
        {"id": "bad\nline"}, {"id": "bad\x7f"}, {"id": "bad\ud800"},
        {"id": "é" * 513}, {"created": True}, {"created": 1.0}, {"created": "1"},
        {"created": -1}, {"created": 2**63}, {"created": None},
        {"owned_by": None}, {"owned_by": 1}, {"owned_by": ""},
        {"owned_by": "é" * 513}, {"owned_by": "bad\nowner"},
        {"owned_by": "bad\x7fowner"}, {"owned_by": "bad\u200bowner"},
        {"object": "other"}, {"object": None},
    ],
)
async def test_catalog_records_are_strict_bounded_and_control_safe(change):
    body = {"object": "list", "data": [{**RECORD, **change}]}
    async with catalog_provider(lambda _: httpx.Response(200, content=json.dumps(body).encode(), headers={"content-type": "application/json"})) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize(
    "body",
    [
        [], {}, {"object": "other", "data": []}, {"object": "list", "data": {}},
        {"object": "list", "data": [RECORD, RECORD]}, {"object": "list", "data": [None]},
        {"object": "list", "data": [{key: value for key, value in RECORD.items() if key != "created"}]},
        {"object": "list", "data": [{**RECORD, "id": str(i)} for i in range(4097)]},
    ],
    ids=["array", "missing", "wrong-object", "data-type", "duplicate-id", "record-type", "required", "count"],
)
async def test_catalog_envelope_count_required_fields_and_duplicate_ids_are_checked(body):
    async with catalog_provider(lambda _: httpx.Response(200, json=body)) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE


@pytest.mark.parametrize("compressed", [False, True])
async def test_catalog_byte_limit_applies_to_decoded_body_without_truncation(compressed):
    body = json.dumps({**DOCUMENT, "private_metadata": "x" * 1_048_576}).encode()
    stream = CatalogStream(gzip.compress(body) if compressed else body)
    headers = {"content-encoding": "gzip"} if compressed else {}
    async with catalog_provider(lambda _: streamed_catalog(stream, **headers)) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE
    assert stream.close_attempts == 1


async def test_catalog_boundary_sizes_and_valid_unknown_metadata_are_not_truncated():
    records = [{**RECORD, "id": str(i)} for i in range(4096)]
    records[0] = {**RECORD, "id": "é" * 512, "owned_by": "é" * 512, "created": 2**63 - 1}
    document = {"object": "list", "data": records, "private_metadata": {"synthetic": [None, True, 1.5]}}
    source = json.dumps(document).encode()
    source += b" " * (1_048_576 - len(source))
    stream = CatalogStream(source)
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        result = await provider.get_models()
    assert len(result) == 4096 and result[0] == CatalogModel("é" * 512, 2**63 - 1, "é" * 512)
    assert not hasattr(result[0], "private_metadata")


@pytest.mark.parametrize("body,media", [(b"\xff", "application/json"), (b"{}", "text/plain")])
async def test_catalog_requires_utf8_json_media_type(body, media):
    async with catalog_provider(
        lambda _: httpx.Response(200, content=body, headers={"content-type": media})
    ) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models()
    assert error.value.reason is ProviderErrorReason.INVALID_RESPONSE


async def test_singleflight_waiter_cancellation_does_not_cancel_leader():
    seen = []
    stream = CatalogStream(pause=True)

    def handle(wire):
        seen.append(wire)
        return streamed_catalog(stream)

    async with catalog_provider(handle) as provider:
        before = asyncio.all_tasks()
        leader = asyncio.create_task(provider.get_models())
        await asyncio.wait_for(stream.reading.wait(), 1)
        cancelled = asyncio.create_task(provider.get_models())
        waiters = [asyncio.create_task(provider.get_models()) for _ in range(8)]
        await checkpoint()
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert not leader.done() and not stream.closing.is_set() and len(seen) == 1
        stream.release.set()
        result = await leader
        assert all(value is result for value in await asyncio.gather(*waiters))
        assert not (asyncio.all_tasks() - before)
    assert len(seen) == stream.close_attempts == 1


@pytest.mark.parametrize("close_fails", [False, True])
@pytest.mark.parametrize("phase", ["read", "eof", "invalid"])
async def test_cancelled_leader_waits_through_repeated_cancel_then_wakes_waiters(close_fails, phase):
    stream = CatalogStream(
        b"{}" if phase == "invalid" else None,
        pause=phase == "read",
        hold_close=True,
        close_fails=close_fails,
    )
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        before = asyncio.all_tasks()
        leader = asyncio.create_task(provider.get_models())
        await asyncio.wait_for(stream.reading.wait(), 1)
        waiter = asyncio.create_task(provider.get_models())
        await checkpoint()
        if phase == "read":
            leader.cancel("first")
        await asyncio.wait_for(stream.closing.wait(), 1)
        for _ in range(2):
            leader.cancel("during cleanup")
            await checkpoint()
            assert not leader.done() and not waiter.done() and not stream.close_interrupted
        stream.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await leader
        with pytest.raises(ProviderError) as error:
            await waiter
        assert error.value.reason is ProviderErrorReason.UNAVAILABLE
        assert stream.closed.is_set() and provider._catalog_failure is None
        assert not (asyncio.all_tasks() - before)
    assert stream.close_attempts == 1


async def test_shutdown_cancels_leader_awaits_owned_close_and_wakes_waiters():
    stream = CatalogStream(pause=True, hold_close=True)
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        before = asyncio.all_tasks()
        leader = asyncio.create_task(provider.get_models())
        await asyncio.wait_for(stream.reading.wait(), 1)
        waiter = asyncio.create_task(provider.get_models())
        await checkpoint()
        shutdown = asyncio.create_task(provider.aclose())
        await asyncio.wait_for(stream.closing.wait(), 1)
        for _ in range(2):
            shutdown.cancel()
            await checkpoint()
            assert not shutdown.done() and not leader.done() and not waiter.done()
            assert not stream.close_interrupted and not provider._client.is_closed
        with pytest.raises(ProviderError):
            await provider.get_models()
        stream.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await shutdown
        with pytest.raises(asyncio.CancelledError):
            await leader
        with pytest.raises(ProviderError):
            await waiter
        assert provider._client.is_closed and not (asyncio.all_tasks() - before)
    assert stream.close_attempts == 1 and stream.closed.is_set()


async def test_waiter_own_deadline_expires_without_cancelling_or_poisoning_leader():
    stream = CatalogStream(pause=True)
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        leader = asyncio.create_task(provider.get_models())
        await asyncio.wait_for(stream.reading.wait(), 1)
        with pytest.raises(TimeoutError):
            await provider.get_models(deadline=time.monotonic() + 0.02)
        assert not leader.done() and not stream.closing.is_set()
        stream.release.set()
        result = await leader
        assert await provider.get_models() is result and provider._catalog_failure is None


async def test_leader_own_deadline_does_not_create_account_failure_cache():
    streams = [CatalogStream(pause=True), CatalogStream()]
    seen = []

    def handle(wire):
        seen.append(wire)
        return streamed_catalog(streams[len(seen) - 1])

    async with catalog_provider(handle) as provider:
        leader = asyncio.create_task(provider.get_models(deadline=time.monotonic() + 0.03))
        await asyncio.wait_for(streams[0].reading.wait(), 1)
        waiter = asyncio.create_task(provider.get_models())
        with pytest.raises(TimeoutError):
            await leader
        with pytest.raises(ProviderError):
            await waiter
        assert provider._catalog_failure is None and streams[0].closed.is_set()
        assert await provider.get_models() == (CatalogModel(OPAQUE_MODEL, 42, "synthetic"),)
    assert len(seen) == 2


async def test_fetch_budget_is_two_seconds_independent_of_larger_request_deadline(monkeypatch):
    assert PROVIDERS.CATALOG_FETCH_SECONDS == 2.0
    monkeypatch.setattr(PROVIDERS, "CATALOG_FETCH_SECONDS", 0.02)
    stream = CatalogStream(pause=True)
    async with catalog_provider(lambda _: streamed_catalog(stream)) as provider:
        with pytest.raises(ProviderError) as error:
            await provider.get_models(deadline=time.monotonic() + 5)
        assert error.value.reason is ProviderErrorReason.TIMEOUT and stream.closed.is_set()
        assert provider._catalog_failure is ProviderErrorReason.TIMEOUT


async def test_expired_deadline_never_returns_even_a_fresh_cached_catalog():
    async with catalog_provider(lambda _: httpx.Response(200, json=DOCUMENT)) as provider:
        await provider.get_models()
        with pytest.raises(TimeoutError):
            await provider.get_models(deadline=time.monotonic() - 1)


async def test_catalog_depth_boundary_is_checked_even_for_ignored_metadata():
    source = (
        json.dumps(DOCUMENT)[:-1] + ',"private_metadata":' + "[" * 63 + "null" + "]" * 63 + "}"
    ).encode()
    async with catalog_provider(
        lambda _: httpx.Response(200, content=source, headers={"content-type": "application/json"})
    ) as provider:
        assert await provider.get_models() == (CatalogModel(OPAQUE_MODEL, 42, "synthetic"),)


@pytest.fixture
def catalog_app(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_CATALOG_KEY", KEY)
    monkeypatch.setenv("SYNTHETIC_CATALOG_TOKEN", TOKEN)
    monkeypatch.setenv("SYNTHETIC_OTHER_TOKEN", OTHER_TOKEN)

    @asynccontextmanager
    async def open_app(handle, *, kind="openai", provider_updates=None, clients=None, **updates):
        config = GatewayConfig.model_validate(
            {
                "provider": {
                    "kind": kind,
                    "model": "configured-model",
                    "key_env": "SYNTHETIC_CATALOG_KEY",
                    **(provider_updates or {}),
                },
                "auth": {
                    "enabled": True,
                    "clients": clients or {
                        "unlimited": {"token_env": "SYNTHETIC_CATALOG_TOKEN"}
                    },
                },
                **updates,
            }
        )
        provider = build_provider(config.provider, KEY, transport=httpx.MockTransport(handle))
        monkeypatch.setattr(
            importlib.import_module("gateway7.app"), "build_provider", lambda *_: provider
        )
        app = create_app(config=config)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="http://synthetic.invalid",
                trust_env=False,
            ) as client:
                yield app, client, provider
        assert provider._client.is_closed

    return open_app


async def test_app_unlimited_catalog_and_finite_clients_never_share_permissions(catalog_app):
    seen = []

    def handle(wire):
        seen.append(wire)
        return httpx.Response(200, json={**DOCUMENT, "private_metadata": "SYNTHETIC_PRIVATE_METADATA"})

    clients = {
        "unlimited": {"token_env": "SYNTHETIC_CATALOG_TOKEN"},
        "restricted": {"token_env": "SYNTHETIC_OTHER_TOKEN", "models": ["local-only"]},
    }
    async with catalog_app(handle, clients=clients) as (_, client, _):
        upstream = await client.get("/v1/models", headers=AUTH)
        local = await client.get("/v1/models", headers={"authorization": "Bearer " + OTHER_TOKEN})
        again = await client.get("/v1/models", headers=AUTH)
    assert upstream.status_code == again.status_code == local.status_code == 200
    assert upstream.json() == again.json() == DOCUMENT
    assert local.json()["data"] == [
        {"id": "local-only", "object": "model", "created": 0, "owned_by": "gateway7"}
    ]
    assert OPAQUE_MODEL not in local.text and "local-only" not in upstream.text
    assert len(seen) == 1 and "SYNTHETIC_PRIVATE" not in upstream.text


@pytest.mark.parametrize("provider_policy,client_policy,expected", [
    (None, [], []), ([], None, []), ([], ["local-a"], []),
    (["local-a", "local-b"], None, ["local-a", "local-b"]),
    (["local-a", "local-b"], ["local-b", "outside"], ["local-b"]),
    (None, ["local-only"], ["local-only"]),
])
async def test_effective_finite_policy_including_empty_never_fetches(
    catalog_app, provider_policy, client_policy, expected
):
    seen = []
    provider_updates = {} if provider_policy is None else {"allowed_models": provider_policy}
    clients = {"finite": {
        "token_env": "SYNTHETIC_CATALOG_TOKEN",
        **({} if client_policy is None else {"models": client_policy}),
    }}
    async with catalog_app(
        lambda wire: seen.append(wire), clients=clients, provider_updates=provider_updates
    ) as (_, client, _):
        response = await client.get("/v1/models", headers=AUTH)
    assert response.status_code == 200 and [item["id"] for item in response.json()["data"]] == expected
    assert all(
        item["owned_by"] == "gateway7" and item["created"] == 0 for item in response.json()["data"]
    )
    assert not seen


@pytest.mark.parametrize("kind", ["fake", "claude", "gemini"])
async def test_unlimited_other_adapters_return_only_the_local_default_seed(catalog_app, kind):
    seen = []
    async with catalog_app(lambda wire: seen.append(wire), kind=kind) as (_, client, _):
        response = await client.get("/v1/models", headers=AUTH)
    assert response.status_code == 200 and response.json()["data"] == [
        {"id": "configured-model", "object": "model", "created": 0, "owned_by": "gateway7"}
    ]
    assert not seen


@pytest.mark.parametrize("authorization", [None, "Bearer gateway7-synthetic-invalid"])
async def test_catalog_authentication_precedes_every_upstream_attempt(catalog_app, authorization):
    seen = []
    async with catalog_app(lambda wire: seen.append(wire)) as (app, client, _):
        app.state.admission.limit = 0
        response = await client.get(
            "/v1/models", headers={} if authorization is None else {"authorization": authorization}
        )
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthorized"
    assert not seen


@pytest.mark.parametrize("catalog_fails", [False, True])
async def test_app_catalog_failure_is_safe_503_and_generation_is_independent(
    catalog_app, caplog, catalog_fails
):
    seen = []

    def handle(wire):
        seen.append(wire)
        if wire.method == "GET":
            return (
                httpx.Response(401, content=(KEY + " SYNTHETIC_PRIVATE " + str(wire.url)).encode())
                if catalog_fails
                else httpx.Response(200, json={"object": "list", "data": []})
            )
        assert wire.url.path == "/v1/chat/completions"
        assert json.loads(wire.content)["model"] == OPAQUE_MODEL
        return httpx.Response(200, json={"choices": [{
            "message": {"role": "assistant", "content": "answer"}, "finish_reason": "stop"
        }]})

    with caplog.at_level("INFO", logger="gateway7"):
        async with catalog_app(handle) as (_, client, _):
            for _ in range(2):
                failed = await client.get("/v1/models", headers=AUTH)
                if catalog_fails:
                    assert failed.status_code == 503
                    assert failed.json()["error"]["code"] == "unavailable"
                else:
                    assert failed.status_code == 200 and failed.json()["data"] == []
            generated = await client.post(
                "/v1/chat/completions", headers=AUTH,
                json={"model": OPAQUE_MODEL, "messages": [{"role": "user", "content": "ping"}]},
            )
            metrics = (await client.get("/metrics")).text
    assert generated.status_code == 200 and generated.json()["model"] == OPAQUE_MODEL
    assert [wire.method for wire in seen] == ["GET", "POST"]
    assert "SYNTHETIC_PRIVATE" not in failed.text + metrics + caplog.text
    assert KEY not in failed.text + metrics + caplog.text and TOKEN not in metrics + caplog.text


class CatalogHTTP:
    def __init__(self, app, *, headers=AUTH):
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/v1/models",
            "raw_path": b"/v1/models",
            "root_path": "",
            "query_string": b"",
            "headers": [(name.encode(), value.encode()) for name, value in headers.items()],
            "client": ("synthetic", 1),
            "server": ("synthetic.invalid", 80),
        }
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait({"type": "http.request", "body": b"", "more_body": False})
        self.sent = []
        self.task = asyncio.create_task(app(self.scope, self.incoming.get, self.send))

    async def send(self, message):
        self.sent.append(dict(message))

    async def finish(self):
        await asyncio.wait_for(asyncio.shield(self.task), 1)

    @property
    def status(self):
        return next(
            (message["status"] for message in self.sent if message["type"] == "http.response.start"),
            None,
        )


async def test_app_catalog_own_deadline_is_504_and_does_not_poison_next_request(catalog_app):
    streams = [CatalogStream(pause=True), CatalogStream()]
    seen = []

    def handle(wire):
        seen.append(wire)
        return streamed_catalog(streams[len(seen) - 1])

    async with catalog_app(handle, limits={"request_timeout_seconds": 0.03}) as (app, client, provider):
        raw = CatalogHTTP(app)
        await raw.finish()
        assert raw.status == 504 and streams[0].closed.is_set()
        assert provider._catalog_failure is None and app.state.admission.active == 0
        again = await client.get("/v1/models", headers=AUTH)
        assert again.status_code == 200 and again.json() == DOCUMENT
    assert len(seen) == 2


async def test_app_catalog_disconnect_awaits_real_cleanup_even_under_repeated_cancel(catalog_app):
    stream = CatalogStream(pause=True, hold_close=True)
    async with catalog_app(lambda _: streamed_catalog(stream)) as (app, _, _):
        before = asyncio.all_tasks()
        raw = CatalogHTTP(app)
        await asyncio.wait_for(stream.reading.wait(), 1)
        raw.incoming.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(stream.closing.wait(), 1)
        for _ in range(2):
            raw.task.cancel()
            await checkpoint()
            assert not raw.task.done() and app.state.admission.active == 1
            assert not stream.close_interrupted and not stream.closed.is_set()
        stream.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await raw.task
        assert raw.status is None and stream.closed.is_set() and app.state.admission.active == 0
        assert not (asyncio.all_tasks() - before)


async def test_app_waiter_disconnect_does_not_cancel_another_requests_owned_fetch(catalog_app):
    stream = CatalogStream(pause=True)
    seen = []

    def handle(wire):
        seen.append(wire)
        return streamed_catalog(stream)

    async with catalog_app(handle) as (app, _, _):
        before = asyncio.all_tasks()
        leader = CatalogHTTP(app)
        await asyncio.wait_for(stream.reading.wait(), 1)
        waiter = CatalogHTTP(app)
        await checkpoint()
        await checkpoint()
        waiter.incoming.put_nowait({"type": "http.disconnect"})
        await waiter.finish()
        assert waiter.status == 499 and not leader.task.done() and not stream.closing.is_set()
        assert len(seen) == 1 and app.state.admission.active == 1
        stream.release.set()
        await leader.finish()
        assert leader.status == 200 and stream.closed.is_set() and app.state.admission.active == 0
        assert not (asyncio.all_tasks() - before)


async def test_app_discovery_budget_expiry_is_503_not_the_clients_504(catalog_app, monkeypatch):
    monkeypatch.setattr(PROVIDERS, "CATALOG_FETCH_SECONDS", 0.02)
    stream = CatalogStream(pause=True)
    async with catalog_app(lambda _: streamed_catalog(stream)) as (_, client, _):
        response = await client.get("/v1/models", headers=AUTH)
    assert response.status_code == 503 and response.json()["error"]["code"] == "unavailable"
    assert stream.closed.is_set()


@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions"])
async def test_native_and_chat_routes_keep_opaque_model_authority_without_discovery(
    catalog_app, path
):
    seen = []

    def handle(wire):
        seen.append(wire)
        assert wire.method == "POST" and wire.url.path == "/v1/chat/completions"
        assert json.loads(wire.content)["model"] == OPAQUE_MODEL
        return httpx.Response(200, json={"choices": [{
            "message": {"role": "assistant", "content": "answer"}, "finish_reason": "stop"
        }]})

    async with catalog_app(handle) as (_, client, _):
        response = await client.post(
            path, headers=AUTH,
            json={"model": OPAQUE_MODEL, "messages": [{"role": "user", "content": "ping"}]},
        )
    assert response.status_code == 200 and len(seen) == 1


@pytest.mark.parametrize("path", ["/chat", "/v1/chat/completions"])
async def test_unrestricted_gemini_route_rejects_path_escape_before_admission(catalog_app, path):
    seen = []
    async with catalog_app(lambda wire: seen.append(wire), kind="gemini") as (app, client, _):
        app.state.admission.limit = 0
        response = await client.post(
            path, headers=AUTH,
            json={
                "model": "models/model:otherOperation",
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
    assert response.status_code == (400 if path.startswith("/v1/") else 422)
    assert response.json()["error"]["code"] == "invalid_request" and not seen

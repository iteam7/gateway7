"""Provider boundary reservations work in buffered and streaming execution."""

import asyncio
import json
import os
import threading

import pytest

from gateway7.accounting import AccountingService, BudgetDenied
from gateway7.admin_store import AdminStore
from gateway7.config import GatewayConfig, LimitsConfig
from gateway7.db_execution import DBExecutor
from gateway7.errors import GatewayError
from gateway7.loader import load_plugins
from gateway7.pipeline import Pipeline
from gateway7.postgres_store import PostgresAdminStore
from gateway7.models import ChatRequest, Message
from gateway7.responses_models import ResponsesRequest
from test_accounting import InlineDB, policy, store as accounting_store
from test_usage import AccountingProvider, MODES, run_mode

store = accounting_store


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("outcome", ["complete", "provider_error", "cancelled"])
async def test_durable_before_and_async_terminal_accounting_cover_every_mode(store, mode, outcome):
    service = AccountingService(store, InlineDB())
    provider = AccountingProvider(outcome=outcome, usage={"input_tokens": 7, "output_tokens": 3})
    before, observer = service.bind("client_a", "fake", key_id="synthetic_key")
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_before=before,
        provider_observer=observer,
    )
    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await run_mode(pipeline, mode)
    elif outcome == "provider_error":
        with pytest.raises(GatewayError):
            await run_mode(pipeline, mode)
    else:
        await run_mode(pipeline, mode)
    assert provider.calls == 1
    events = store.list_usage_events()
    assert events["total"] == 1
    assert events["items"][0]["status"] == outcome
    assert events["items"][0]["known_input_tokens"] == 7
    assert events["items"][0]["known_output_tokens"] == 3
    assert events["items"][0]["key_id"] == "synthetic_key"


@pytest.mark.parametrize("mode", MODES)
async def test_budget_denial_is_before_provider_and_creates_no_usage(store, mode):
    policy(store, tokens=1)
    service = AccountingService(store, InlineDB())
    provider = AccountingProvider()
    before, observer = service.bind("client_a", "fake")
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_before=before,
        provider_observer=observer,
    )
    with pytest.raises(GatewayError) as caught:
        await run_mode(pipeline, mode)
    assert caught.value.code == "budget_exceeded"
    assert provider.calls == 0
    assert store.list_usage_events()["total"] == 0


def bounded_request(mode):
    if mode in ("chat", "early_chat"):
        return ChatRequest(messages=[Message(role="user", content="synthetic")], max_tokens=16)
    return ResponsesRequest(input="synthetic", max_output_tokens=16)


async def run_bounded(pipeline, mode, request):
    async def discard(_):
        pass

    if mode == "chat":
        return await pipeline.run(request, "synthetic-cancel-before-provider")
    if mode == "early_chat":
        return await pipeline.run_early(
            request, "synthetic-cancel-before-provider", on_text=discard
        )
    if mode == "responses":
        return await pipeline.run_responses(request, "synthetic-cancel-before-provider")
    return await pipeline.run_responses_early(
        request, "synthetic-cancel-before-provider", on_text=discard
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("repeated_cancel", [False, True])
async def test_cancel_after_reserve_commit_before_provider_releases_only_its_reservation(
    store, mode, repeated_cancel, monkeypatch
):
    db = DBExecutor()
    committed, release_reserve = threading.Event(), threading.Event()
    deleting, release_delete = threading.Event(), threading.Event()
    reopened = None
    task = None
    original_reserve = store.reserve_usage
    original_query = store._control_query
    address = (
        os.environ["GATEWAY7_TEST_POSTGRES_DSN"]
        if store._backend_postgres
        else store._db.execute("PRAGMA database_list").fetchone()[2]
    )
    request = bounded_request(mode)
    payload = request.model_dump(mode="json")
    allowance = (
        len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        + 1024
        + 32 * len(payload.get("messages", []))
        + 16
    )
    await db.call(policy, store, tokens=allowance)

    def reserve(*args, **kwargs):
        result = original_reserve(*args, **kwargs)
        committed.set()
        assert release_reserve.wait(5)
        return result

    def query(sql, values=()):
        result = original_query(sql, values)
        if repeated_cancel and sql.startswith("DELETE FROM {prefix}usage_events"):
            deleting.set()
            assert release_delete.wait(5)
        return result

    monkeypatch.setattr(store, "reserve_usage", reserve)
    monkeypatch.setattr(store, "_control_query", query)
    service = AccountingService(store, db)
    before, observer = service.bind("client_a", "fake")
    provider = AccountingProvider(usage={"input_tokens": 7, "output_tokens": 3})
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_before=before,
        provider_observer=observer,
    )
    try:
        task = asyncio.create_task(run_bounded(pipeline, mode, request))
        assert await asyncio.to_thread(committed.wait, 5)
        task.cancel("first cancellation")
        await asyncio.sleep(0)
        release_reserve.set()
        if repeated_cancel:
            assert await asyncio.to_thread(deleting.wait, 5)
            task.cancel("second cancellation")
            await asyncio.sleep(0)
            task.cancel("third cancellation")
            release_delete.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args == ("first cancellation",)
        assert provider.calls == 0
        await observer("cancelled", None)
        assert (await db.call(store.list_usage_events))["total"] == 0
        assert (
            await db.call(store.usage_rows, client_id=None, model=None, start=None, end=None) == []
        )
        await db.call(store.close)
        constructor = PostgresAdminStore if store._backend_postgres else AdminStore
        reopened = await db.call(constructor, address, GatewayConfig())
        assert (await db.call(reopened.list_usage_events))["total"] == 0
        following = AccountingService(reopened, db)
        next_before, next_observer = following.bind("client_a", "fake")
        await next_before(request)
        await next_observer("complete", {"input_tokens": 7, "output_tokens": 3})
        assert (await db.call(reopened.list_usage_events))["total"] == 1
    finally:
        release_reserve.set()
        release_delete.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if reopened is not None:
            await db.call(reopened.close)
        await db.close()


@pytest.mark.parametrize("failure", ["reserve", "cleanup"])
async def test_cancelled_admission_preserves_cancellation_when_storage_fails(
    store, failure, monkeypatch, caplog
):
    db = DBExecutor()
    ready, release = threading.Event(), threading.Event()
    original_reserve = store.reserve_usage
    original_query = store._control_query
    task = None

    def reserve(*args, **kwargs):
        result = original_reserve(*args, **kwargs) if failure == "cleanup" else None
        ready.set()
        assert release.wait(5)
        if failure == "reserve":
            raise BudgetDenied("synthetic admission failure")
        return result

    def query(sql, values=()):
        result = original_query(sql, values)
        if sql.startswith("DELETE FROM {prefix}usage_events"):
            raise RuntimeError("synthetic private storage failure")
        return result

    monkeypatch.setattr(store, "reserve_usage", reserve)
    monkeypatch.setattr(store, "_control_query", query)
    before, _ = AccountingService(store, db).bind("client_a", "fake")
    try:
        task = asyncio.create_task(before(bounded_request("chat")))
        assert await asyncio.to_thread(ready.wait, 5)
        task.cancel("original cancellation")
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args == ("original cancellation",)
        events = await db.call(store.list_usage_events)
        assert events["total"] == (1 if failure == "cleanup" else 0)
        if failure == "cleanup":
            assert events["items"][0]["status"] == "pending"
            assert events["items"][0]["charged_tokens"] > 0
            assert "reservation_cleanup_error" in caplog.text
            assert "synthetic private storage failure" not in caplog.text
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await db.close()


@pytest.mark.parametrize("mode", MODES)
async def test_actual_provider_cancellation_with_unknown_usage_keeps_reserved_allowance(
    store, mode
):
    db = DBExecutor()
    await db.call(policy, store, tokens=100_000)
    service = AccountingService(store, db)
    before, observer = service.bind("client_a", "fake")
    provider = AccountingProvider(outcome="cancelled", usage=None)
    pipeline = Pipeline(
        load_plugins(GatewayConfig()),
        provider,
        LimitsConfig(),
        provider_name="openai",
        provider_before=before,
        provider_observer=observer,
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await run_bounded(pipeline, mode, bounded_request(mode))
        assert provider.calls == 1
        events = await db.call(store.list_usage_events)
        assert events["total"] == 1
        event = events["items"][0]
        assert event["status"] == "cancelled"
        assert event["known_input_tokens"] is event["known_output_tokens"] is None
        assert event["charged_tokens"] == event["input_bound"] + event["output_bound"] > 0
    finally:
        await db.close()

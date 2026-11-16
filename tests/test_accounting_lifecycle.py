"""Provider boundary reservations work in buffered and streaming execution."""

import asyncio

import pytest

from gateway7.accounting import AccountingService
from gateway7.config import GatewayConfig, LimitsConfig
from gateway7.errors import GatewayError
from gateway7.loader import load_plugins
from gateway7.pipeline import Pipeline
from test_accounting import InlineDB, policy, store  # noqa: F401
from test_usage import AccountingProvider, MODES, run_mode


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

"""Resiliencia: degradación, idempotencia, reinicio."""

from __future__ import annotations

import pytest

from tests.e2e.harness import E2EHarness
from tests.fixtures.market import liquid_call_chain


@pytest.mark.resilience
@pytest.mark.asyncio
async def test_degraded_blocks_entries_allows_recovery():
    h = E2EHarness()
    chain = liquid_call_chain()
    h.inject_chain(chain)
    h.degrade_provider()
    _, order = await h.buy_selected("BULLISH", chain)
    assert order is None
    h.recover_provider()
    dec, order2 = await h.buy_selected("BULLISH", chain)
    assert order2 is not None


@pytest.mark.resilience
@pytest.mark.asyncio
async def test_idempotent_correlation_on_restart():
    h = E2EHarness()
    chain = liquid_call_chain()
    h.inject_chain(chain)
    _, order = await h.buy_selected("BULLISH", chain)
    assert order is not None
    corr = order.request.correlation_id
    await h.simulate_worker_restart()
    # no re-submit automático
    same = [o for o in h.broker._orders.values() if o.request.correlation_id == corr]  # noqa: SLF001
    assert len(same) == 1

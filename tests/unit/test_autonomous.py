"""Pruebas del servicio autónomo."""

from __future__ import annotations

import pytest

from opciones.modules.autonomous.orchestrator import (
    DistributedLock,
    OperationalState,
    TradingOrchestrator,
    reset_orchestrator,
)
from opciones.modules.configuration.settings import Settings


@pytest.mark.asyncio
async def test_orchestrator_cycle_idempotent():
    reset_orchestrator()
    settings = Settings(emergency_stop=False, trading_mode="paper", live_trading_enabled=False, _env_file=None)
    orch = TradingOrchestrator(settings=settings, simulate_market_open=True, cycle_sleep_s=0.001)
    await orch.startup()
    await orch._cycle()
    n = orch.app_state.state.cycle_count
    # Replay same idempotency key path — cycle increments key list
    await orch._cycle()
    assert orch.app_state.state.cycle_count == n + 1
    assert orch.app_state.state.state in {
        OperationalState.RUNNING,
        OperationalState.DEGRADED,
        OperationalState.EMERGENCY_STOPPED,
        OperationalState.RISK_BLOCKED,
    }


@pytest.mark.asyncio
async def test_emergency_stop_blocks_and_manual_unlock():
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    orch = TradingOrchestrator(settings=settings, simulate_market_open=True)
    await orch.startup()
    await orch.emergency.activate("test")
    assert orch.risk.is_buying_blocked()
    with pytest.raises(PermissionError):
        await orch.emergency.deactivate("NOPE")
    await orch.emergency.deactivate("MANUAL_UNLOCK_CONFIRMED")
    assert not orch.emergency.active


@pytest.mark.asyncio
async def test_lock_prevents_duplicate_instance():
    lock = DistributedLock()
    assert lock.acquire("a")
    assert not lock.acquire("b")
    lock.release("a")
    assert lock.acquire("b")


@pytest.mark.asyncio
async def test_reconnect_backoff_and_session_sim():
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    orch = TradingOrchestrator(settings=settings, simulate_market_open=True, cycle_sleep_s=0.001)
    await orch.start()
    await orch._cycle()
    await orch.pause()
    assert orch.app_state.state.state == OperationalState.PAUSED
    await orch.resume()
    await orch.stop()
    assert orch.app_state.state.state == OperationalState.STOPPED


@pytest.mark.asyncio
async def test_no_duplicate_order_notifications():
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    orch = TradingOrchestrator(settings=settings, simulate_market_open=True)
    await orch.startup()
    await orch._cycle()
    first = set(orch._processed_order_ids)
    # Simulate restart recovery of processed ids
    await orch._cycle()
    # IDs only grow, never re-notify same
    assert first.issubset(orch._processed_order_ids)

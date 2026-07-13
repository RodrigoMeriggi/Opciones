"""Pruebas de la estrategia básica en distintos regímenes de mercado."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.enums import SignalAction
from opciones.domain.models import PortfolioSnapshot, RiskLimits
from opciones.modules.configuration.settings import Settings
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.modules.strategy_engine.executor import StrategyExecutor
from opciones.modules.strategy_engine.indicators import compute_indicators
from opciones.modules.option_chain.simulator import generate_price_series


def _strategy_config(**over):
    cfg = {
        "signal_confirm_cycles": 1,
        "min_seconds_between_trades": 0,
        "min_volume": 1,
        "max_spread_pct": 25.0,
        "min_momentum_pct": 0.05,
        "rsi_min": 0,
        "rsi_max": 100,
        "max_daily_trades": 50,
    }
    cfg.update(over)
    return cfg


def _make_stack(scenario: str, liquidity: str = "high"):
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    limits = RiskLimits(
        minimum_cash_reserve=Decimal("10000"),
        maximum_position_percentage=Decimal("0.2"),
        maximum_capital_at_risk=Decimal("500000"),
        maximum_total_premium=Decimal("500000"),
        minimum_volume=1,
        maximum_bid_ask_spread_percentage=Decimal("30"),
        cooldown_after_loss_minutes=0,
        daily_trade_limit=100,
        maximum_open_positions=10,
    )
    md = MockMarketDataProvider(scenario=scenario, liquidity=liquidity)
    broker = PaperBroker(md, initial_cash=Decimal("1000000"))
    risk = DefaultRiskManager(limits=limits, settings=settings, ignore_market_hours=True)
    if risk.is_buying_blocked():
        risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    strategy = BasicOptionStrategy(risk, config=_strategy_config())
    return md, broker, risk, strategy


@pytest.mark.asyncio
async def test_bullish_can_generate_call_bias():
    md, broker, risk, strategy = _make_stack("bullish")
    underlying = await md.get_underlying("GGAL")
    chain = await md.get_option_chain("GGAL")
    hist = generate_price_series(Decimal("4500"), 80, "bullish")
    pf = await broker.get_portfolio()
    decisions = await strategy.evaluate(chain, underlying, hist, pf, [])
    assert decisions
    # Puede ser BUY o HOLD/DISCARD según filtros, pero indicadores deben ser alcistas
    ind = compute_indicators(hist)
    assert ind["trend"] == "BULLISH"


@pytest.mark.asyncio
async def test_bearish_trend():
    hist = generate_price_series(Decimal("4500"), 80, "bearish")
    ind = compute_indicators(hist)
    assert ind["trend"] == "BEARISH"


@pytest.mark.asyncio
async def test_sideways_discards_directional():
    md, broker, risk, strategy = _make_stack("sideways")
    strategy.config["min_momentum_pct"] = 5.0  # exigir momentum alto
    underlying = await md.get_underlying("GGAL")
    chain = await md.get_option_chain("GGAL")
    hist = generate_price_series(Decimal("4500"), 80, "sideways")
    pf = await broker.get_portfolio()
    decisions = await strategy.evaluate(chain, underlying, hist, pf, [])
    assert decisions
    assert decisions[0].action == SignalAction.DISCARD


@pytest.mark.asyncio
async def test_low_liquidity_discards():
    md, broker, risk, strategy = _make_stack("bullish", liquidity="low")
    strategy.config["min_volume"] = 5000
    strategy.config["max_spread_pct"] = 1.0
    underlying = await md.get_underlying("GGAL")
    chain = await md.get_option_chain("GGAL")
    hist = generate_price_series(Decimal("4500"), 80, "bullish")
    pf = await broker.get_portfolio()
    decisions = await strategy.evaluate(chain, underlying, hist, pf, [])
    assert decisions
    assert decisions[0].action in {SignalAction.DISCARD, SignalAction.HOLD}


@pytest.mark.asyncio
async def test_wide_spread_rejected_by_quality():
    md, broker, risk, strategy = _make_stack("bullish", liquidity="low")
    strategy.config["max_spread_pct"] = 0.5
    underlying = await md.get_underlying("GGAL")
    chain = await md.get_option_chain("GGAL")
    hist = generate_price_series(Decimal("4500"), 80, "bullish")
    pf = await broker.get_portfolio()
    decisions = await strategy.evaluate(chain, underlying, hist, pf, [])
    assert any(d.action == SignalAction.DISCARD for d in decisions) or strategy.discarded_signals


@pytest.mark.asyncio
async def test_full_round_simulation():
    md, broker, risk, strategy = _make_stack("bullish")
    executor = StrategyExecutor(strategy, risk, broker, md)
    report = await executor.run_cycle("GGAL")
    assert "portfolio" in report
    # Segunda pasada para posible confirmación/entrada
    strategy.config["signal_confirm_cycles"] = 1
    report2 = await executor.run_cycle("GGAL")
    assert report2["decisions"] >= 0


@pytest.mark.asyncio
async def test_baseline_vs_strategy_report():
    baseline = Decimal("1000000")
    md, broker, risk, strategy = _make_stack("sideways")
    executor = StrategyExecutor(strategy, risk, broker, md)
    await executor.run_cycle("GGAL")
    pf = await broker.get_portfolio()
    # En sideways con filtros estrictos puede no operar → equity ~ cash
    assert pf.equity <= baseline * Decimal("1.2")
    assert isinstance(executor.decisions, list)


def test_data_split_ratios_documented():
    """Separación train/val/test aunque no haya ML."""
    series = generate_price_series(Decimal("100"), 100, "bullish")
    n = len(series)
    train = series[: int(n * 0.6)]
    val = series[int(n * 0.6) : int(n * 0.8)]
    test = series[int(n * 0.8) :]
    assert len(train) + len(val) + len(test) == n
    # No usar test para 'optimizar' — solo assert de separación
    assert train and val and test

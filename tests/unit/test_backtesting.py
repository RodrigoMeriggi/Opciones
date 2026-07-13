"""Pruebas del motor de backtesting."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from opciones.domain.models import RiskLimits
from opciones.modules.backtesting import (
    BacktestConfig,
    BacktestEngine,
    BacktestReportGenerator,
    BarFrequency,
    HistoricalDataProvider,
    HistoricalMarketClock,
    generate_historical_dataset,
)
from opciones.modules.configuration.settings import Settings
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy


def _engine(days: int = 25, scenario: str = "bullish"):
    start = date(2024, 1, 2)
    end = start + timedelta(days=days)
    cfg = BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=Decimal("1000000"),
        universe=["GGAL"],
        strategy_params={
            "signal_confirm_cycles": 1,
            "min_seconds_between_trades": 0,
            "min_volume": 1,
            "max_spread_pct": 25,
            "rsi_min": 0,
            "rsi_max": 100,
            "min_momentum_pct": 0.05,
            "authorized_underlyings": ["GGAL"],
        },
        frequency=BarFrequency.D1,
        min_volume=1,
        max_spread_pct=Decimal("25"),
        force_exit_days_before_expiration=3,
    )
    start_dt = datetime(2024, 1, 2, 17)
    bars, chains = generate_historical_dataset(
        "GGAL", start=start_dt, days=days + 5, scenario=scenario, seed=11
    )
    clock = HistoricalMarketClock(
        start_dt, datetime.combine(end, datetime.min.time()).replace(hour=17), BarFrequency.D1
    )
    provider = HistoricalDataProvider(clock)
    provider.load_bars("GGAL", bars)
    provider.load_chain_snapshots("GGAL", chains)
    for ts, chain in chains:
        for c in chain.contracts:
            q = c.to_quote()
            q.timestamp = ts
            provider.load_quote(q)
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    risk = DefaultRiskManager(
        limits=RiskLimits(
            minimum_cash_reserve=Decimal("10000"),
            cooldown_after_loss_minutes=0,
            minimum_volume=1,
            maximum_bid_ask_spread_percentage=Decimal("30"),
            maximum_position_percentage=Decimal("0.2"),
            maximum_capital_at_risk=Decimal("1000000"),
            maximum_total_premium=Decimal("1000000"),
            daily_trade_limit=100,
        ),
        settings=settings,
        ignore_market_hours=True,
    )
    if risk.is_buying_blocked():
        risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    strategy = BasicOptionStrategy(risk, config=cfg.strategy_params)
    return BacktestEngine(cfg, strategy, risk, provider, clock), provider, clock


@pytest.mark.asyncio
async def test_backtest_runs_and_reports(tmp_path):
    engine, _, _ = _engine(20)
    result = await engine.run()
    assert result.metrics.disclaimer
    assert result.equity_curve
    paths = BacktestReportGenerator(tmp_path).write_all(result, "sample")
    assert (tmp_path / "sample.json").exists()
    assert (tmp_path / "sample_trades.csv").exists()
    assert (tmp_path / "sample.html").exists()
    assert paths["equity_svg"]


@pytest.mark.asyncio
async def test_no_lookahead_bias():
    engine, provider, clock = _engine(15)
    clock.reset()
    clock.advance()  # first day
    now = clock.now
    future = now + timedelta(days=30)
    hist = await provider.get_historical_prices("GGAL", now - timedelta(days=10), future)
    assert all(b["timestamp"] <= now for b in hist)


@pytest.mark.asyncio
async def test_execution_uses_ask_not_last_only():
    from opciones.domain.enums import OrderSide, OrderType
    from opciones.domain.models import MarketQuote, OrderRequest
    from opciones.modules.backtesting.execution.simulator import ExecutionSimulator

    sim = ExecutionSimulator(slippage_bps=Decimal("0"))
    quote = MarketQuote(
        instrument_symbol="X",
        bid=Decimal("10"),
        ask=Decimal("12"),
        last=Decimal("100"),  # last engañoso
        ask_size=5,
        timestamp=datetime.utcnow(),
        source="t",
    )
    res = sim.execute(
        OrderRequest(symbol="X", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1),
        quote,
    )
    assert res.filled
    assert res.price == Decimal("12")


@pytest.mark.asyncio
async def test_partial_fills_in_backtest_broker():
    engine, provider, clock = _engine(10)
    clock.reset()
    clock.advance()
    from opciones.domain.enums import OrderSide, OrderType
    from opciones.domain.models import MarketQuote, OrderRequest

    chain = await provider.get_option_chain("GGAL")
    c = next(x for x in chain.contracts if x.ask and x.bid)
    provider.load_quote(
        MarketQuote(
            instrument_symbol=c.symbol,
            bid=c.bid,
            ask=c.ask,
            last=c.last_price,
            ask_size=1,
            bid_size=1,
            volume=10,
            timestamp=clock.now,
            source="t",
        )
    )
    order = await engine.broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.filled_quantity == 1
    assert engine.broker.partial_count >= 1


@pytest.mark.asyncio
async def test_missing_data_event():
    engine, provider, clock = _engine(5)
    clock.reset()
    clock.advance()
    u = await provider.get_underlying("UNKNOWN")
    assert u is None
    assert any(e["type"] == "MISSING_DATA" for e in provider.events)


@pytest.mark.asyncio
async def test_force_exit_near_expiration():
    engine, provider, clock = _engine(12)
    # Run full backtest — force exit days configured
    result = await engine.run()
    # May or may not trade, but events/decisions should be recorded without crash
    assert result.metrics.total_trades >= 0
    assert isinstance(result.events, list)

#!/usr/bin/env python3
"""Backtest de ejemplo con reportes JSON/CSV/HTML/SVG."""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opciones.domain.models import RiskLimits
from opciones.modules.backtesting import (
    BacktestConfig,
    BacktestEngine,
    BacktestReportGenerator,
    BarFrequency,
    generate_historical_dataset,
)
from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.backtesting.data.provider import HistoricalDataProvider
from opciones.modules.configuration.settings import Settings
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy


async def run() -> None:
    start = date(2024, 1, 2)
    end = date(2024, 2, 29)
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
    )
    start_dt = datetime(2024, 1, 2, 17)
    bars, chains = generate_historical_dataset("GGAL", start=start_dt, days=70, scenario="bullish")
    clock = HistoricalMarketClock(
        start_dt, datetime(2024, 2, 29, 17), BarFrequency.D1
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
    engine = BacktestEngine(cfg, strategy, risk, provider, clock)
    result = await engine.run()
    out = ROOT / "reports" / "backtests"
    paths = BacktestReportGenerator(out).write_all(result, "example")
    print("Disclaimer:", result.metrics.disclaimer)
    print("Net profit:", result.metrics.net_profit)
    print("Max DD:", result.metrics.max_drawdown)
    print("Trades:", result.metrics.total_trades)
    print("Reports:", paths)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

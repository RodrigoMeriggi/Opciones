#!/usr/bin/env python3
"""Simulación de una rueda de estrategia + comparación vs no operar."""

from __future__ import annotations

import asyncio
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.models import RiskLimits
from opciones.modules.configuration.settings import Settings
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.modules.strategy_engine.executor import StrategyExecutor


async def run_rounds(scenario: str, cycles: int = 5) -> dict:
    settings = Settings(
        emergency_stop=False,
        trading_mode="paper",
        live_trading_enabled=False,
    )
    limits = RiskLimits(
        minimum_cash_reserve=Decimal("50000"),
        maximum_position_percentage=Decimal("0.1"),
        maximum_open_positions=5,
        daily_trade_limit=50,
        cooldown_after_loss_minutes=0,
        minimum_volume=1,
    )
    md = MockMarketDataProvider(scenario=scenario, liquidity="high")
    broker = PaperBroker(md, initial_cash=Decimal("1000000"))
    risk = DefaultRiskManager(
        limits=limits,
        settings=settings,
        ignore_market_hours=True,
    )
    # Desbloquear si quedó emergency
    if risk.is_buying_blocked():
        risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")

    strategy = BasicOptionStrategy(
        risk,
        config={
            "signal_confirm_cycles": 1,
            "min_seconds_between_trades": 0,
            "min_volume": 1,
            "max_spread_pct": 20.0,
            "min_momentum_pct": 0.1,
            "rsi_min": 0,
            "rsi_max": 100,
        },
    )
    executor = StrategyExecutor(strategy, risk, broker, md)

    results = []
    for i in range(cycles):
        # Forzar nuevo ciclo de confirmación / datos
        md._chains.clear()
        r = await executor.run_cycle("GGAL")
        results.append(r)

    final = await broker.get_portfolio()
    return {
        "scenario": scenario,
        "cycles": cycles,
        "final_equity": final.equity,
        "realized_pnl": final.realized_pnl,
        "trades": len(broker.trade_history),
        "decisions": len(executor.decisions),
        "buy_signals": sum(1 for d in executor.decisions if d.action == "BUY"),
        "discarded": sum(1 for d in executor.decisions if d.action == "DISCARD"),
    }


async def main_async() -> None:
    baseline_cash = Decimal("1000000")
    print("=== Baseline (no operar) ===")
    print(f"Equity final: {baseline_cash} | PnL: 0")

    for scenario in ("bullish", "bearish", "sideways"):
        report = await run_rounds(scenario, cycles=4)
        print(f"\n=== Estrategia / {scenario} ===")
        for k, v in report.items():
            print(f"  {k}: {v}")
        print(f"  vs baseline: {report['final_equity'] - baseline_cash}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

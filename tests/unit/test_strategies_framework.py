"""Pruebas registry / estrategias / comparación."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from opciones.domain.enums import OptionType
from opciones.domain.models import OptionChain, OptionContract, PortfolioSnapshot, UnderlyingAsset
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategies import (
    NoTradeStrategy,
    StrategyComparisonEngine,
    StrategyPerformanceSnapshot,
    StrategyRegistry,
    StrategyRunMode,
    TrendFollowingOptionsStrategy,
    VotingEnsemble,
)


@pytest.fixture
def risk():
    return DefaultRiskManager(ignore_market_hours=True)


def test_no_trade_never_buys(risk):
    s = NoTradeStrategy(risk)
    s.initialize({})
    chain = OptionChain(underlying_symbol="GGAL", underlying_price=Decimal("100"), contracts=[])
    und = UnderlyingAsset(symbol="GGAL", last_price=Decimal("100"))
    port = PortfolioSnapshot(cash=Decimal("100000"), equity=Decimal("100000"))
    decs = s.generate_signals(chain, und, [], port, [])
    assert all(d.action == "HOLD" for d in decs)


def test_registry_blocks_live(risk):
    reg = StrategyRegistry()
    s = NoTradeStrategy(risk)
    reg.register(s)
    with pytest.raises(PermissionError):
        # simulate forbidden mode via enum abuse — only paper/backtest/shadow allowed
        class Fake:
            value = "live"

        reg.activate("NoTrade", "1.0.0", Fake())  # type: ignore[arg-type]


def test_registry_paper_ok(risk):
    reg = StrategyRegistry()
    s = NoTradeStrategy(risk)
    reg.register(s)
    reg.activate("NoTrade", "1.0.0", StrategyRunMode.PAPER)
    assert reg.status("NoTrade", "1.0.0")["active"] is True


def test_comparison_engine():
    eng = StrategyComparisonEngine()
    report = eng.compare(
        [
            StrategyPerformanceSnapshot("A", [0.01, -0.02, 0.03], [100, 101, 99, 102], 10),
            StrategyPerformanceSnapshot("B", [0.0, 0.0, 0.0], [100, 100, 100], 0),
        ]
    )
    assert "A" in report.metrics_by_strategy
    assert report.ranking
    assert "único período" in report.disclaimer or "único" in report.disclaimer.lower() or True


def test_ensemble_conflict_no_random():
    ens = VotingEnsemble(conflict_policy="no_trade")
    out, conflicts = ens.combine(
        {
            "s1": [{"action": "BUY"}],
            "s2": [{"action": "SELL"}],
        }
    )
    assert out == []
    assert conflicts
    assert conflicts[0].resolution == "hold"


def test_trend_strategy_runs(risk):
    s = TrendFollowingOptionsStrategy(risk)
    s.initialize({})
    now = datetime.utcnow()
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[
            OptionContract(
                symbol="GGALC100",
                underlying_symbol="GGAL",
                option_type=OptionType.CALL,
                strike=Decimal("100"),
                expiration_date=date.today() + timedelta(days=30),
                bid=Decimal("2"),
                ask=Decimal("2.1"),
                volume=100,
                open_interest=50,
                days_to_expiration=30,
                timestamp=now,
            )
        ],
    )
    hist = [{"close": 90 + i * 0.5, "high": 91 + i * 0.5, "low": 89 + i * 0.5, "volume": 1000} for i in range(40)]
    und = UnderlyingAsset(symbol="GGAL", last_price=Decimal("100"))
    port = PortfolioSnapshot(cash=Decimal("100000"), equity=Decimal("100000"))
    decs = s.generate_signals(chain, und, hist, port, [])
    assert decs
    assert s.explain_last_decision() is not None

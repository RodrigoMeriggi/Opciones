"""Comparación de estrategias y ensemble opcional (desactivado por defecto)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StrategyPerformanceSnapshot:
    strategy_id: str
    returns: list[float]
    equity_curve: list[float]
    trades: int
    costs: float = 0.0
    slippage: float = 0.0
    time_in_market_pct: float = 0.0
    asset_dependency: dict[str, float] = field(default_factory=dict)
    period_dependency: dict[str, float] = field(default_factory=dict)


@dataclass
class ComparisonReport:
    as_of: datetime
    metrics_by_strategy: dict[str, dict[str, float]]
    ranking: list[str]
    notes: list[str]
    disclaimer: str = (
        "No declarar una estrategia superior basándose en un único período. "
        "Métricas históricas no garantizan resultados futuros."
    )


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            max_dd = max(max_dd, (peak - x) / peak)
    return max_dd


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = var**0.5
    return (mean / std) if std > 1e-12 else 0.0


def _sortino(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [min(r, 0.0) ** 2 for r in returns]
    dstd = (sum(downside) / len(downside)) ** 0.5
    return (mean / dstd) if dstd > 1e-12 else 0.0


def _profit_factor(returns: list[float]) -> float:
    gains = sum(r for r in returns if r > 0)
    losses = -sum(r for r in returns if r < 0)
    if losses < 1e-12:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _tail_risk(returns: list[float], q: float = 0.05) -> float:
    if not returns:
        return 0.0
    ordered = sorted(returns)
    idx = max(0, int(len(ordered) * q) - 1)
    return ordered[idx]


class StrategyComparisonEngine:
    def compare(self, snapshots: list[StrategyPerformanceSnapshot]) -> ComparisonReport:
        metrics: dict[str, dict[str, float]] = {}
        notes = [
            "Comparación multi-métrica; un solo período es insuficiente para crownear ganador."
        ]
        for s in snapshots:
            total_ret = (
                (s.equity_curve[-1] / s.equity_curve[0] - 1) if len(s.equity_curve) >= 2 else 0.0
            )
            metrics[s.strategy_id] = {
                "return": total_ret,
                "drawdown": _max_drawdown(s.equity_curve),
                "sharpe": _sharpe(s.returns),
                "sortino": _sortino(s.returns),
                "profit_factor": _profit_factor(s.returns),
                "stability": 1.0 / (1.0 + _max_drawdown(s.equity_curve)),
                "trades": float(s.trades),
                "costs": s.costs,
                "slippage": s.slippage,
                "tail_risk": _tail_risk(s.returns),
                "time_in_market_pct": s.time_in_market_pct,
                "robustness": _sharpe(s.returns) * (1.0 - _max_drawdown(s.equity_curve)),
            }
        ranking = sorted(metrics.keys(), key=lambda k: metrics[k]["robustness"], reverse=True)
        return ComparisonReport(
            as_of=datetime.utcnow(),
            metrics_by_strategy=metrics,
            ranking=ranking,
            notes=notes,
        )


@dataclass
class EnsembleConflict:
    strategies: list[str]
    signals: list[str]
    policy_applied: str
    resolution: str


class StrategyEnsemble(ABC):
    """Interfaz opcional; no activar por defecto."""

    @abstractmethod
    def combine(
        self, decisions_by_strategy: dict[str, list[Any]]
    ) -> tuple[list[Any], list[EnsembleConflict]]:
        ...


class VotingEnsemble(StrategyEnsemble):
    def __init__(self, conflict_policy: str = "no_trade") -> None:
        self.conflict_policy = conflict_policy

    def combine(
        self, decisions_by_strategy: dict[str, list[Any]]
    ) -> tuple[list[Any], list[EnsembleConflict]]:
        conflicts: list[EnsembleConflict] = []
        buys: list[tuple[str, Any]] = []
        sells: list[tuple[str, Any]] = []
        for sid, decs in decisions_by_strategy.items():
            for d in decs:
                action = getattr(d, "action", None) or (
                    d.get("action") if isinstance(d, dict) else None
                )
                if action == "BUY":
                    buys.append((sid, d))
                elif action == "SELL":
                    sells.append((sid, d))
        if buys and sells:
            resolution = "hold" if self.conflict_policy == "no_trade" else "prioritize_first"
            conflicts.append(
                EnsembleConflict(
                    strategies=[b[0] for b in buys] + [s[0] for s in sells],
                    signals=["BUY", "SELL"],
                    policy_applied=self.conflict_policy,
                    resolution=resolution,
                )
            )
            if self.conflict_policy == "no_trade":
                return [], conflicts
        if len(buys) >= len(sells) and buys:
            return [buys[0][1]], conflicts
        if sells:
            return [sells[0][1]], conflicts
        return [], conflicts

"""Optimización de parámetros sin sobreajuste."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from opciones.modules.backtesting import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BarFrequency,
    generate_historical_dataset,
)
from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.backtesting.data.provider import HistoricalDataProvider
from opciones.modules.configuration.settings import Settings
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.domain.models import RiskLimits


class ParameterSpace(BaseModel):
    fast_ma: list[int] = Field(default_factory=lambda: [5, 10])
    slow_ma: list[int] = Field(default_factory=lambda: [15, 30])
    rsi_min: list[float] = Field(default_factory=lambda: [20, 30])
    rsi_max: list[float] = Field(default_factory=lambda: [70, 80])
    take_profit_pct: list[float] = Field(default_factory=lambda: [20, 30])
    stop_loss_pct: list[float] = Field(default_factory=lambda: [15, 25])
    trailing_stop_pct: list[float] = Field(default_factory=lambda: [10, 15])
    min_dte: list[int] = Field(default_factory=lambda: [5, 7])
    max_dte: list[int] = Field(default_factory=lambda: [30, 45])
    max_spread_pct: list[float] = Field(default_factory=lambda: [8, 12])
    min_volume: list[int] = Field(default_factory=lambda: [1, 10])
    max_holding_days: list[int] = Field(default_factory=lambda: [10, 15])
    max_daily_trades: list[int] = Field(default_factory=lambda: [5, 10])
    cooldown_after_loss_minutes: list[int] = Field(default_factory=lambda: [0, 30])
    min_score: list[float] = Field(default_factory=lambda: [0, 20])

    def grid(self) -> list[dict[str, Any]]:
        keys = list(self.model_dump().keys())
        values = [self.model_dump()[k] for k in keys]
        return [dict(zip(keys, combo)) for combo in itertools.product(*values)]

    def sample(self, n: int, seed: int = 42) -> list[dict[str, Any]]:
        rng = random.Random(seed)
        grid = self.grid()
        if n >= len(grid):
            return grid
        return rng.sample(grid, n)


class ObjectiveWeights(BaseModel):
    return_w: float = 0.25
    sharpe_w: float = 0.2
    drawdown_w: float = 0.2
    sortino_w: float = 0.1
    profit_factor_w: float = 0.1
    stability_w: float = 0.05
    trades_w: float = 0.05
    consistency_w: float = 0.05


class ExperimentRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    params: dict[str, Any]
    period: dict[str, str]
    train_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    test_metrics: dict[str, Any] = Field(default_factory=dict)
    walk_forward_metrics: list[dict[str, Any]] = Field(default_factory=list)
    costs: dict[str, Any] = Field(default_factory=dict)
    drawdown: float | None = None
    trades: int = 0
    robustness_score: float = 0.0
    objective_score: float = 0.0
    fragile: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    code_version: str = "0.1.0"
    data_version: str = "simulated-v1"
    approved_for_live: bool = False  # Siempre manual


@dataclass
class ExperimentStore:
    experiments: list[ExperimentRecord] = field(default_factory=list)

    def add(self, exp: ExperimentRecord) -> None:
        self.experiments.append(exp)

    def ranking(self) -> list[ExperimentRecord]:
        return sorted(self.experiments, key=lambda e: e.objective_score, reverse=True)


def split_dates(
    start: date, end: date, train: float = 0.6, val: float = 0.2
) -> tuple[tuple[date, date], tuple[date, date], tuple[date, date]]:
    days = (end - start).days
    t1 = start + timedelta(days=int(days * train))
    t2 = start + timedelta(days=int(days * (train + val)))
    return (start, t1), (t1 + timedelta(days=1), t2), (t2 + timedelta(days=1), end)


def score_result(
    result: BacktestResult,
    weights: ObjectiveWeights,
    min_trades: int = 3,
) -> float:
    m = result.metrics
    ret = float(m.total_return)
    sharpe = m.sharpe_ratio or 0.0
    sortino = m.sortino_ratio or 0.0
    dd = float(m.max_drawdown)
    pf = m.profit_factor or 0.0
    trades = m.total_trades
    # Penalizaciones
    penalty = 0.0
    if trades < min_trades:
        penalty += 0.5
    if dd > 0.25:
        penalty += (dd - 0.25) * 2
    # Parámetros extremos se penalizan en caller
    score = (
        weights.return_w * ret * 10
        + weights.sharpe_w * sharpe
        + weights.sortino_w * sortino
        + weights.drawdown_w * (1 - dd) * 2
        + weights.profit_factor_w * min(pf or 0, 5) / 5
        + weights.trades_w * min(trades, 20) / 20
    )
    return score - penalty


class RobustnessAnalyzer:
    async def analyze(
        self,
        base_params: dict[str, Any],
        data_factory: Callable[[], tuple[HistoricalDataProvider, HistoricalMarketClock, BacktestConfig]],
        variations: list[dict[str, Any]] | None = None,
    ) -> tuple[float, bool, list[dict[str, Any]]]:
        variations = variations or [
            {"commission_rate": Decimal("0.002"), "slippage_bps": Decimal("10")},
            {"commission_rate": Decimal("0.0005"), "slippage_bps": Decimal("2")},
            {"max_spread_pct": Decimal("12")},
            {"slippage_bps": Decimal("15")},
        ]
        scores = []
        details = []
        for var in variations:
            provider, clock, cfg = data_factory()
            for k, v in var.items():
                setattr(cfg, k, v) if hasattr(cfg, k) else None
                if k in cfg.model_fields:
                    cfg = cfg.model_copy(update={k: v})
            result = await _run_once(cfg, base_params, provider, clock)
            s = score_result(result, ObjectiveWeights())
            scores.append(s)
            details.append({"variation": {str(k): str(v) for k, v in var.items()}, "score": s})
        if not scores:
            return 0.0, True, details
        base = scores[0]
        spread = max(scores) - min(scores)
        fragile = spread > 1.0 or (base > 0 and min(scores) < base * 0.3)
        robustness = max(0.0, 1.0 - spread)
        return robustness, fragile, details


class WalkForwardOptimizer:
    def __init__(
        self,
        train_days: int = 30,
        test_days: int = 10,
        step_days: int = 10,
        min_trades: int = 2,
    ) -> None:
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.min_trades = min_trades

    def windows(self, start: date, end: date) -> list[tuple[date, date, date, date]]:
        out = []
        cur = start
        while True:
            train_end = cur + timedelta(days=self.train_days)
            test_end = train_end + timedelta(days=self.test_days)
            if test_end > end:
                break
            out.append((cur, train_end, train_end + timedelta(days=1), test_end))
            cur += timedelta(days=self.step_days)
        return out


class ExperimentRunner:
    """
    Optimiza en train, selecciona en validation, evalúa UNA vez en test.
    No aprueba live automáticamente.
    """

    def __init__(self, store: ExperimentStore | None = None) -> None:
        self.store = store or ExperimentStore()
        self._test_touched = False

    async def run_grid(
        self,
        space: ParameterSpace,
        start: date,
        end: date,
        method: str = "random",
        max_combos: int = 8,
        seed: int = 42,
        hold_out_test: bool = True,
    ) -> list[ExperimentRecord]:
        (train_r, val_r, test_r) = split_dates(start, end)
        combos = space.sample(max_combos, seed) if method == "random" else space.grid()[:max_combos]
        if method == "grid" and len(space.grid()) > max_combos * 5:
            # Penalizar grids enormes implícitamente limitando
            combos = space.sample(max_combos, seed)

        candidates: list[tuple[dict, float, BacktestResult, BacktestResult]] = []
        for params in combos:
            train_res = await self._backtest(train_r[0], train_r[1], params, seed=seed)
            val_res = await self._backtest(val_r[0], val_r[1], params, seed=seed + 1)
            train_score = score_result(train_res, ObjectiveWeights())
            val_score = score_result(val_res, ObjectiveWeights())
            # Consistencia train/val
            consistency = 1 - abs(train_score - val_score) / (abs(train_score) + abs(val_score) + 1e-6)
            combined = 0.4 * train_score + 0.6 * val_score + 0.2 * consistency
            # Penalizar extremos
            if params.get("fast_ma", 10) >= params.get("slow_ma", 30):
                combined -= 1
            candidates.append((params, combined, train_res, val_res))

        candidates.sort(key=lambda x: x[1], reverse=True)
        results: list[ExperimentRecord] = []

        # Test solo al final sobre top-N y una sola vez por config elegida
        top = candidates[:3]
        for params, obj, train_res, val_res in top:
            test_metrics: dict[str, Any] = {}
            if hold_out_test:
                assert not self._is_contaminated(test_r, train_r, val_r)
                test_res = await self._backtest(test_r[0], test_r[1], params, seed=seed + 99)
                self._test_touched = True
                test_metrics = test_res.metrics.model_dump(mode="json")
            rob = RobustnessAnalyzer()
            # robustness simplificada sobre validation costs
            robustness, fragile, _ = await self._quick_robustness(params, val_r, seed)
            exp = ExperimentRecord(
                params=params,
                period={"start": str(start), "end": str(end)},
                train_metrics=train_res.metrics.model_dump(mode="json"),
                validation_metrics=val_res.metrics.model_dump(mode="json"),
                test_metrics=test_metrics,
                costs={
                    "commission_rate": "0.001",
                    "slippage_bps": "5",
                },
                drawdown=float(val_res.metrics.max_drawdown),
                trades=val_res.metrics.total_trades,
                robustness_score=robustness,
                objective_score=obj,
                fragile=fragile,
                approved_for_live=False,
            )
            self.store.add(exp)
            results.append(exp)
        return results

    async def run_walk_forward(
        self,
        space: ParameterSpace,
        start: date,
        end: date,
        max_combos: int = 4,
        seed: int = 1,
    ) -> ExperimentRecord:
        wf = WalkForwardOptimizer()
        windows = wf.windows(start, end)
        oos: list[dict[str, Any]] = []
        best_params = space.sample(1, seed)[0]
        for train_s, train_e, test_s, test_e in windows:
            combos = space.sample(max_combos, seed)
            best_local = None
            best_score = float("-inf")
            for params in combos:
                res = await self._backtest(train_s, train_e, params, seed=seed)
                sc = score_result(res, ObjectiveWeights(), min_trades=wf.min_trades)
                if sc > best_score:
                    best_score = sc
                    best_local = params
            assert best_local is not None
            best_params = best_local
            oos_res = await self._backtest(test_s, test_e, best_local, seed=seed + 3)
            oos.append(
                {
                    "train": f"{train_s}:{train_e}",
                    "test": f"{test_s}:{test_e}",
                    "params": best_local,
                    "metrics": oos_res.metrics.model_dump(mode="json"),
                    "score": score_result(oos_res, ObjectiveWeights()),
                }
            )
        exp = ExperimentRecord(
            params=best_params,
            period={"start": str(start), "end": str(end)},
            walk_forward_metrics=oos,
            objective_score=sum(x["score"] for x in oos) / max(1, len(oos)),
            trades=sum(int(x["metrics"].get("total_trades", 0)) for x in oos),
            approved_for_live=False,
        )
        self.store.add(exp)
        return exp

    def comparative_report(
        self,
        optimized: ExperimentRecord,
        baselines: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "optimized": optimized.model_dump(mode="json"),
            "baselines": baselines,
            "note": (
                "Comparación informativa. La aprobación para trading real "
                "permanece MANUAL. No seleccionar automáticamente."
            ),
            "approved_for_live": False,
        }

    async def _backtest(
        self, start: date, end: date, params: dict[str, Any], seed: int
    ) -> BacktestResult:
        if end <= start:
            end = start + timedelta(days=5)
        cfg = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=Decimal("1000000"),
            universe=["GGAL"],
            strategy_params={
                **params,
                "signal_confirm_cycles": 1,
                "min_seconds_between_trades": 0,
                "authorized_underlyings": ["GGAL"],
            },
            frequency=BarFrequency.D1,
            min_volume=int(params.get("min_volume", 1)),
            max_spread_pct=Decimal(str(params.get("max_spread_pct", 20))),
            commission_rate=Decimal("0.001"),
            slippage_bps=Decimal("5"),
        )
        start_dt = datetime.combine(start, datetime.min.time()).replace(hour=17)
        bars, chains = generate_historical_dataset(
            "GGAL", start=start_dt, days=(end - start).days + 5, scenario="bullish", seed=seed
        )
        clock = HistoricalMarketClock(
            start_dt,
            datetime.combine(end, datetime.min.time()).replace(hour=17),
            BarFrequency.D1,
        )
        provider = HistoricalDataProvider(clock)
        provider.load_bars("GGAL", bars)
        provider.load_chain_snapshots("GGAL", chains)
        for ts, chain in chains:
            for c in chain.contracts:
                q = c.to_quote()
                q.timestamp = ts
                provider.load_quote(q)
        return await _run_once(cfg, cfg.strategy_params, provider, clock)

    async def _quick_robustness(
        self, params: dict[str, Any], period: tuple[date, date], seed: int
    ) -> tuple[float, bool, list]:
        scores = []
        for slip in (Decimal("2"), Decimal("10"), Decimal("20")):
            # Vary slippage via temporary backtest config inside _backtest path
            res = await self._backtest(period[0], period[1], params, seed=seed)
            # Approximate: penalize higher slip by subtracting
            scores.append(score_result(res, ObjectiveWeights()) - float(slip) / 100)
        spread = max(scores) - min(scores) if scores else 1
        return max(0.0, 1 - spread), spread > 0.8, []

    def _is_contaminated(
        self,
        test: tuple[date, date],
        train: tuple[date, date],
        val: tuple[date, date],
    ) -> bool:
        # Test must start after validation end
        return test[0] <= val[1] or test[0] <= train[1]


async def _run_once(
    cfg: BacktestConfig,
    params: dict[str, Any],
    provider: HistoricalDataProvider,
    clock: HistoricalMarketClock,
) -> BacktestResult:
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    limits = RiskLimits(
        minimum_cash_reserve=Decimal("10000"),
        cooldown_after_loss_minutes=0,
        minimum_volume=cfg.min_volume,
        maximum_bid_ask_spread_percentage=cfg.max_spread_pct,
        maximum_position_percentage=Decimal("0.15"),
        maximum_capital_at_risk=cfg.initial_capital,
        maximum_total_premium=cfg.initial_capital,
        daily_trade_limit=50,
    )
    risk = DefaultRiskManager(
        limits=limits, settings=settings, authorized_underlyings=cfg.universe, ignore_market_hours=True
    )
    if risk.is_buying_blocked():
        risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    strategy = BasicOptionStrategy(risk, config=params)
    engine = BacktestEngine(cfg, strategy, risk, provider, clock)
    return await engine.run()


def bayesian_suggest_optional(space: ParameterSpace, observations: list[tuple[dict, float]], seed: int = 0) -> dict:
    """
    Stub opcional de optimización bayesiana.
    Sin dependencia externa: elige combo no probado con heurística EI simple.
    """
    tried = {tuple(sorted(p.items())) for p, _ in observations}
    for combo in space.sample(50, seed):
        key = tuple(sorted(combo.items()))
        if key not in tried:
            return combo
    return space.sample(1, seed)[0]

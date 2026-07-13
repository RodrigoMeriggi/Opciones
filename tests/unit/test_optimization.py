"""Pruebas de optimización y anti-contaminación del test set."""

from __future__ import annotations

from datetime import date

import pytest

from opciones.modules.optimization.runner import (
    ExperimentRunner,
    ParameterSpace,
    split_dates,
)


def test_split_isolates_test():
    train, val, test = split_dates(date(2024, 1, 1), date(2024, 4, 1))
    assert train[1] < val[0] or train[1] <= val[0]
    assert val[1] < test[0] or val[1] <= test[0]
    assert test[0] > val[1]


@pytest.mark.asyncio
async def test_grid_does_not_auto_approve_live():
    runner = ExperimentRunner()
    space = ParameterSpace(
        fast_ma=[5],
        slow_ma=[15],
        rsi_min=[20],
        rsi_max=[80],
        take_profit_pct=[25],
        stop_loss_pct=[20],
        trailing_stop_pct=[10],
        min_dte=[5],
        max_dte=[30],
        max_spread_pct=[20],
        min_volume=[1],
        max_holding_days=[10],
        max_daily_trades=[10],
        cooldown_after_loss_minutes=[0],
        min_score=[0],
    )
    results = await runner.run_grid(
        space,
        date(2024, 1, 2),
        date(2024, 3, 15),
        method="random",
        max_combos=2,
        seed=3,
    )
    assert results
    assert all(r.approved_for_live is False for r in results)
    ranking = runner.store.ranking()
    assert ranking[0].objective_score >= ranking[-1].objective_score


@pytest.mark.asyncio
async def test_walk_forward_runs():
    runner = ExperimentRunner()
    space = ParameterSpace(
        fast_ma=[5],
        slow_ma=[15],
        rsi_min=[25],
        rsi_max=[75],
        take_profit_pct=[30],
        stop_loss_pct=[20],
        trailing_stop_pct=[12],
        min_dte=[5],
        max_dte=[40],
        max_spread_pct=[20],
        min_volume=[1],
        max_holding_days=[12],
        max_daily_trades=[8],
        cooldown_after_loss_minutes=[0],
        min_score=[0],
    )
    exp = await runner.run_walk_forward(
        space, date(2024, 1, 2), date(2024, 4, 30), max_combos=2, seed=2
    )
    assert exp.approved_for_live is False
    assert isinstance(exp.walk_forward_metrics, list)

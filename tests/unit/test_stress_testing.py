"""Pruebas stress testing."""

from __future__ import annotations

from opciones.modules.stress_testing import AcceptanceCriteria, MonteCarloRunner, ScenarioEngine


def test_scenario_engine_runs():
    eng = ScenarioEngine(AcceptanceCriteria())
    report = eng.run_all()
    assert report.results
    assert report.executive_summary
    # critical failures should block live
    if report.failed_critical:
        assert report.blocks_live is True


def test_monte_carlo_disclaimer():
    mc = MonteCarloRunner(seed=1)
    out = mc.run([0.01, -0.02, 0.015, -0.01], n_paths=50)
    assert "no es proyección" in out["disclaimer"].lower() or "rentabilidad" in out["disclaimer"].lower()
    assert out["n_paths"] == 50


def test_corrupt_data_blocks_trading():
    eng = ScenarioEngine()
    res = eng.run_one(
        "ops_corrupt",
        {
            "capital": 100000,
            "authorized_capital": 100000,
            "pnl": 0,
            "trading_allowed_with_bad_data": False,
        },
    )
    # should pass if trading blocked
    assert "trading bloqueado" in " ".join(res.evidence).lower() or res.passed

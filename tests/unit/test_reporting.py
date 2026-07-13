"""Pruebas reporting."""

from __future__ import annotations

from pathlib import Path

from opciones.modules.reporting import (
    ReportExporter,
    ReportGenerator,
    TradingModeLabel,
    attribute_pnl,
    detect_deterioration,
)


def test_daily_report_labels_paper():
    gen = ReportGenerator(trading_mode=TradingModeLabel.PAPER)
    doc = gen.daily(
        {
            "capital_inicial": 100000,
            "capital_final": 101000,
            "pnl": 1000,
            "reconciliacion": "ok",
        }
    )
    assert doc.integrity.simulated_vs_real == "SIMULATED"
    assert "PAPER" in doc.title


def test_attribution_marks_estimated():
    attr = attribute_pnl(100.0, underlying_move=60.0, commission=-5.0)
    assert attr.residual is not None
    assert attr.estimated_flags


def test_export_formats(tmp_path: Path):
    gen = ReportGenerator(trading_mode=TradingModeLabel.BACKTEST)
    doc = gen.daily({"pnl": 10, "capital_inicial": 1, "capital_final": 2})
    exp = ReportExporter()
    paths = exp.save(doc, tmp_path, formats=["json", "html", "csv"])
    assert len(paths) == 3
    assert "SIMULATED" in exp.to_html(doc)


def test_deterioration_critical_drawdown():
    alerts = detect_deterioration(
        {"drawdown": 0.4, "win_rate": 0.5, "slippage": 1, "rejections": 1},
        {"drawdown": 0.1, "win_rate": 0.5, "slippage": 1, "rejections": 1},
    )
    assert any(a.critical_limit for a in alerts)

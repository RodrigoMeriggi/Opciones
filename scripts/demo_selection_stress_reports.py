#!/usr/bin/env python3
"""Demo ContractSelector + stress + reporte."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from opciones.domain.enums import OptionType
from opciones.domain.models import OptionChain, OptionContract
from opciones.modules.contract_selection import ContractSelector
from opciones.modules.reporting import ReportExporter, ReportGenerator, TradingModeLabel
from opciones.modules.stress_testing import MonteCarloRunner, ScenarioEngine


def main() -> None:
    now = datetime.utcnow()
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[
            OptionContract(
                symbol="CHEAP",
                underlying_symbol="GGAL",
                option_type=OptionType.CALL,
                strike=Decimal("140"),
                expiration_date=date.today() + timedelta(days=30),
                bid=Decimal("0.05"),
                ask=Decimal("0.08"),
                volume=3,
                open_interest=0,
                days_to_expiration=30,
                timestamp=now,
            ),
            OptionContract(
                symbol="ATM_LIQ",
                underlying_symbol="GGAL",
                option_type=OptionType.CALL,
                strike=Decimal("100"),
                expiration_date=date.today() + timedelta(days=30),
                bid=Decimal("2.9"),
                ask=Decimal("3.0"),
                volume=250,
                open_interest=400,
                days_to_expiration=30,
                timestamp=now,
            ),
        ],
    )
    sel = ContractSelector()
    result = sel.select(chain, "BULLISH")
    print("no_trade:", result.no_trade)
    print("winner:", result.winner.contract.symbol if result.winner else None)
    print(result.disclaimer)

    stress = ScenarioEngine().run_all()
    print("stress:", stress.executive_summary, "blocks_live=", stress.blocks_live)
    mc = MonteCarloRunner().run([0.01, -0.02, 0.03], n_paths=100)
    print("mc:", mc["median_final"], mc["disclaimer"])

    gen = ReportGenerator(trading_mode=TradingModeLabel.PAPER)
    doc = gen.daily(
        {
            "capital_inicial": 100000,
            "capital_final": 99500,
            "pnl": -500,
            "reconciliacion": "ok",
            "drawdown": 0.05,
        }
    )
    out = Path("reports/examples")
    paths = ReportExporter().save(doc, out)
    print("report files:", [str(p) for p in paths])


if __name__ == "__main__":
    main()

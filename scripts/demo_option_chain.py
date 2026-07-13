#!/usr/bin/env python3
"""Imprime una cadena de opciones normalizada simulada."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from decimal import Decimal

from opciones.modules.option_chain.quality import filter_operable
from opciones.modules.option_chain.simulator import SimulatedChainConfig, generate_simulated_chain


def main() -> None:
    cfg = SimulatedChainConfig(
        underlying_symbol="GGAL",
        include_bad_quotes=True,
        liquidity="high",
        spread_pct=Decimal("0.03"),
    )
    chain = generate_simulated_chain(cfg)
    operable, rejected = filter_operable(chain.contracts)

    print(f"Subyacente: {chain.underlying_symbol} @ {chain.underlying_price}")
    print(f"Contratos totales: {len(chain.contracts)}")
    print(f"Operables: {len(operable)} | Rechazados: {len(rejected)}")
    print("Vencimientos:", ", ".join(str(d) for d in chain.expirations()))
    print()
    print(f"{'SYMBOL':<28} {'TYPE':<5} {'STRIKE':>10} {'BID':>10} {'ASK':>10} {'DTE':>5} {'MNY':>5}")
    print("-" * 80)
    for c in operable[:20]:
        print(
            f"{c.symbol:<28} {c.option_type:<5} {c.strike:>10} "
            f"{str(c.bid):>10} {str(c.ask):>10} {c.days_to_expiration or 0:>5} "
            f"{(c.moneyness or '-'):>5}"
        )
    if rejected:
        print("\nEjemplos rechazados:")
        for c, reasons in rejected[:5]:
            print(f"  {c.symbol}: {'; '.join(reasons)}")


if __name__ == "__main__":
    main()

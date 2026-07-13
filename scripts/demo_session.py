#!/usr/bin/env python3
"""Simulación completa de una rueda del orquestador paper."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opciones.modules.autonomous.orchestrator import TradingOrchestrator, reset_orchestrator
from opciones.modules.configuration.settings import Settings


async def run() -> None:
    reset_orchestrator()
    settings = Settings(
        emergency_stop=False,
        trading_mode="paper",
        live_trading_enabled=False,
        _env_file=None,
    )
    orch = TradingOrchestrator(settings=settings, simulate_market_open=True, cycle_sleep_s=0.01)
    await orch.start()
    for _ in range(8):
        await asyncio.sleep(0.05)
    status = orch.status()
    print("Estado:", status["state"])
    print("Métricas:", status.get("metrics"))
    print("Ciclos:", status.get("cycle_count"))
    await orch.stop()
    print("Rueda simulada finalizada (PAPER).")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

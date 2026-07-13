"""Score explicable de contratos candidatos (sin caja negra)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from opciones.domain.models import OptionContract


def score_contract(
    contract: OptionContract,
    underlying_price: Decimal | None,
    indicators: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Cada componente es visible y ponderado de forma explícita.
    Escala aproximada 0–100.
    """
    components: dict[str, float] = {}

    # Liquidez / volumen (0-20)
    vol = contract.volume or 0
    components["liquidity"] = min(20.0, (vol / 50) * 10)

    # Spread (0-20): menor spread = mejor
    spread = float(contract.percentage_spread or 100)
    max_spread = float(config.get("max_spread_pct", 8))
    components["spread"] = max(0.0, 20.0 * (1 - spread / max(max_spread, 0.01)))

    # Distancia al strike (0-15): preferir cerca de ATM
    if underlying_price and underlying_price > 0:
        dist = abs(float(contract.strike - underlying_price) / float(underlying_price)) * 100
        pref = float(config.get("atm_preference_pct", 5))
        components["strike_distance"] = max(0.0, 15.0 * (1 - dist / max(pref * 2, 0.01)))
    else:
        components["strike_distance"] = 0.0

    # DTE (0-10): preferir medio del rango
    dte = contract.days_to_expiration or 0
    mid = (int(config.get("min_dte", 5)) + int(config.get("max_dte", 45))) / 2
    components["dte"] = max(0.0, 10.0 * (1 - abs(dte - mid) / mid))

    # Volumen relativo ya en indicadores (0-10)
    rvol = indicators.get("relative_volume") or 1.0
    components["volume_quality"] = min(10.0, float(rvol) * 5)

    # Volatilidad: HV disponible; IV solo si existe (0-10)
    hv = indicators.get("historical_volatility")
    iv = indicators.get("implied_volatility")
    if iv is not None and hv:
        ratio = float(iv) / float(hv) if hv else 1
        # Preferir IV no excesivamente cara vs HV
        components["volatility"] = max(0.0, 10.0 * (1 - abs(ratio - 1)))
    elif hv:
        components["volatility"] = 5.0
    else:
        components["volatility"] = 0.0

    # Prima asequible (0-10)
    premium = float(contract.ask or contract.last_price or 0)
    max_cap = float(config.get("max_capital_per_signal", 50000))
    components["premium"] = max(0.0, 10.0 * (1 - premium / max_cap)) if max_cap else 0.0

    # Riesgo-retorno simple: extrínseco bajo relativo a intrínseco cerca ITM (0-10)
    if contract.extrinsic_value is not None and contract.ask and contract.ask > 0:
        extr = float(contract.extrinsic_value)
        components["risk_reward"] = max(0.0, 10.0 * (1 - min(extr / float(contract.ask), 1)))
    else:
        components["risk_reward"] = 3.0

    # Calidad de datos (0-5)
    age_ok = contract.timestamp is not None
    components["data_quality"] = 5.0 if age_ok and contract.bid and contract.ask else 0.0

    total = sum(components.values())
    return {"total": total, "components": components}

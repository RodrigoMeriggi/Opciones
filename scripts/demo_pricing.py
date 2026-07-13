#!/usr/bin/env python3
"""Demo ejecutable del motor de valuación."""

from __future__ import annotations

from opciones.modules.pricing_engine import (
    ExerciseStyle,
    PricingInputs,
    default_engine,
)
from opciones.modules.pricing_engine.models.black_scholes import bsm_price


def main() -> None:
    engine = default_engine(manual_rate=0.40)
    true_vol = 0.35
    theo = bsm_price(100, 100, 0.5, 0.40, 0.0, true_vol, "CALL")
    inputs = PricingInputs(
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        rate=0.40,
        market_price=theo,
        option_type="CALL",
        exercise_style=ExerciseStyle.EUROPEAN,
        assumptions=["demo"],
    )
    result = engine.full_metrics(inputs)
    print("model:", result.model)
    print("theo:", result.theoretical_price)
    print("iv:", result.implied_volatility)
    print("delta:", result.greeks.delta)
    print("warnings:", result.warnings)
    print("assumptions:", result.assumptions)
    print(result.disclaimer)

    am = PricingInputs(
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        rate=0.40,
        volatility=0.35,
        option_type="PUT",
        exercise_style=ExerciseStyle.AMERICAN,
    )
    am_res = engine.value(am)
    print("american put:", am_res.theoretical_price, am_res.model)


if __name__ == "__main__":
    main()

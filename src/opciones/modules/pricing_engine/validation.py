"""Validaciones de entradas y límites de arbitraje evidentes."""

from __future__ import annotations

import math

from opciones.modules.pricing_engine.types import PricingInputs, PricingStatus


def validate_inputs(inp: PricingInputs) -> list[str]:
    errors: list[str] = []
    if inp.spot <= 0:
        errors.append("spot debe ser positivo")
    if inp.strike <= 0:
        errors.append("strike debe ser positivo")
    if inp.time_to_expiry_years <= 0:
        errors.append("tiempo al vencimiento debe ser positivo")
    if inp.volatility is not None and inp.volatility <= 0:
        errors.append("volatilidad debe ser positiva")
    if inp.option_type.upper() not in {"CALL", "PUT"}:
        errors.append("option_type debe ser CALL o PUT")
    if inp.contract_size <= 0:
        errors.append("contract_size inválido")
    if inp.market_price is not None and inp.market_price < 0:
        errors.append("precio de mercado no puede ser negativo")
    return errors


def intrinsic(spot: float, strike: float, option_type: str) -> float:
    if option_type.upper() == "CALL":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def moneyness_label(spot: float, strike: float, option_type: str) -> str:
    ratio = spot / strike if strike else 0.0
    deep = 0.10
    near = 0.02
    if option_type.upper() == "CALL":
        if ratio > 1 + deep:
            return "DEEP_ITM"
        if ratio > 1 + near:
            return "ITM"
        if abs(ratio - 1) <= near:
            return "ATM"
        if ratio > 1 - deep:
            return "OTM"
        return "DEEP_OTM"
    # PUT
    if ratio < 1 - deep:
        return "DEEP_ITM"
    if ratio < 1 - near:
        return "ITM"
    if abs(ratio - 1) <= near:
        return "ATM"
    if ratio < 1 + deep:
        return "OTM"
    return "DEEP_OTM"


def check_arbitrage_bounds(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    dividend_yield: float,
    option_type: str,
) -> list[str]:
    """Marca violaciones evidentes (no exhaustivo)."""
    warnings: list[str] = []
    if market_price < 0:
        warnings.append("precio negativo viola límites de arbitraje")
        return warnings
    disc_k = strike * math.exp(-rate * time_to_expiry)
    disc_s = spot * math.exp(-dividend_yield * time_to_expiry)
    if option_type.upper() == "CALL":
        lower = max(0.0, disc_s - disc_k)
        upper = disc_s
        if market_price > upper * 1.001 + 1e-8:
            warnings.append(f"call por encima del cota superior (~{upper:.6f})")
        if market_price + 1e-8 < lower * 0.999 and lower > 0:
            warnings.append(f"call por debajo de cota inferior (~{lower:.6f})")
    else:
        lower = max(0.0, disc_k - disc_s)
        upper = disc_k
        if market_price > upper * 1.001 + 1e-8:
            warnings.append(f"put por encima de cota superior (~{upper:.6f})")
        if market_price + 1e-8 < lower * 0.999 and lower > 0:
            warnings.append(f"put por debajo de cota inferior (~{lower:.6f})")
    return warnings


def status_from_errors(errors: list[str]) -> PricingStatus:
    if not errors:
        return PricingStatus.OK
    if any("tiempo" in e or "spot" in e or "strike" in e for e in errors):
        return PricingStatus.INVALID_INPUT
    return PricingStatus.INCOMPLETE_DATA

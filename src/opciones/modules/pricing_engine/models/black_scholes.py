"""Black-Scholes y Black-Scholes-Merton (dividendos continuos)."""

from __future__ import annotations

import math
from datetime import datetime

from opciones.modules.pricing_engine.math_utils import norm_cdf, norm_pdf
from opciones.modules.pricing_engine.models.base import OptionPricingModel
from opciones.modules.pricing_engine.types import (
    ExerciseStyle,
    Greeks,
    PricingInputs,
    PricingResult,
    PricingStatus,
)
from opciones.modules.pricing_engine.validation import (
    check_arbitrage_bounds,
    intrinsic,
    moneyness_label,
    status_from_errors,
    validate_inputs,
)


def _d1_d2(s: float, k: float, t: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    if sigma <= 0 or t <= 0:
        raise ValueError("sigma y t deben ser positivos")
    vol_sqrt = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / vol_sqrt
    d2 = d1 - vol_sqrt
    return d1, d2


def bsm_price(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
) -> float:
    d1, d2 = _d1_d2(spot, strike, t, r, q, sigma)
    if option_type.upper() == "CALL":
        return spot * math.exp(-q * t) * norm_cdf(d1) - strike * math.exp(-r * t) * norm_cdf(d2)
    return strike * math.exp(-r * t) * norm_cdf(-d2) - spot * math.exp(-q * t) * norm_cdf(-d1)


def bsm_greeks(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
) -> Greeks:
    d1, d2 = _d1_d2(spot, strike, t, r, q, sigma)
    pdf = norm_pdf(d1)
    disc_s = math.exp(-q * t)
    disc_k = math.exp(-r * t)
    gamma = disc_s * pdf / (spot * sigma * math.sqrt(t))
    vega = spot * disc_s * pdf * math.sqrt(t) / 100.0  # por 1 punto de vol (%)
    if option_type.upper() == "CALL":
        delta = disc_s * norm_cdf(d1)
        theta_annual = (
            -spot * disc_s * pdf * sigma / (2 * math.sqrt(t))
            - r * strike * disc_k * norm_cdf(d2)
            + q * spot * disc_s * norm_cdf(d1)
        )
        rho = strike * t * disc_k * norm_cdf(d2) / 100.0
    else:
        delta = -disc_s * norm_cdf(-d1)
        theta_annual = (
            -spot * disc_s * pdf * sigma / (2 * math.sqrt(t))
            + r * strike * disc_k * norm_cdf(-d2)
            - q * spot * disc_s * norm_cdf(-d1)
        )
        rho = -strike * t * disc_k * norm_cdf(-d2) / 100.0
    price = bsm_price(spot, strike, t, r, q, sigma, option_type)
    elasticity = (delta * spot / price) if price else None
    return Greeks(
        delta=delta,
        gamma=gamma,
        theta_annual=theta_annual,
        theta_daily=theta_annual / 365.0,
        vega_per_pct=vega,
        rho=rho,
        elasticity=elasticity,
    )


def approx_itm_prob(spot: float, strike: float, t: float, r: float, q: float, sigma: float, option_type: str) -> float:
    """Probabilidad risk-neutral aproximada de terminar ITM (N(d2) / N(-d2))."""
    _, d2 = _d1_d2(spot, strike, t, r, q, sigma)
    if option_type.upper() == "CALL":
        return float(norm_cdf(d2))
    return float(norm_cdf(-d2))


class BlackScholesModel(OptionPricingModel):
    """Europeas sin dividendos (q=0). Advertir si hay dividendos en inputs."""

    @property
    def name(self) -> str:
        return "BlackScholes"

    def price(self, inputs: PricingInputs) -> PricingResult:
        return _price_bs_family(self.name, inputs, force_q=0.0)

    def greeks(self, inputs: PricingInputs) -> Greeks:
        q = 0.0
        if inputs.volatility is None:
            return Greeks()
        return bsm_greeks(
            inputs.spot,
            inputs.strike,
            inputs.time_to_expiry_years,
            inputs.rate,
            q,
            inputs.volatility,
            inputs.option_type,
        )


class BlackScholesMertonModel(OptionPricingModel):
    """Europeas con dividend yield continuo."""

    @property
    def name(self) -> str:
        return "BlackScholesMerton"

    def price(self, inputs: PricingInputs) -> PricingResult:
        return _price_bs_family(self.name, inputs, force_q=None)

    def greeks(self, inputs: PricingInputs) -> Greeks:
        if inputs.volatility is None:
            return Greeks()
        return bsm_greeks(
            inputs.spot,
            inputs.strike,
            inputs.time_to_expiry_years,
            inputs.rate,
            inputs.dividend_yield,
            inputs.volatility,
            inputs.option_type,
        )


def _price_bs_family(model_name: str, inputs: PricingInputs, force_q: float | None) -> PricingResult:
    errors = validate_inputs(inputs)
    assumptions = list(inputs.assumptions)
    warnings: list[str] = []
    if inputs.exercise_style == ExerciseStyle.AMERICAN:
        warnings.append(
            "estilo americano: BS/BSM es aproximación europea; preferir binomial"
        )
    if force_q is not None:
        q = force_q
        if inputs.dividend_yield != 0:
            assumptions.append("BS clásico fuerza q=0 ignorando dividend_yield de entrada")
    else:
        q = inputs.dividend_yield
    if inputs.volatility is None:
        errors.append("volatilidad requerida para precio teórico")
    if errors:
        return PricingResult(
            model=model_name,
            parameters=_params(inputs, q),
            warnings=errors + warnings,
            assumptions=assumptions,
            confidence=0.0,
            convergence_status=status_from_errors(errors),
        )
    assert inputs.volatility is not None
    if inputs.market_price is not None:
        warnings.extend(
            check_arbitrage_bounds(
                inputs.market_price,
                inputs.spot,
                inputs.strike,
                inputs.time_to_expiry_years,
                inputs.rate,
                q,
                inputs.option_type,
            )
        )
    theo = bsm_price(
        inputs.spot,
        inputs.strike,
        inputs.time_to_expiry_years,
        inputs.rate,
        q,
        inputs.volatility,
        inputs.option_type,
    )
    g = bsm_greeks(
        inputs.spot,
        inputs.strike,
        inputs.time_to_expiry_years,
        inputs.rate,
        q,
        inputs.volatility,
        inputs.option_type,
    )
    intr = intrinsic(inputs.spot, inputs.strike, inputs.option_type)
    status = PricingStatus.WARNING if warnings else PricingStatus.OK
    conf = 0.85 if inputs.exercise_style == ExerciseStyle.EUROPEAN else 0.55
    if warnings:
        conf *= 0.8
    return PricingResult(
        theoretical_price=theo,
        greeks=g,
        intrinsic_value=intr,
        extrinsic_value=max(theo - intr, 0.0),
        moneyness=moneyness_label(inputs.spot, inputs.strike, inputs.option_type),
        approx_itm_probability=approx_itm_prob(
            inputs.spot,
            inputs.strike,
            inputs.time_to_expiry_years,
            inputs.rate,
            q,
            inputs.volatility,
            inputs.option_type,
        ),
        model=model_name,
        parameters=_params(inputs, q),
        timestamp=datetime.utcnow(),
        assumptions=assumptions,
        confidence=conf,
        warnings=warnings,
        convergence_status=status,
    )


def _params(inputs: PricingInputs, q: float) -> dict:
    return {
        "spot": inputs.spot,
        "strike": inputs.strike,
        "t": inputs.time_to_expiry_years,
        "r": inputs.rate,
        "q": q,
        "sigma": inputs.volatility,
        "option_type": inputs.option_type,
        "exercise_style": inputs.exercise_style.value,
    }

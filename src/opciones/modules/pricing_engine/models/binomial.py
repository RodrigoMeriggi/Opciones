"""Árbol binomial CRR para opciones americanas (y europeas)."""

from __future__ import annotations

import math
from datetime import datetime

from opciones.modules.pricing_engine.models.base import OptionPricingModel
from opciones.modules.pricing_engine.types import (
    ExerciseStyle,
    Greeks,
    PricingInputs,
    PricingResult,
    PricingStatus,
)
from opciones.modules.pricing_engine.validation import (
    intrinsic,
    moneyness_label,
    status_from_errors,
    validate_inputs,
)


def binomial_crr_price(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
    *,
    steps: int = 100,
    american: bool = True,
    discrete_dividends: list[dict[str, float]] | None = None,
) -> float:
    if steps < 1:
        raise ValueError("steps >= 1")
    dt = t / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    a = math.exp((r - q) * dt)
    p = (a - d) / (u - d)
    if not (0.0 < p < 1.0):
        # parámetros extremos: aún así continuar con clamp suave y advertencia vía caller
        p = min(max(p, 1e-12), 1 - 1e-12)
    disc = math.exp(-r * dt)

    # Ajuste simple de dividendos discretos: restar PV de divs del spot (escrowed)
    s0 = spot
    divs = discrete_dividends or []
    for div in divs:
        td = float(div["t"])
        amt = float(div["amount"])
        if 0 < td <= t:
            s0 -= amt * math.exp(-r * td)
    if s0 <= 0:
        s0 = max(spot * 0.01, 1e-8)

    # precios terminales
    values = [0.0] * (steps + 1)
    for j in range(steps + 1):
        st = s0 * (u ** (steps - j)) * (d**j)
        if option_type.upper() == "CALL":
            values[j] = max(st - strike, 0.0)
        else:
            values[j] = max(strike - st, 0.0)

    for i in range(steps - 1, -1, -1):
        for j in range(i + 1):
            cont = disc * (p * values[j] + (1 - p) * values[j + 1])
            if american:
                st = s0 * (u ** (i - j)) * (d**j)
                exercise = max(st - strike, 0.0) if option_type.upper() == "CALL" else max(strike - st, 0.0)
                values[j] = max(cont, exercise)
            else:
                values[j] = cont
    return values[0]


def binomial_greeks_fd(inputs: PricingInputs, steps: int = 80) -> Greeks:
    """Griegas por diferencias finitas sobre el árbol."""
    if inputs.volatility is None:
        return Greeks()
    base = _price_raw(inputs, steps)
    bump_s = inputs.spot * 0.01
    up = inputs.model_copy(update={"spot": inputs.spot + bump_s})
    dn = inputs.model_copy(update={"spot": inputs.spot - bump_s})
    pu = _price_raw(up, steps)
    pd = _price_raw(dn, steps)
    delta = (pu - pd) / (2 * bump_s)
    gamma = (pu - 2 * base + pd) / (bump_s**2)

    bump_v = 0.01
    vol_up = inputs.model_copy(update={"volatility": inputs.volatility + bump_v})
    vega = (_price_raw(vol_up, steps) - base)  # por 1 punto absoluto de vol (=1%)

    bump_t = min(1.0 / 365.0, inputs.time_to_expiry_years / 2)
    if inputs.time_to_expiry_years - bump_t > 1e-8:
        t_dn = inputs.model_copy(
            update={"time_to_expiry_years": inputs.time_to_expiry_years - bump_t}
        )
        # Al pasar un día, t baja → theta diaria ≈ V(t-Δt) - V(t)
        theta_daily = _price_raw(t_dn, steps) - base
        theta_annual = theta_daily * 365.0
    else:
        theta_daily = None
        theta_annual = None

    bump_r = 0.01
    r_up = inputs.model_copy(update={"rate": inputs.rate + bump_r})
    rho = _price_raw(r_up, steps) - base  # por 1% absoluto de tasa

    elasticity = (delta * inputs.spot / base) if base else None
    return Greeks(
        delta=delta,
        gamma=gamma,
        theta_daily=theta_daily,
        theta_annual=theta_annual,
        vega_per_pct=vega,
        rho=rho,
        elasticity=elasticity,
    )


def _price_raw(inputs: PricingInputs, steps: int) -> float:
    assert inputs.volatility is not None
    return binomial_crr_price(
        inputs.spot,
        inputs.strike,
        inputs.time_to_expiry_years,
        inputs.rate,
        inputs.dividend_yield,
        inputs.volatility,
        inputs.option_type,
        steps=steps,
        american=inputs.exercise_style == ExerciseStyle.AMERICAN,
        discrete_dividends=inputs.discrete_dividends,
    )


class BinomialAmericanModel(OptionPricingModel):
    def __init__(self, steps: int = 100) -> None:
        self.steps = steps

    @property
    def name(self) -> str:
        return f"BinomialCRR(steps={self.steps})"

    def price(self, inputs: PricingInputs) -> PricingResult:
        errors = validate_inputs(inputs)
        warnings: list[str] = []
        assumptions = list(inputs.assumptions)
        if inputs.volatility is None:
            errors.append("volatilidad requerida")
        if errors:
            return PricingResult(
                model=self.name,
                warnings=errors,
                assumptions=assumptions,
                confidence=0.0,
                convergence_status=status_from_errors(errors),
            )
        theo = _price_raw(inputs, self.steps)
        g = binomial_greeks_fd(inputs, steps=min(self.steps, 60))
        intr = intrinsic(inputs.spot, inputs.strike, inputs.option_type)
        if inputs.discrete_dividends:
            assumptions.append("dividendos discretos vía spot escrowed")
        conf = 0.75 if inputs.exercise_style == ExerciseStyle.AMERICAN else 0.7
        return PricingResult(
            theoretical_price=theo,
            greeks=g,
            intrinsic_value=intr,
            extrinsic_value=max(theo - intr, 0.0),
            moneyness=moneyness_label(inputs.spot, inputs.strike, inputs.option_type),
            approx_itm_probability=None,  # no RN simple en árbol sin calibración extra
            model=self.name,
            parameters={
                "steps": self.steps,
                "spot": inputs.spot,
                "strike": inputs.strike,
                "t": inputs.time_to_expiry_years,
                "r": inputs.rate,
                "q": inputs.dividend_yield,
                "sigma": inputs.volatility,
                "american": inputs.exercise_style == ExerciseStyle.AMERICAN,
            },
            timestamp=datetime.utcnow(),
            assumptions=assumptions,
            confidence=conf,
            warnings=warnings,
            convergence_status=PricingStatus.OK,
        )

    def greeks(self, inputs: PricingInputs) -> Greeks:
        return binomial_greeks_fd(inputs, steps=min(self.steps, 60))

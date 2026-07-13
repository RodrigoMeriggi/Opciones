"""Solvers de volatilidad implícita: bisección, Newton-Raphson, Brent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from opciones.modules.pricing_engine.models.black_scholes import bsm_greeks, bsm_price
from opciones.modules.pricing_engine.types import PricingStatus
from opciones.modules.pricing_engine.validation import check_arbitrage_bounds


@dataclass
class IVSolverConfig:
    min_vol: float = 1e-4
    max_vol: float = 5.0
    tolerance: float = 1e-6
    max_iterations: int = 100
    methods: tuple[str, ...] = ("brent", "newton", "bisection")


@dataclass
class IVResult:
    implied_volatility: float | None
    method: str | None
    iterations: int
    converged: bool
    status: PricingStatus
    warnings: list[str] = field(default_factory=list)
    residual: float | None = None


def _price_fn(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    option_type: str,
) -> Callable[[float], float]:
    def f(sigma: float) -> float:
        return bsm_price(spot, strike, t, r, q, sigma, option_type)

    return f


def _vega_fn(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    option_type: str,
) -> Callable[[float], float]:
    def v(sigma: float) -> float:
        g = bsm_greeks(spot, strike, t, r, q, sigma, option_type)
        return (g.vega_per_pct or 0.0) * 100.0

    return v


def solve_implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    option_type: str,
    config: IVSolverConfig | None = None,
) -> IVResult:
    cfg = config or IVSolverConfig()
    warnings: list[str] = []
    if market_price <= 0:
        return IVResult(
            None, None, 0, False, PricingStatus.INVALID_INPUT, ["precio observado no positivo"]
        )
    if t <= 0 or spot <= 0 or strike <= 0:
        return IVResult(
            None, None, 0, False, PricingStatus.INVALID_INPUT, ["inputs esenciales inválidos"]
        )
    arb = check_arbitrage_bounds(market_price, spot, strike, t, r, q, option_type)
    if arb:
        warnings.extend(arb)
        if any("encima" in a for a in arb):
            return IVResult(
                None, None, 0, False, PricingStatus.ARBITRAGE_VIOLATION, warnings
            )

    price = _price_fn(spot, strike, t, r, q, option_type)
    vega = _vega_fn(spot, strike, t, r, q, option_type)

    lo_price = price(cfg.min_vol)
    hi_price = price(cfg.max_vol)
    if market_price < lo_price - cfg.tolerance or market_price > hi_price + cfg.tolerance:
        warnings.append(
            f"precio {market_price:.6f} fuera del rango alcanzable [{lo_price:.6f}, {hi_price:.6f}]"
        )
        return IVResult(None, None, 0, False, PricingStatus.NO_CONVERGENCE, warnings)

    last: IVResult | None = None
    for method in cfg.methods:
        if method == "brent":
            last = _brent(price, market_price, cfg)
        elif method == "newton":
            last = _newton(price, vega, market_price, cfg)
        elif method == "bisection":
            last = _bisection(price, market_price, cfg)
        else:
            continue
        last.warnings = warnings + last.warnings
        if last.converged and last.implied_volatility is not None:
            return last

    if last is None:
        last = IVResult(None, None, 0, False, PricingStatus.NO_CONVERGENCE, warnings)
    last.converged = False
    last.implied_volatility = None
    last.status = PricingStatus.NO_CONVERGENCE
    last.warnings.append("ningún método convergó; IV no inventada")
    return last


def _bisection(price: Callable[[float], float], target: float, cfg: IVSolverConfig) -> IVResult:
    a, b = cfg.min_vol, cfg.max_vol
    fa, fb = price(a) - target, price(b) - target
    if fa * fb > 0:
        return IVResult(None, "bisection", 0, False, PricingStatus.NO_CONVERGENCE, ["sin bracket"])
    for i in range(cfg.max_iterations):
        mid = 0.5 * (a + b)
        fm = price(mid) - target
        if abs(fm) < cfg.tolerance or abs(b - a) < cfg.tolerance:
            return IVResult(mid, "bisection", i + 1, True, PricingStatus.OK, residual=fm)
        if fa * fm < 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return IVResult(None, "bisection", cfg.max_iterations, False, PricingStatus.NO_CONVERGENCE)


def _newton(
    price: Callable[[float], float],
    vega: Callable[[float], float],
    target: float,
    cfg: IVSolverConfig,
) -> IVResult:
    sigma = 0.2
    for i in range(cfg.max_iterations):
        diff = price(sigma) - target
        if abs(diff) < cfg.tolerance:
            if cfg.min_vol <= sigma <= cfg.max_vol:
                return IVResult(sigma, "newton", i + 1, True, PricingStatus.OK, residual=diff)
            return IVResult(
                None, "newton", i + 1, False, PricingStatus.NO_CONVERGENCE, ["sigma fuera de límites"]
            )
        v = vega(sigma)
        if abs(v) < 1e-12:
            return IVResult(
                None, "newton", i + 1, False, PricingStatus.NO_CONVERGENCE, ["vega ~ 0"]
            )
        sigma = sigma - diff / v
        if sigma <= cfg.min_vol or sigma >= cfg.max_vol:
            return IVResult(
                None, "newton", i + 1, False, PricingStatus.NO_CONVERGENCE, ["newton salió de bounds"]
            )
    return IVResult(None, "newton", cfg.max_iterations, False, PricingStatus.NO_CONVERGENCE)


def _brent(price: Callable[[float], float], target: float, cfg: IVSolverConfig) -> IVResult:
    """Brent con bisección garantizada (implementación robusta simplificada)."""

    def f(x: float) -> float:
        return price(x) - target

    a, b = cfg.min_vol, cfg.max_vol
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        return IVResult(None, "brent", 0, False, PricingStatus.NO_CONVERGENCE, ["sin bracket"])

    c, fc = a, fa
    d = e = b - a
    for i in range(cfg.max_iterations):
        if fb == 0.0 or abs(b - a) < cfg.tolerance:
            return IVResult(b, "brent", i + 1, True, PricingStatus.OK, residual=fb)
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa
            c, fc = a, fa  # after swap keep consistency lightly
        # try inverse quadratic / secant
        if fa != fc and fb != fc:
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            s = b - fb * (b - a) / (fb - fa) if fb != fa else 0.5 * (a + b)

        m = 0.5 * (a + b)
        tol = cfg.tolerance
        accept = (
            (min(a, b) < s < max(a, b))
            and abs(s - b) < 0.5 * abs(e)
            and abs(e) > tol
        )
        if not accept:
            s = m
            d = e = b - a
        else:
            e, d = d, s - b

        c, fc = b, fb
        b = s
        fb = f(b)
        if fa * fb > 0:
            a, fa = c, fc
        if abs(fb) < tol:
            return IVResult(b, "brent", i + 1, True, PricingStatus.OK, residual=fb)
    return IVResult(None, "brent", cfg.max_iterations, False, PricingStatus.NO_CONVERGENCE)

"""Pruebas del motor de valuación."""

from __future__ import annotations

import pytest

from opciones.modules.pricing_engine import (
    BinomialAmericanModel,
    BlackScholesMertonModel,
    BlackScholesModel,
    ExplicitMissingDividendProvider,
    ManualRiskFreeRateProvider,
    PricingEngine,
    PricingInputs,
    PricingStatus,
    VolatilitySurface,
    bsm_price,
    default_engine,
)
from opciones.modules.pricing_engine.iv.solver import solve_implied_volatility
from opciones.modules.pricing_engine.types import ExerciseStyle


def test_bs_atm_call_known_value():
    # Hull-ish reference: S=K=100, T=1, r=0.05, q=0, sigma=0.2 ≈ 10.4506
    price = bsm_price(100, 100, 1.0, 0.05, 0.0, 0.2, "CALL")
    assert price == pytest.approx(10.4506, rel=1e-3)


def test_bs_put_call_parity():
    s, k, t, r, q, sig = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
    c = bsm_price(s, k, t, r, q, sig, "CALL")
    p = bsm_price(s, k, t, r, q, sig, "PUT")
    import math

    lhs = c - p
    rhs = s * math.exp(-q * t) - k * math.exp(-r * t)
    assert lhs == pytest.approx(rhs, rel=1e-6)


@pytest.mark.parametrize("otype", ["CALL", "PUT"])
@pytest.mark.parametrize("moneyness_spot", [90.0, 100.0, 110.0])
def test_bsm_itm_atm_otm(otype, moneyness_spot):
    model = BlackScholesMertonModel()
    res = model.price(
        PricingInputs(
            spot=moneyness_spot,
            strike=100,
            time_to_expiry_years=0.5,
            rate=0.1,
            dividend_yield=0.0,
            volatility=0.3,
            option_type=otype,
        )
    )
    assert res.theoretical_price is not None and res.theoretical_price >= 0
    assert res.greeks.delta is not None
    assert res.moneyness is not None


def test_short_and_long_expiry():
    model = BlackScholesModel()
    short = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=1 / 365, rate=0.05, volatility=0.2, option_type="CALL"
        )
    )
    long = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=2.0, rate=0.05, volatility=0.2, option_type="CALL"
        )
    )
    assert short.theoretical_price is not None
    assert long.theoretical_price is not None
    assert long.theoretical_price > short.theoretical_price


def test_high_low_vol():
    model = BlackScholesMertonModel()
    low = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=1, rate=0.05, volatility=0.05, option_type="CALL"
        )
    )
    high = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=1, rate=0.05, volatility=1.0, option_type="CALL"
        )
    )
    assert high.theoretical_price > low.theoretical_price


def test_dividends_reduce_call():
    model = BlackScholesMertonModel()
    no_div = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=1, rate=0.05, dividend_yield=0.0, volatility=0.2, option_type="CALL"
        )
    )
    with_div = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=1, rate=0.05, dividend_yield=0.05, volatility=0.2, option_type="CALL"
        )
    )
    assert with_div.theoretical_price < no_div.theoretical_price


def test_american_binomial_ge_european():
    inp = PricingInputs(
        spot=100,
        strike=100,
        time_to_expiry_years=1,
        rate=0.05,
        dividend_yield=0.0,
        volatility=0.25,
        option_type="PUT",
        exercise_style=ExerciseStyle.AMERICAN,
    )
    am = BinomialAmericanModel(steps=80).price(inp)
    eu = BlackScholesMertonModel().price(inp.model_copy(update={"exercise_style": ExerciseStyle.EUROPEAN}))
    assert am.theoretical_price is not None and eu.theoretical_price is not None
    assert am.theoretical_price + 1e-6 >= eu.theoretical_price


def test_iv_recovers_vol():
    true_vol = 0.35
    price = bsm_price(100, 100, 0.75, 0.1, 0.0, true_vol, "CALL")
    iv = solve_implied_volatility(price, 100, 100, 0.75, 0.1, 0.0, "CALL")
    assert iv.converged
    assert iv.implied_volatility == pytest.approx(true_vol, rel=1e-3)


def test_iv_no_convergence_no_invention():
    # precio absurdo por encima del spot (call)
    iv = solve_implied_volatility(1000.0, 100, 100, 1.0, 0.05, 0.0, "CALL")
    assert not iv.converged
    assert iv.implied_volatility is None
    assert iv.status in {PricingStatus.NO_CONVERGENCE, PricingStatus.ARBITRAGE_VIOLATION}


def test_invalid_inputs():
    engine = default_engine(0.1)
    res = engine.value(
        PricingInputs(
            spot=-1,
            strike=100,
            time_to_expiry_years=1,
            rate=0.1,
            volatility=0.2,
            option_type="CALL",
        )
    )
    assert res.convergence_status == PricingStatus.INVALID_INPUT


def test_zero_time_rejected():
    model = BlackScholesModel()
    res = model.price(
        PricingInputs(
            spot=100, strike=100, time_to_expiry_years=0, rate=0.05, volatility=0.2, option_type="CALL"
        )
    )
    assert res.theoretical_price is None


def test_surface_no_silent_extrapolation():
    surf = VolatilitySurface()
    surf.add_point(100, 0.5, 0.25)
    surf.add_point(110, 0.5, 0.28)
    hit = surf.lookup(105, 0.5)
    assert hit.volatility is not None
    assert hit.interpolated
    miss = surf.lookup(200, 2.0)
    assert miss.volatility is None
    assert any("extrapola" in w for w in miss.warnings)


def test_engine_full_metrics():
    eng = PricingEngine(
        rate_provider=ManualRiskFreeRateProvider(0.1),
        dividend_provider=ExplicitMissingDividendProvider(assume_zero_with_warning=True),
    )
    price = bsm_price(100, 100, 1, 0.1, 0.0, 0.2, "CALL")
    res = eng.full_metrics(
        PricingInputs(
            spot=100,
            strike=100,
            time_to_expiry_years=1,
            rate=0.1,
            market_price=price,
            option_type="CALL",
            exercise_style=ExerciseStyle.EUROPEAN,
        )
    )
    assert res.implied_volatility == pytest.approx(0.2, rel=1e-2)
    assert res.greeks.vega_per_pct is not None

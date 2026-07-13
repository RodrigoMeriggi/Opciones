"""Pruebas de rendimiento ligeras (CI-friendly)."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from opciones.modules.pricing_engine import BlackScholesMertonModel, PricingInputs
from tests.fixtures.market import liquid_call_chain
from opciones.modules.contract_selection import ContractSelector


@pytest.mark.performance
def test_bsm_pricing_throughput():
    model = BlackScholesMertonModel()
    start = time.perf_counter()
    n = 500
    for i in range(n):
        model.price(
            PricingInputs(
                spot=100 + (i % 10),
                strike=100,
                time_to_expiry_years=0.5,
                rate=0.1,
                volatility=0.25,
                option_type="CALL",
            )
        )
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0  # margen holgado para CI


@pytest.mark.performance
def test_selector_on_chain():
    chain = liquid_call_chain()
    sel = ContractSelector({"min_volume": 1, "max_spread_pct": 50, "avoid_deep_otm": False})
    start = time.perf_counter()
    for _ in range(50):
        sel.select(chain, "BULLISH")
    assert time.perf_counter() - start < 2.0

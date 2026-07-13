"""Contract tests — puertos y contratos de interfaz (offline)."""

from __future__ import annotations

import inspect

from opciones.ports import Broker, MarketDataProvider, RiskManager, Strategy


def test_broker_port_methods():
    required = {"submit_order", "cancel_order", "get_order", "get_positions", "get_portfolio", "get_cash"}
    methods = {n for n, _ in inspect.getmembers(Broker, predicate=inspect.isfunction)}
    # ABC abstracts appear as functions
    assert required <= {m for m in dir(Broker) if not m.startswith("_")}


def test_risk_manager_port_methods():
    for name in (
        "validate_order",
        "size_position",
        "is_buying_blocked",
        "activate_circuit_breaker",
        "reset_circuit_breaker",
        "get_limits",
    ):
        assert hasattr(RiskManager, name)


def test_strategy_port_methods():
    assert hasattr(Strategy, "evaluate")
    assert hasattr(Strategy, "evaluate_exits")
    assert hasattr(Strategy, "strategy_id")


def test_market_data_port_methods():
    for name in (
        "get_underlying",
        "get_quote",
        "get_option_chain",
        "get_historical_prices",
        "list_underlyings",
    ):
        assert hasattr(MarketDataProvider, name)

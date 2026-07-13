"""Fixtures compartidas."""

from __future__ import annotations

from decimal import Decimal

import pytest

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.models import RiskLimits
from opciones.modules.configuration.settings import Settings, reset_settings_cache
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.risk_manager.default import DefaultRiskManager


@pytest.fixture(autouse=True)
def _clear_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def safe_settings() -> Settings:
    return Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        emergency_stop=False,
        paper_initial_cash=Decimal("1000000"),
    )


@pytest.fixture
def risk_limits() -> RiskLimits:
    return RiskLimits(
        initial_capital=Decimal("1000000"),
        minimum_cash_reserve=Decimal("50000"),
        maximum_position_percentage=Decimal("0.1"),
        maximum_capital_at_risk=Decimal("500000"),
        maximum_total_premium=Decimal("500000"),
        maximum_open_positions=5,
        maximum_positions_per_underlying=3,
        daily_trade_limit=50,
        cooldown_after_loss_minutes=0,
        minimum_volume=1,
        maximum_bid_ask_spread_percentage=Decimal("25"),
        minimum_days_to_expiration=3,
        maximum_days_to_expiration=90,
        force_exit_days_before_expiration=2,
        maximum_daily_loss=Decimal("100000"),
        maximum_drawdown=Decimal("0.5"),
        maximum_consecutive_losses=10,
    )


@pytest.fixture
def market_data() -> MockMarketDataProvider:
    return MockMarketDataProvider(liquidity="high")


@pytest.fixture
def paper_broker(market_data: MockMarketDataProvider) -> PaperBroker:
    return PaperBroker(
        market_data,
        initial_cash=Decimal("1000000"),
        commission_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        latency_ms=0,
    )


@pytest.fixture
def risk_manager(safe_settings: Settings, risk_limits: RiskLimits) -> DefaultRiskManager:
    rm = DefaultRiskManager(
        limits=risk_limits,
        settings=safe_settings,
        ignore_market_hours=True,
    )
    if rm.is_buying_blocked():
        rm.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    return rm

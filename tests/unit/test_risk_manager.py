"""Pruebas del RiskManager y circuit breakers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from opciones.domain.enums import OrderSide, OrderType, RejectionCode
from opciones.domain.models import MarketQuote, OptionContract, OrderRequest, PortfolioSnapshot, Position
from opciones.domain.enums import OptionType


def _quote(symbol: str = "GGALC4500") -> MarketQuote:
    return MarketQuote(
        instrument_symbol=symbol,
        bid=Decimal("100"),
        ask=Decimal("102"),
        last=Decimal("101"),
        volume=100,
        ask_size=20,
        timestamp=datetime.utcnow(),
        source="test",
    )


def _portfolio(**kwargs) -> PortfolioSnapshot:
    base = dict(
        cash=Decimal("1000000"),
        reserved_cash=Decimal("0"),
        equity=Decimal("1000000"),
        open_positions=0,
        total_premium=Decimal("0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        weekly_pnl=Decimal("0"),
        peak_equity=Decimal("1000000"),
        consecutive_losses=0,
        trades_today=0,
        positions_by_underlying={},
    )
    base.update(kwargs)
    return PortfolioSnapshot(**base)


def _contract() -> OptionContract:
    return OptionContract(
        symbol="GGALC4500",
        underlying_symbol="GGAL",
        option_type=OptionType.CALL,
        strike=Decimal("4500"),
        expiration_date=date.today() + timedelta(days=20),
        bid=Decimal("100"),
        ask=Decimal("102"),
        last_price=Decimal("101"),
        volume=100,
        days_to_expiration=20,
        timestamp=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_approve_valid_buy(risk_manager):
    req = OrderRequest(
        symbol="GGALC4500",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        underlying_symbol="GGAL",
        expiration_date=date.today() + timedelta(days=20),
    )
    result = await risk_manager.validate_order(req, _quote(), _portfolio(), [], _contract())
    assert result.approved
    assert result.audit_trail
    assert result.suggested_quantity is not None


@pytest.mark.asyncio
async def test_emergency_blocks_buy_allows_sell(risk_manager):
    risk_manager.activate_circuit_breaker("MANUAL", "test")
    buy = OrderRequest(
        symbol="GGALC4500",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        underlying_symbol="GGAL",
    )
    buy_res = await risk_manager.validate_order(buy, _quote(), _portfolio(), [], _contract())
    assert not buy_res.approved
    assert RejectionCode.CIRCUIT_BREAKER.value in buy_res.codes

    pos = Position(
        symbol="GGALC4500",
        underlying_symbol="GGAL",
        option_type=OptionType.CALL,
        quantity=2,
        average_price=Decimal("100"),
        expiration_date=date.today() + timedelta(days=20),
    )
    sell = OrderRequest(
        symbol="GGALC4500",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=1,
        underlying_symbol="GGAL",
    )
    sell_res = await risk_manager.validate_order(sell, _quote(), _portfolio(), [pos], _contract())
    assert sell_res.approved


@pytest.mark.asyncio
async def test_daily_loss_circuit_breaker(risk_manager):
    pf = _portfolio(daily_pnl=Decimal("-150000"))
    req = OrderRequest(
        symbol="GGALC4500",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        underlying_symbol="GGAL",
    )
    result = await risk_manager.validate_order(req, _quote(), pf, [], _contract())
    assert not result.approved
    assert risk_manager.is_buying_blocked()


@pytest.mark.asyncio
async def test_max_open_positions(risk_manager):
    pf = _portfolio(open_positions=5)
    req = OrderRequest(
        symbol="GGALC4500",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        underlying_symbol="GGAL",
    )
    result = await risk_manager.validate_order(req, _quote(), pf, [], _contract())
    assert not result.approved
    assert RejectionCode.MAX_OPEN_POSITIONS.value in result.codes


@pytest.mark.asyncio
async def test_position_sizing_takes_minimum(risk_manager):
    pf = _portfolio(equity=Decimal("100000"), cash=Decimal("100000"))
    req = OrderRequest(symbol="X", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1000)
    q = _quote()
    sized = risk_manager.size_position(req, q, pf)
    assert sized < 1000
    assert sized >= 0


@pytest.mark.asyncio
async def test_manual_unlock_required(risk_manager):
    risk_manager.activate_circuit_breaker("MANUAL", "x")
    with pytest.raises(PermissionError):
        risk_manager.reset_circuit_breaker("wrong")
    risk_manager.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    assert not risk_manager.is_buying_blocked()


@pytest.mark.asyncio
async def test_api_errors_trigger_breaker(risk_manager):
    for _ in range(5):
        risk_manager.record_api_error()
    assert risk_manager.is_buying_blocked()

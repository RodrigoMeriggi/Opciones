"""Pruebas del PaperBroker."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.enums import OrderSide, OrderStatus, OrderType
from opciones.domain.models import MarketQuote, OrderRequest
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.paper_broker.expiration import ExpirationCloser, ExpirationCloserConfig


async def _pick_contract(md: MockMarketDataProvider, min_dte: int = 15):
    chain = await md.get_option_chain("GGAL")
    for c in chain.contracts:
        if (
            c.bid
            and c.ask
            and c.ask > c.bid
            and (c.volume or 0) >= 10
            and (c.days_to_expiration or 0) >= min_dte
        ):
            return c
    raise RuntimeError("No contract")


@pytest.mark.asyncio
async def test_market_buy_and_sell(paper_broker, market_data):
    c = await _pick_contract(market_data)
    buy = await paper_broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=2,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert buy.status == OrderStatus.FILLED
    assert buy.average_fill_price is not None
    assert buy.commission > 0

    sell = await paper_broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=2,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert sell.status == OrderStatus.FILLED
    positions = await paper_broker.get_positions()
    assert positions == []


@pytest.mark.asyncio
async def test_insufficient_cash(market_data):
    broker = PaperBroker(market_data, initial_cash=Decimal("10"))
    c = await _pick_contract(market_data)
    order = await broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_code == "INSUFFICIENT_CASH"


@pytest.mark.asyncio
async def test_naked_short_forbidden(paper_broker, market_data):
    c = await _pick_contract(market_data)
    order = await paper_broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.status == OrderStatus.REJECTED
    assert order.rejection_code == "NAKED_SHORT_FORBIDDEN"


@pytest.mark.asyncio
async def test_partial_fill(market_data):
    broker = PaperBroker(market_data, allow_partial=True)
    c = await _pick_contract(market_data)
    market_data.set_quote(
        MarketQuote(
            instrument_symbol=c.symbol,
            bid=c.bid,
            ask=c.ask,
            last=c.last_price,
            ask_size=1,
            bid_size=1,
            volume=c.volume,
            timestamp=datetime.utcnow(),
            source="mock",
        )
    )
    order = await broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 1


@pytest.mark.asyncio
async def test_no_liquidity(market_data):
    broker = PaperBroker(market_data)
    c = await _pick_contract(market_data)
    market_data.set_quote(
        MarketQuote(
            instrument_symbol=c.symbol,
            bid=c.bid,
            ask=c.ask,
            last=c.last_price,
            ask_size=0,
            bid_size=0,
            volume=0,
            timestamp=datetime.utcnow(),
            source="mock",
        )
    )
    # Matching uses ask_size or default; force available 0 via override of default
    broker.matching.default_available_size = 0
    order = await broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_limit_pending_then_fill(paper_broker, market_data):
    c = await _pick_contract(market_data)
    assert c.ask is not None
    order = await paper_broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            limit_price=c.ask / 2,  # demasiado bajo
            underlying_symbol="GGAL",
            expiration_date=c.expiration_date,
            option_type=c.option_type,
        )
    )
    assert order.status == OrderStatus.PENDING

    # Mejora el límite vía nueva cotización más baja
    market_data.set_quote(
        MarketQuote(
            instrument_symbol=c.symbol,
            bid=Decimal("1"),
            ask=order.request.limit_price,
            last=order.request.limit_price,
            ask_size=10,
            volume=100,
            timestamp=datetime.utcnow(),
            source="mock",
        )
    )
    updated = await paper_broker.process_pending()
    assert updated
    assert updated[0].status in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED}


@pytest.mark.asyncio
async def test_expiration_closer(paper_broker, market_data):
    c = await _pick_contract(market_data, min_dte=15)
    await paper_broker.submit_order(
        OrderRequest(
            symbol=c.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            underlying_symbol="GGAL",
            expiration_date=date.today() + timedelta(days=2),
            option_type=c.option_type,
        )
    )
    # Forzar expiration cercana en la posición
    positions = await paper_broker.get_positions()
    positions[0].expiration_date = date.today() + timedelta(days=1)

    closer = ExpirationCloser(
        paper_broker,
        market_data,
        ExpirationCloserConfig(force_exit_days=3, block_new_buys_days=5),
    )
    assert closer.should_block_new_buy(date.today() + timedelta(days=2))
    results = await closer.close_near_expiration()
    assert results
    assert results[0]["symbol"] == c.symbol

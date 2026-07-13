#!/usr/bin/env python3
"""Demostración de PaperBroker con varias operaciones."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.enums import OrderSide, OrderType
from opciones.domain.models import OrderRequest
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.paper_broker.expiration import ExpirationCloser


async def run() -> None:
    md = MockMarketDataProvider()
    broker = PaperBroker(
        md,
        initial_cash=Decimal("1000000"),
        commission_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        latency_ms=0,
    )
    chain = await md.get_option_chain("GGAL")
    operable = [c for c in chain.contracts if c.bid and c.ask and c.ask > c.bid and (c.volume or 0) >= 10]
    contract = next(c for c in operable if c.days_to_expiration and c.days_to_expiration >= 15)

    print("=== Compra MARKET ===")
    buy = await broker.submit_order(
        OrderRequest(
            symbol=contract.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=2,
            underlying_symbol="GGAL",
            expiration_date=contract.expiration_date,
            option_type=contract.option_type,
            strategy_id="demo",
            correlation_id="demo-1",
        )
    )
    print(buy.status, buy.average_fill_price, buy.commission)

    print("=== Intento short (debe rechazar) ===")
    short = await broker.submit_order(
        OrderRequest(
            symbol=contract.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=10,
            underlying_symbol="GGAL",
            expiration_date=contract.expiration_date,
            option_type=contract.option_type,
        )
    )
    print(short.status, short.rejection_code, short.rejection_reason)

    print("=== Venta parcial ===")
    sell = await broker.submit_order(
        OrderRequest(
            symbol=contract.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1,
            underlying_symbol="GGAL",
            expiration_date=contract.expiration_date,
            option_type=contract.option_type,
        )
    )
    print(sell.status, sell.average_fill_price)

    print("=== Limit lejos del mercado (pending) ===")
    far = operable[-1]
    limit_order = await broker.submit_order(
        OrderRequest(
            symbol=far.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            limit_price=Decimal("0.01"),
            underlying_symbol="GGAL",
            expiration_date=far.expiration_date,
            option_type=far.option_type,
        )
    )
    print(limit_order.status, limit_order.rejection_reason)

    portfolio = await broker.get_portfolio()
    print("\nPortfolio cash:", portfolio.cash, "positions:", portfolio.open_positions)
    print("Trades:", len(broker.trade_history))

    closer = ExpirationCloser(broker, md)
    print("Forced exits:", await closer.close_near_expiration())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

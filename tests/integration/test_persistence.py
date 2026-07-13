"""Pruebas de integración ligeras (sin PostgreSQL externo)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from opciones.database.models.orm import Base, UnderlyingAssetRow
from opciones.adapters.persistence.memory import InMemoryOrderRepository, InMemoryPortfolioRepository
from opciones.domain.models import Order, OrderRequest, PortfolioSnapshot
from opciones.domain.enums import OrderStatus


def test_sqlite_schema_creates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            UnderlyingAssetRow(
                symbol="GGAL",
                description="Galicia",
                last_price=Decimal("4500"),
            )
        )
        session.commit()
        row = session.get(UnderlyingAssetRow, "GGAL")
        assert row is not None
        assert row.last_price == Decimal("4500")


@pytest.mark.asyncio
async def test_memory_repositories():
    orders = InMemoryOrderRepository()
    portfolio = InMemoryPortfolioRepository()
    order = Order(
        request=OrderRequest(symbol="X", side="BUY", order_type="MARKET", quantity=1),
        status=OrderStatus.FILLED,
    )
    await orders.save(order)
    assert await orders.get(order.id) is not None
    snap = PortfolioSnapshot(cash=Decimal("1"), equity=Decimal("1"))
    await portfolio.save_snapshot(snap)
    assert await portfolio.get_latest_snapshot() == snap

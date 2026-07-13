"""Repositorios en memoria (desarrollo/tests) que implementan los puertos."""

from __future__ import annotations

from uuid import UUID

from opciones.domain.models import Order, PortfolioSnapshot, Position
from opciones.ports import OrderRepository, PortfolioRepository


class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._orders: dict[UUID, Order] = {}

    async def save(self, order: Order) -> None:
        self._orders[order.id] = order

    async def get(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def list_by_status(self, status: str) -> list[Order]:
        return [o for o in self._orders.values() if str(o.status).endswith(status)]

    async def list_recent(self, limit: int = 100) -> list[Order]:
        orders = sorted(self._orders.values(), key=lambda o: o.created_at, reverse=True)
        return orders[:limit]


class InMemoryPortfolioRepository(PortfolioRepository):
    def __init__(self) -> None:
        self._snapshots: list[PortfolioSnapshot] = []
        self._positions: dict[UUID, Position] = {}

    async def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._snapshots.append(snapshot)

    async def get_latest_snapshot(self) -> PortfolioSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    async def save_position(self, position: Position) -> None:
        self._positions[position.id] = position

    async def list_open_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def delete_position(self, position_id: UUID) -> None:
        self._positions.pop(position_id, None)

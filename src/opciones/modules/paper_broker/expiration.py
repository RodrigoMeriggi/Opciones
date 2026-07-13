"""ExpirationCloser tipado contra Broker duck-typing (paper o histórico)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from opciones.domain.enums import OrderSide, OrderType
from opciones.domain.models import OrderRequest, Position
from opciones.ports import MarketDataProvider


class CloseableBroker(Protocol):
    async def submit_order(self, request: OrderRequest) -> Any: ...
    async def get_positions(self) -> list[Position]: ...
    def add_alert(self, message: str) -> None: ...


@dataclass
class ExpirationCloserConfig:
    force_exit_days: int = 3
    block_new_buys_days: int = 5
    max_aggression_steps: int = 5
    aggression_step_pct: Decimal = Decimal("0.02")


class ExpirationCloser:
    def __init__(
        self,
        broker: CloseableBroker,
        market_data: MarketDataProvider,
        config: ExpirationCloserConfig | None = None,
    ) -> None:
        self.broker = broker
        self.market_data = market_data
        self.config = config or ExpirationCloserConfig()
        self._aggression: dict[str, int] = {}
        if not hasattr(self.broker, "add_alert"):
            setattr(self.broker, "add_alert", lambda msg: None)

    def days_to_exp(self, position: Position, today: date | None = None) -> int:
        ref = today or date.today()
        return (position.expiration_date - ref).days

    def should_block_new_buy(self, expiration: date, today: date | None = None) -> bool:
        ref = today or date.today()
        return (expiration - ref).days < self.config.block_new_buys_days

    def positions_needing_exit(
        self, positions: list[Position], today: date | None = None
    ) -> list[Position]:
        return [p for p in positions if self.days_to_exp(p, today) <= self.config.force_exit_days]

    async def close_near_expiration(self, today: date | None = None) -> list[dict]:
        positions = await self.broker.get_positions()
        results: list[dict] = []
        for pos in self.positions_needing_exit(positions, today):
            results.append(await self._attempt_close(pos))
        return results

    async def _attempt_close(self, pos: Position) -> dict:
        quote = await self.market_data.get_quote(pos.symbol)
        step = self._aggression.get(pos.symbol, 0)
        correlation_id = str(uuid4())
        if quote is None or quote.bid is None:
            msg = f"Sin liquidez para cerrar {pos.symbol} (DTE={self.days_to_exp(pos)})"
            self.broker.add_alert(msg)
            return {"symbol": pos.symbol, "closed": False, "reason": msg}

        limit = quote.bid * (Decimal("1") - self.config.aggression_step_pct * step)
        if limit <= 0:
            limit = quote.bid

        request = OrderRequest(
            symbol=pos.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            underlying_symbol=pos.underlying_symbol,
            expiration_date=pos.expiration_date,
            option_type=pos.option_type,
            strategy_id="expiration_closer",
            correlation_id=correlation_id,
            reason="FORCE_EXIT_BEFORE_EXPIRATION",
        )
        order = await self.broker.submit_order(request)
        status = str(order.status).replace("OrderStatus.", "")
        if status in {"FILLED", "PARTIALLY_FILLED"}:
            return {
                "symbol": pos.symbol,
                "closed": status == "FILLED",
                "order_id": str(order.id),
                "aggression_step": step,
            }

        request.order_type = OrderType.LIMIT
        request.limit_price = limit
        order = await self.broker.submit_order(request)
        status = str(order.status).replace("OrderStatus.", "")
        if status not in {"FILLED", "PARTIALLY_FILLED"}:
            self.broker.add_alert(
                f"No se pudo cerrar {pos.symbol}: {order.rejection_reason or status}"
            )
            if step < self.config.max_aggression_steps:
                self._aggression[pos.symbol] = step + 1
        else:
            self._aggression.pop(pos.symbol, None)
        return {
            "symbol": pos.symbol,
            "closed": status == "FILLED",
            "order_id": str(order.id),
            "aggression_step": step,
            "limit_price": str(limit),
            "status": status,
        }

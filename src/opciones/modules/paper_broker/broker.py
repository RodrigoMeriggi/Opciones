"""PaperBroker: simulación completa de compra/venta de opciones sin dinero real."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from opciones.domain.enums import OrderSide, OrderStatus, OrderType, OptionType
from opciones.domain.models import (
    Fill,
    MarketQuote,
    Order,
    OrderRequest,
    PortfolioSnapshot,
    Position,
)
from opciones.modules.paper_broker.matching import SimulatedMatchingEngine
from opciones.ports import Broker, MarketDataProvider


class PaperBroker(Broker):
    """
    Broker simulado en memoria (persistencia ORM se agrega vía repositorios).
    - No permite shorts ni lanzamientos descubiertos.
    - No ejerce opciones.
    """

    def __init__(
        self,
        market_data: MarketDataProvider,
        initial_cash: Decimal = Decimal("1000000"),
        commission_rate: Decimal = Decimal("0.001"),
        slippage_bps: Decimal = Decimal("5"),
        latency_ms: int = 0,
        allow_partial: bool = True,
    ) -> None:
        self.market_data = market_data
        self.commission_rate = commission_rate
        self.latency_ms = latency_ms
        self.matching = SimulatedMatchingEngine(
            slippage_bps=slippage_bps,
            allow_partial=allow_partial,
        )
        self._cash = initial_cash
        self._reserved = Decimal("0")
        self._positions: dict[str, Position] = {}
        self._orders: dict[UUID, Order] = {}
        self._pending: list[UUID] = []
        self._realized_pnl = Decimal("0")
        self._daily_pnl = Decimal("0")
        self._weekly_pnl = Decimal("0")
        self._peak_equity = initial_cash
        self._consecutive_losses = 0
        self._trades_today = 0
        self._last_loss_at: datetime | None = None
        self._trade_history: list[dict] = []
        self._alerts: list[str] = []

    @property
    def alerts(self) -> list[str]:
        return list(self._alerts)

    @property
    def trade_history(self) -> list[dict]:
        return list(self._trade_history)

    async def submit_order(self, request: OrderRequest) -> Order:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)

        order = Order(
            id=uuid4(),
            request=request,
            status=OrderStatus.CREATED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._orders[order.id] = order

        validation = await self._validate(request)
        if not validation["ok"]:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = validation["reason"]
            order.rejection_code = validation.get("code")
            order.validation_notes = validation.get("notes", [])
            order.updated_at = datetime.utcnow()
            return order

        order.status = OrderStatus.VALIDATED
        order.validation_notes = validation.get("notes", [])

        quote = await self.market_data.get_quote(request.symbol)
        order.quote_used = quote

        match = self.matching.match(request, quote)
        if not match.can_fill:
            # Limit/stop pueden quedar pendientes
            if request.order_type.upper() in {
                OrderType.LIMIT,
                OrderType.STOP_MARKET,
                OrderType.STOP_LIMIT,
            }:
                order.status = OrderStatus.PENDING
                self._pending.append(order.id)
                if request.side.upper() == OrderSide.BUY and request.limit_price:
                    reserve = request.limit_price * request.quantity
                    reserve += reserve * self.commission_rate
                    if reserve > self._cash - self._reserved:
                        order.status = OrderStatus.REJECTED
                        order.rejection_code = "INSUFFICIENT_CASH"
                        order.rejection_reason = "Saldo insuficiente para reservar"
                        self._pending.remove(order.id)
                    else:
                        self._reserved += reserve
                order.updated_at = datetime.utcnow()
                return order
            order.status = OrderStatus.REJECTED
            order.rejection_reason = match.reason
            order.rejection_code = "NO_FILL"
            order.updated_at = datetime.utcnow()
            return order

        await self._apply_fill(order, match.fill_price, match.fill_quantity, match.slippage, quote)
        return order

    async def process_pending(self) -> list[Order]:
        """Reintenta órdenes pendientes con cotización actual."""
        updated: list[Order] = []
        for oid in list(self._pending):
            order = self._orders[oid]
            quote = await self.market_data.get_quote(order.request.symbol)
            order.quote_used = quote
            match = self.matching.match(order.request, quote)
            if match.can_fill:
                remaining = order.request.quantity - order.filled_quantity
                fill_qty = min(match.fill_quantity, remaining)
                # Liberar reserva proporcional en buys
                if order.request.side.upper() == OrderSide.BUY and order.request.limit_price:
                    reserved_unit = order.request.limit_price * (
                        Decimal("1") + self.commission_rate
                    )
                    self._reserved = max(
                        Decimal("0"),
                        self._reserved - reserved_unit * fill_qty,
                    )
                await self._apply_fill(order, match.fill_price, fill_qty, match.slippage, quote)
                if order.status == OrderStatus.FILLED:
                    self._pending.remove(oid)
                updated.append(order)
        return updated

    async def cancel_order(self, order_id: UUID) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Orden {order_id} no encontrada")
        if order.status not in {OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED, OrderStatus.VALIDATED}:
            raise ValueError(f"No se puede cancelar orden en estado {order.status}")
        if order_id in self._pending:
            self._pending.remove(order_id)
        if order.request.side.upper() == OrderSide.BUY and order.request.limit_price:
            remaining = order.request.quantity - order.filled_quantity
            reserved_unit = order.request.limit_price * (Decimal("1") + self.commission_rate)
            self._reserved = max(Decimal("0"), self._reserved - reserved_unit * remaining)
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        return order

    async def get_order(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def get_positions(self) -> list[Position]:
        # Mark-to-market con cotización actual (mid preferido; si no, last/bid)
        for pos in self._positions.values():
            q = await self.market_data.get_quote(pos.symbol)
            if q is None:
                continue
            mark = q.mid or q.last or q.bid or q.ask
            if mark is not None and mark > 0:
                pos.current_price = mark
        return list(self._positions.values())

    async def get_portfolio(self) -> PortfolioSnapshot:
        positions = await self.get_positions()
        unrealized = Decimal("0")
        premium = Decimal("0")
        by_und: dict[str, int] = {}
        for p in positions:
            if p.unrealized_pnl is not None:
                unrealized += p.unrealized_pnl
            premium += p.average_price * p.quantity
            by_und[p.underlying_symbol] = by_und.get(p.underlying_symbol, 0) + 1
        equity = self._cash + unrealized + sum(
            (p.current_price or p.average_price) * p.quantity for p in positions
        )
        # equity = cash + market value of positions (cash already reduced on buy)
        mv = sum((p.current_price or p.average_price) * p.quantity for p in positions)
        equity = self._cash + mv
        self._peak_equity = max(self._peak_equity, equity)
        return PortfolioSnapshot(
            cash=self._cash,
            reserved_cash=self._reserved,
            equity=equity,
            open_positions=len(positions),
            total_premium=premium,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized,
            daily_pnl=self._daily_pnl,
            weekly_pnl=self._weekly_pnl,
            peak_equity=self._peak_equity,
            consecutive_losses=self._consecutive_losses,
            trades_today=self._trades_today,
            positions_by_underlying=by_und,
            last_loss_at=self._last_loss_at,
        )

    async def get_cash(self) -> Decimal:
        return self._cash

    async def _validate(self, request: OrderRequest) -> dict:
        notes: list[str] = []
        if request.quantity <= 0 or int(request.quantity) != request.quantity:
            return {"ok": False, "reason": "Cantidad inválida", "code": "INVALID_QUANTITY", "notes": notes}
        if request.side.upper() not in {OrderSide.BUY, OrderSide.SELL}:
            return {"ok": False, "reason": "Side inválido", "code": "INVALID_SIDE", "notes": notes}

        if request.side.upper() == OrderSide.SELL:
            pos = self._positions.get(request.symbol)
            if pos is None or pos.quantity < request.quantity:
                return {
                    "ok": False,
                    "reason": "No se permiten shorts ni ventas descubiertas",
                    "code": "NAKED_SHORT_FORBIDDEN",
                    "notes": notes,
                }
            notes.append("Venta cubierta validada")
        else:
            quote = await self.market_data.get_quote(request.symbol)
            if quote is None or quote.ask is None or quote.ask <= 0:
                return {"ok": False, "reason": "Sin ask válido", "code": "INVALID_QUOTE", "notes": notes}
            est = quote.ask * request.quantity
            est_comm = est * self.commission_rate
            if est + est_comm > self._cash - self._reserved:
                return {
                    "ok": False,
                    "reason": "Saldo insuficiente",
                    "code": "INSUFFICIENT_CASH",
                    "notes": notes,
                }
            notes.append("Saldo suficiente estimado")
        return {"ok": True, "notes": notes}

    async def _apply_fill(
        self,
        order: Order,
        price: Decimal | None,
        quantity: int,
        slippage: Decimal,
        quote: MarketQuote | None,
    ) -> None:
        assert price is not None and quantity > 0
        notional = price * quantity
        commission = notional * self.commission_rate
        side = order.request.side.upper()

        if side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self._cash:
                order.status = OrderStatus.REJECTED
                order.rejection_code = "INSUFFICIENT_CASH"
                order.rejection_reason = "Saldo insuficiente al ejecutar"
                return
            self._cash -= total_cost
            self._upsert_long(order, price, quantity)
        else:
            pos = self._positions[order.request.symbol]
            proceeds = notional - commission
            pnl = (price - pos.average_price) * quantity - commission
            self._cash += proceeds
            self._realized_pnl += pnl
            self._daily_pnl += pnl
            self._weekly_pnl += pnl
            if pnl < 0:
                self._consecutive_losses += 1
                self._last_loss_at = datetime.utcnow()
            else:
                self._consecutive_losses = 0
            remaining = pos.quantity - quantity
            if remaining == 0:
                del self._positions[order.request.symbol]
            else:
                pos.quantity = remaining

        fill = Fill(
            order_id=order.id,
            quantity=quantity,
            price=price,
            commission=commission,
            slippage=slippage,
            quote_snapshot=quote,
        )
        order.fills.append(fill.model_dump())
        order.filled_quantity += quantity
        if order.average_fill_price is None:
            order.average_fill_price = price
        else:
            prev = order.filled_quantity - quantity
            order.average_fill_price = (
                order.average_fill_price * prev + price * quantity
            ) / order.filled_quantity
        order.commission += commission
        order.slippage += slippage
        order.updated_at = datetime.utcnow()
        self._trades_today += 1

        if order.filled_quantity >= order.request.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
            if order.id not in self._pending:
                self._pending.append(order.id)

        self._trade_history.append(
            {
                "order_id": str(order.id),
                "symbol": order.request.symbol,
                "side": side,
                "quantity": quantity,
                "price": str(price),
                "commission": str(commission),
                "slippage": str(slippage),
                "strategy_id": order.request.strategy_id,
                "correlation_id": order.request.correlation_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def _upsert_long(self, order: Order, price: Decimal, quantity: int) -> None:
        symbol = order.request.symbol
        existing = self._positions.get(symbol)
        und = order.request.underlying_symbol or symbol
        exp = order.request.expiration_date
        opt = order.request.option_type or OptionType.CALL
        if existing:
            total_qty = existing.quantity + quantity
            existing.average_price = (
                existing.average_price * existing.quantity + price * quantity
            ) / total_qty
            existing.quantity = total_qty
            existing.current_price = price
        else:
            if exp is None:
                # Inferir de metadata si existe; si no, rechazar implícitamente no debería llegar
                from datetime import date, timedelta

                exp = date.today() + timedelta(days=30)
            self._positions[symbol] = Position(
                symbol=symbol,
                underlying_symbol=und,
                option_type=opt,
                quantity=quantity,
                average_price=price,
                current_price=price,
                expiration_date=exp,
                strategy_id=order.request.strategy_id,
                correlation_id=order.request.correlation_id,
            )

    def add_alert(self, message: str) -> None:
        self._alerts.append(f"{datetime.utcnow().isoformat()} {message}")

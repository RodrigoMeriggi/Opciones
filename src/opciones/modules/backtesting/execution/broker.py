"""HistoricalBroker — PaperBroker dirigido por reloj histórico."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from opciones.domain.enums import OrderSide, OrderStatus, OptionType
from opciones.domain.models import (
    Order,
    OrderRequest,
    PortfolioSnapshot,
    Position,
)
from opciones.modules.backtesting.data.provider import HistoricalDataProvider
from opciones.modules.backtesting.execution.simulator import ExecutionSimulator
from opciones.modules.backtesting.types import TradeRecord
from opciones.ports import Broker


class HistoricalBroker(Broker):
    def __init__(
        self,
        market_data: HistoricalDataProvider,
        initial_cash: Decimal,
        simulator: ExecutionSimulator | None = None,
    ) -> None:
        self.market_data = market_data
        self.simulator = simulator or ExecutionSimulator()
        self._cash = initial_cash
        self._reserved = Decimal("0")
        self._positions: dict[str, Position] = {}
        self._orders: dict[UUID, Order] = {}
        self._pending: list[UUID] = []
        self._realized = Decimal("0")
        self._daily = Decimal("0")
        self._weekly = Decimal("0")
        self._peak = initial_cash
        self._consecutive_losses = 0
        self._trades_today = 0
        self._last_loss_at: datetime | None = None
        self.trades: list[TradeRecord] = []
        self.rejected_count = 0
        self.partial_count = 0
        self.total_commission = Decimal("0")
        self.total_slippage = Decimal("0")

    async def submit_order(self, request: OrderRequest) -> Order:
        now = self.market_data.clock.now
        order = Order(
            id=uuid4(),
            request=request,
            status=OrderStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        self._orders[order.id] = order

        if request.side.upper() == OrderSide.SELL:
            pos = self._positions.get(request.symbol)
            if pos is None or pos.quantity < request.quantity:
                order.status = OrderStatus.REJECTED
                order.rejection_code = "NAKED_SHORT_FORBIDDEN"
                order.rejection_reason = "Short prohibido"
                self.rejected_count += 1
                self.trades.append(
                    TradeRecord(
                        symbol=request.symbol,
                        underlying=request.underlying_symbol or "",
                        option_type=str(request.option_type or ""),
                        side=request.side,
                        quantity=request.quantity,
                        price=Decimal("0"),
                        commission=Decimal("0"),
                        slippage=Decimal("0"),
                        timestamp=now,
                        rejected=True,
                        rejection_reason=order.rejection_reason,
                    )
                )
                return order

        quote = await self.market_data.get_quote(request.symbol)
        order.quote_used = quote
        result = self.simulator.execute(request, quote)
        if not result.filled:
            if request.order_type.upper() == "LIMIT":
                order.status = OrderStatus.PENDING
                self._pending.append(order.id)
                return order
            order.status = OrderStatus.REJECTED
            order.rejection_reason = result.reason
            self.rejected_count += 1
            return order

        await self._apply(order, result.price, result.quantity, result.commission, result.slippage, result.partial)
        return order

    async def process_pending(self) -> list[Order]:
        updated = []
        for oid in list(self._pending):
            order = self._orders[oid]
            quote = await self.market_data.get_quote(order.request.symbol)
            result = self.simulator.execute(order.request, quote)
            if result.filled:
                rem = order.request.quantity - order.filled_quantity
                qty = min(result.quantity, rem)
                await self._apply(
                    order, result.price, qty, result.commission, result.slippage, result.partial
                )
                if order.status == OrderStatus.FILLED:
                    self._pending.remove(oid)
                updated.append(order)
        return updated

    async def _apply(
        self,
        order: Order,
        price: Decimal | None,
        qty: int,
        commission: Decimal,
        slippage: Decimal,
        partial: bool,
    ) -> None:
        assert price is not None
        now = self.market_data.clock.now
        side = order.request.side.upper()
        notional = price * qty
        if side == OrderSide.BUY:
            cost = notional + commission
            if cost > self._cash:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "Saldo insuficiente"
                self.rejected_count += 1
                return
            self._cash -= cost
            self._upsert(order, price, qty, now)
            pnl = None
        else:
            pos = self._positions[order.request.symbol]
            proceeds = notional - commission
            pnl = (price - pos.average_price) * qty - commission
            self._cash += proceeds
            self._realized += pnl
            self._daily += pnl
            self._weekly += pnl
            if pnl < 0:
                self._consecutive_losses += 1
                self._last_loss_at = now
            else:
                self._consecutive_losses = 0
            rem = pos.quantity - qty
            if rem <= 0:
                del self._positions[order.request.symbol]
            else:
                pos.quantity = rem

        order.filled_quantity += qty
        order.average_fill_price = price
        order.commission += commission
        order.slippage += slippage
        order.updated_at = now
        order.status = (
            OrderStatus.PARTIALLY_FILLED
            if order.filled_quantity < order.request.quantity
            else OrderStatus.FILLED
        )
        if partial or order.status == OrderStatus.PARTIALLY_FILLED:
            self.partial_count += 1
            if order.id not in self._pending and order.status != OrderStatus.FILLED:
                self._pending.append(order.id)
        self.total_commission += commission
        self.total_slippage += slippage
        self._trades_today += 1
        self.trades.append(
            TradeRecord(
                symbol=order.request.symbol,
                underlying=order.request.underlying_symbol or "",
                option_type=str(order.request.option_type or ""),
                side=side,
                quantity=qty,
                price=price,
                commission=commission,
                slippage=slippage,
                timestamp=now,
                pnl=pnl,
                entry_reason=order.request.reason if side == OrderSide.BUY else None,
                exit_reason=order.request.reason if side == OrderSide.SELL else None,
                expiration=order.request.expiration_date,
                partial=partial or order.status == OrderStatus.PARTIALLY_FILLED,
            )
        )

    def _upsert(self, order: Order, price: Decimal, qty: int, now: datetime) -> None:
        sym = order.request.symbol
        existing = self._positions.get(sym)
        und = order.request.underlying_symbol or sym
        exp = order.request.expiration_date
        opt = order.request.option_type or OptionType.CALL
        if existing:
            total = existing.quantity + qty
            existing.average_price = (
                existing.average_price * existing.quantity + price * qty
            ) / total
            existing.quantity = total
            existing.current_price = price
        else:
            from datetime import timedelta

            self._positions[sym] = Position(
                symbol=sym,
                underlying_symbol=und,
                option_type=opt,
                quantity=qty,
                average_price=price,
                current_price=price,
                expiration_date=exp or (now.date() + timedelta(days=30)),
                opened_at=now,
                strategy_id=order.request.strategy_id,
                correlation_id=order.request.correlation_id,
            )

    async def cancel_order(self, order_id: UUID) -> Order:
        order = self._orders[order_id]
        if order_id in self._pending:
            self._pending.remove(order_id)
        order.status = OrderStatus.CANCELLED
        order.updated_at = self.market_data.clock.now
        return order

    async def get_order(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def get_positions(self) -> list[Position]:
        for p in self._positions.values():
            q = await self.market_data.get_quote(p.symbol)
            if q and (q.bid or q.mid):
                # Mark-to-market con bid (salida realista), no last
                p.current_price = q.bid or q.mid
        return list(self._positions.values())

    async def get_portfolio(self) -> PortfolioSnapshot:
        positions = await self.get_positions()
        mv = sum((p.current_price or p.average_price) * p.quantity for p in positions)
        unreal = sum(
            ((p.current_price or p.average_price) - p.average_price) * p.quantity for p in positions
        )
        premium = sum(p.average_price * p.quantity for p in positions)
        by_und: dict[str, int] = {}
        for p in positions:
            by_und[p.underlying_symbol] = by_und.get(p.underlying_symbol, 0) + 1
        equity = self._cash + mv
        self._peak = max(self._peak, equity)
        return PortfolioSnapshot(
            cash=self._cash,
            reserved_cash=self._reserved,
            equity=equity,
            open_positions=len(positions),
            total_premium=premium,
            realized_pnl=self._realized,
            unrealized_pnl=unreal,
            daily_pnl=self._daily,
            weekly_pnl=self._weekly,
            peak_equity=self._peak,
            consecutive_losses=self._consecutive_losses,
            trades_today=self._trades_today,
            positions_by_underlying=by_und,
            last_loss_at=self._last_loss_at,
            as_of=self.market_data.clock.now,
        )

    async def get_cash(self) -> Decimal:
        return self._cash

    def reset_daily_counters(self) -> None:
        self._daily = Decimal("0")
        self._trades_today = 0

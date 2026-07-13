"""Simulador de ejecución histórica — bid/ask, no last price automático."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from opciones.domain.enums import OrderSide, OrderType
from opciones.domain.models import MarketQuote, OrderRequest


@dataclass
class ExecutionResult:
    filled: bool
    quantity: int = 0
    price: Decimal | None = None
    slippage: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    partial: bool = False
    reason: str | None = None


class ExecutionSimulator:
    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.001"),
        slippage_bps: Decimal = Decimal("5"),
        allow_partial: bool = True,
        default_size: int = 30,
    ) -> None:
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps
        self.allow_partial = allow_partial
        self.default_size = default_size

    def execute(self, request: OrderRequest, quote: MarketQuote | None) -> ExecutionResult:
        if quote is None:
            return ExecutionResult(False, reason="Sin cotización histórica")
        if quote.bid is None or quote.ask is None:
            return ExecutionResult(False, reason="Sin bid/ask — no se usa last automáticamente")
        if quote.ask <= 0 or quote.bid < 0:
            return ExecutionResult(False, reason="Precios inválidos")
        if quote.bid > quote.ask:
            return ExecutionResult(False, reason="Bid > Ask")

        side = request.side.upper()
        available = (
            (quote.ask_size if side == OrderSide.BUY else quote.bid_size)
            or self.default_size
        )
        if available <= 0:
            return ExecutionResult(False, reason="Sin liquidez")

        qty = request.quantity
        fill_qty = qty
        partial = False
        if qty > available:
            if not self.allow_partial:
                return ExecutionResult(False, reason="Liquidez insuficiente")
            fill_qty = available
            partial = True

        otype = request.order_type.upper()
        if otype == OrderType.MARKET:
            raw = quote.ask if side == OrderSide.BUY else quote.bid
        elif otype == OrderType.LIMIT:
            if request.limit_price is None or request.limit_price <= 0:
                return ExecutionResult(False, reason="Limit inválido")
            if side == OrderSide.BUY:
                if quote.ask > request.limit_price:
                    return ExecutionResult(False, reason="Ask sobre límite")
                raw = min(quote.ask, request.limit_price)
            else:
                if quote.bid < request.limit_price:
                    return ExecutionResult(False, reason="Bid bajo límite")
                raw = max(quote.bid, request.limit_price)
        else:
            return ExecutionResult(False, reason=f"Tipo no soportado en backtest: {otype}")

        slip = raw * self.slippage_bps / Decimal("10000")
        price = raw + slip if side == OrderSide.BUY else raw - slip
        if price <= 0:
            return ExecutionResult(False, reason="Precio post-slippage inválido")
        notional = price * fill_qty
        commission = notional * self.commission_rate
        return ExecutionResult(
            True,
            quantity=fill_qty,
            price=price,
            slippage=slip * fill_qty,
            commission=commission,
            partial=partial,
        )

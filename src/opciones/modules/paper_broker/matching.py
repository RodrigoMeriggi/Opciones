"""Motor de matching simulado para PaperBroker."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from opciones.domain.enums import OrderSide, OrderType
from opciones.domain.models import MarketQuote, OrderRequest


@dataclass
class MatchResult:
    can_fill: bool
    fill_price: Decimal | None = None
    fill_quantity: int = 0
    reason: str | None = None
    slippage: Decimal = Decimal("0")


class SimulatedMatchingEngine:
    """Matching basado en bid/ask, liquidez y slippage configurable."""

    def __init__(
        self,
        slippage_bps: Decimal = Decimal("5"),
        allow_partial: bool = True,
        default_available_size: int = 50,
    ) -> None:
        self.slippage_bps = slippage_bps
        self.allow_partial = allow_partial
        self.default_available_size = default_available_size

    def match(self, request: OrderRequest, quote: MarketQuote | None) -> MatchResult:
        if quote is None:
            return MatchResult(False, reason="Sin cotización")
        if quote.bid is None or quote.ask is None:
            return MatchResult(False, reason="Cotización sin bid/ask")
        if quote.ask <= 0:
            return MatchResult(False, reason="Ask inválido")
        if quote.bid > quote.ask:
            return MatchResult(False, reason="Cruzado bid>ask")

        available = quote.ask_size or quote.bid_size or self.default_available_size
        if available <= 0:
            return MatchResult(False, reason="Sin liquidez")

        side = request.side.upper()
        otype = request.order_type.upper()
        qty = request.quantity

        if otype == OrderType.MARKET:
            return self._match_market(side, qty, quote, available)
        if otype == OrderType.LIMIT:
            return self._match_limit(side, qty, request.limit_price, quote, available)
        if otype == OrderType.STOP_MARKET:
            return self._match_stop_market(side, qty, request.stop_price, quote, available)
        if otype == OrderType.STOP_LIMIT:
            return self._match_stop_limit(
                side, qty, request.stop_price, request.limit_price, quote, available
            )
        return MatchResult(False, reason=f"Tipo de orden no soportado: {otype}")

    def _apply_slippage(self, price: Decimal, side: str) -> tuple[Decimal, Decimal]:
        slip = price * self.slippage_bps / Decimal("10000")
        if side == OrderSide.BUY:
            return price + slip, slip
        return price - slip, slip

    def _qty(self, requested: int, available: int) -> tuple[int, str | None]:
        if available <= 0:
            return 0, "Sin liquidez"
        if requested <= available:
            return requested, None
        if self.allow_partial:
            return available, None
        return 0, "Liquidez insuficiente para fill completo"

    def _match_market(
        self, side: str, qty: int, quote: MarketQuote, available: int
    ) -> MatchResult:
        fill_qty, reason = self._qty(qty, available)
        if fill_qty <= 0:
            return MatchResult(False, reason=reason or "Sin fill")
        raw = quote.ask if side == OrderSide.BUY else quote.bid
        assert raw is not None
        price, slip = self._apply_slippage(raw, side)
        if price <= 0:
            return MatchResult(False, reason="Precio resultante inválido")
        return MatchResult(True, fill_price=price, fill_quantity=fill_qty, slippage=slip)

    def _match_limit(
        self,
        side: str,
        qty: int,
        limit: Decimal | None,
        quote: MarketQuote,
        available: int,
    ) -> MatchResult:
        if limit is None or limit <= 0:
            return MatchResult(False, reason="Limit price inválido")
        assert quote.ask is not None and quote.bid is not None
        if side == OrderSide.BUY:
            if quote.ask > limit:
                return MatchResult(False, reason="Ask por encima del límite")
            raw = min(quote.ask, limit)
        else:
            if quote.bid < limit:
                return MatchResult(False, reason="Bid por debajo del límite")
            raw = max(quote.bid, limit)
        fill_qty, reason = self._qty(qty, available)
        if fill_qty <= 0:
            return MatchResult(False, reason=reason or "Sin fill")
        return MatchResult(True, fill_price=raw, fill_quantity=fill_qty)

    def _match_stop_market(
        self,
        side: str,
        qty: int,
        stop: Decimal | None,
        quote: MarketQuote,
        available: int,
    ) -> MatchResult:
        if stop is None or stop <= 0:
            return MatchResult(False, reason="Stop price inválido")
        last = quote.last or quote.mid
        if last is None:
            return MatchResult(False, reason="Sin last/mid para stop")
        triggered = (side == OrderSide.SELL and last <= stop) or (
            side == OrderSide.BUY and last >= stop
        )
        if not triggered:
            return MatchResult(False, reason="Stop no disparado")
        return self._match_market(side, qty, quote, available)

    def _match_stop_limit(
        self,
        side: str,
        qty: int,
        stop: Decimal | None,
        limit: Decimal | None,
        quote: MarketQuote,
        available: int,
    ) -> MatchResult:
        if stop is None or stop <= 0:
            return MatchResult(False, reason="Stop price inválido")
        last = quote.last or quote.mid
        if last is None:
            return MatchResult(False, reason="Sin last/mid para stop")
        triggered = (side == OrderSide.SELL and last <= stop) or (
            side == OrderSide.BUY and last >= stop
        )
        if not triggered:
            return MatchResult(False, reason="Stop no disparado")
        return self._match_limit(side, qty, limit, quote, available)

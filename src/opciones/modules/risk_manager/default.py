"""Simplificación del RiskManager: validación clara compra vs reducción."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from opciones.domain.enums import CircuitBreakerReason, OrderSide, RejectionCode
from opciones.domain.models import (
    MarketQuote,
    OptionContract,
    OrderRequest,
    PortfolioSnapshot,
    Position,
    RiskLimits,
    RiskValidationResult,
)
from opciones.modules.configuration import Settings, get_settings
from opciones.modules.instruments.symbols import percentage_spread
from opciones.ports import RiskManager


class DefaultRiskManager(RiskManager):
    def __init__(
        self,
        limits: RiskLimits | None = None,
        settings: Settings | None = None,
        authorized_underlyings: list[str] | None = None,
        *,
        ignore_market_hours: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.limits = limits or self.settings.to_risk_limits()
        # Completar límites no cubiertos por settings básicos
        if limits is None:
            base = self.settings.to_risk_limits()
            self.limits = base
        self.authorized = {
            s.upper() for s in (authorized_underlyings or self.settings.authorized_underlyings)
        }
        self.ignore_market_hours = ignore_market_hours
        self._circuit_breaker_active = bool(self.settings.emergency_stop)
        self._circuit_breaker_reason: str | None = (
            CircuitBreakerReason.EMERGENCY_STOP if self.settings.emergency_stop else None
        )
        self._circuit_breaker_detail: str | None = (
            "EMERGENCY_STOP=true al iniciar" if self.settings.emergency_stop else None
        )
        self._api_error_count = 0
        self._rejection_count = 0
        self._audit: list[dict[str, Any]] = []
        self._manual_unlock_token = "MANUAL_UNLOCK_CONFIRMED"

    def get_limits(self) -> RiskLimits:
        return self.limits

    def is_buying_blocked(self) -> bool:
        return self._circuit_breaker_active or self.settings.emergency_stop

    def activate_circuit_breaker(self, reason: str, detail: str) -> None:
        self._circuit_breaker_active = True
        self._circuit_breaker_reason = reason
        self._circuit_breaker_detail = detail
        self._audit.append(
            {
                "event": "circuit_breaker_activated",
                "reason": reason,
                "detail": detail,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def reset_circuit_breaker(self, manual_confirmation: str) -> None:
        if manual_confirmation != self._manual_unlock_token:
            raise PermissionError("Se requiere confirmación manual válida para desbloquear")
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None
        self._circuit_breaker_detail = None
        self._api_error_count = 0
        self._rejection_count = 0
        # También desactivar emergency en settings de instancia (no cambia env global)
        object.__setattr__(self.settings, "emergency_stop", False)
        self._audit.append(
            {"event": "circuit_breaker_reset", "timestamp": datetime.utcnow().isoformat()}
        )

    def record_api_error(self) -> None:
        self._api_error_count += 1
        if self._api_error_count >= 5:
            self.activate_circuit_breaker(
                CircuitBreakerReason.API_ERRORS,
                f"{self._api_error_count} errores consecutivos de API",
            )

    def record_rejection(self) -> None:
        self._rejection_count += 1
        if self._rejection_count >= 10:
            self.activate_circuit_breaker(
                CircuitBreakerReason.REPEATED_REJECTIONS,
                f"{self._rejection_count} rechazos repetidos",
            )

    def size_position(
        self,
        request: OrderRequest,
        quote: MarketQuote,
        portfolio: PortfolioSnapshot,
        stop_loss_price: Decimal | None = None,
    ) -> int:
        price = quote.ask or quote.last
        if price is None or price <= 0:
            return 0
        by_pct = int((portfolio.equity * self.limits.maximum_position_percentage) / price)
        by_loss = int(self.limits.maximum_loss_per_trade / price) if price else 0
        remaining_premium = self.limits.maximum_total_premium - portfolio.total_premium
        by_premium_cap = int(max(Decimal("0"), remaining_premium) / price)
        by_cash = int(
            max(Decimal("0"), portfolio.available_cash - self.limits.minimum_cash_reserve)
            / (price * Decimal("1.002"))
        )
        by_liquidity = quote.ask_size or 50
        candidates = [c for c in [by_pct, by_loss, by_premium_cap, by_cash, by_liquidity] if c >= 0]
        if stop_loss_price is not None and 0 < stop_loss_price < price:
            risk_per = price - stop_loss_price
            candidates.append(int(self.limits.maximum_loss_per_trade / risk_per))
        sized = max(0, min(candidates)) if candidates else 0
        return min(sized, request.quantity) if request.quantity else sized

    async def validate_order(
        self,
        request: OrderRequest,
        quote: MarketQuote | None,
        portfolio: PortfolioSnapshot,
        positions: list[Position],
        contract: OptionContract | None = None,
    ) -> RiskValidationResult:
        audit: list[dict[str, Any]] = []
        codes: list[str] = []
        messages: list[str] = []

        def fail(code: RejectionCode, msg: str) -> None:
            codes.append(code.value)
            messages.append(msg)
            audit.append({"check": code.value, "passed": False, "message": msg})

        def ok(check: str, msg: str = "ok") -> None:
            audit.append({"check": check, "passed": True, "message": msg})

        side = request.side.upper()
        is_buy = side == OrderSide.BUY
        is_sell = side == OrderSide.SELL

        # --- checks comunes ---
        if request.quantity <= 0 or request.quantity != int(request.quantity):
            fail(RejectionCode.INVALID_QUANTITY, "Cantidad debe ser entero positivo")
        else:
            ok("quantity")

        if request.limit_price is not None and request.limit_price <= 0:
            fail(RejectionCode.INVALID_PRICE, "Precio límite debe ser positivo")
        else:
            ok("price")

        if self.settings.trading_mode.value == "live" and not self.settings.is_live_trading_allowed():
            fail(RejectionCode.LIVE_TRADING_DISABLED, "Trading real no habilitado")

        # Ventas: solo cubrir, permitir durante circuit breaker
        if is_sell:
            held = next((p for p in positions if p.symbol == request.symbol), None)
            if held is None or held.quantity < request.quantity:
                fail(RejectionCode.NAKED_SHORT_FORBIDDEN, "Venta descubierta prohibida")
            else:
                ok("covered_sell")
            if quote is None:
                fail(RejectionCode.MISSING_DATA, "Sin cotización")
            elif quote.quality(self.limits.max_quote_age_seconds).value == "INVALID":
                fail(RejectionCode.INVALID_QUOTE, "Cotización inválida")
            else:
                ok("quote_quality")

            approved = len(codes) == 0
            result = RiskValidationResult(
                approved=approved,
                codes=codes,
                messages=messages,
                suggested_quantity=request.quantity,
                exposure_metrics=self._exposure(portfolio),
                audit_trail=audit,
            )
            self._audit.append(
                {"symbol": request.symbol, "side": side, "approved": approved, "codes": codes}
            )
            return result

        # --- compras ---
        if self.settings.emergency_stop or self._circuit_breaker_active:
            reason = self._circuit_breaker_reason or CircuitBreakerReason.EMERGENCY_STOP
            code = (
                RejectionCode.EMERGENCY_STOP
                if self.settings.emergency_stop
                else RejectionCode.CIRCUIT_BREAKER
            )
            fail(code, f"Compras bloqueadas: {reason}")

        und = (
            request.underlying_symbol
            or (contract.underlying_symbol if contract else "")
            or ""
        ).upper()
        if und and und not in self.authorized:
            fail(RejectionCode.ASSET_NOT_AUTHORIZED, f"{und} no autorizado")
        elif und:
            ok("authorized_asset", und)

        if not self.ignore_market_hours and not self._within_market_hours():
            fail(RejectionCode.MARKET_CLOSED, "Fuera de horario de operación")
        else:
            ok("market_hours")

        if quote is None:
            fail(RejectionCode.MISSING_DATA, "Sin cotización")
        else:
            q_quality = quote.quality(self.limits.max_quote_age_seconds)
            if q_quality.value in {"INVALID", "MISSING"}:
                fail(RejectionCode.INVALID_QUOTE, f"Cotización {q_quality}")
            elif q_quality.value == "STALE":
                fail(RejectionCode.STALE_QUOTE, "Cotización desactualizada")
                self.activate_circuit_breaker(
                    CircuitBreakerReason.STALE_MARKET_DATA, f"Quote stale: {request.symbol}"
                )
            else:
                ok("quote_quality")

            spread = percentage_spread(quote.bid, quote.ask)
            if spread is not None and spread > self.limits.maximum_bid_ask_spread_percentage:
                fail(RejectionCode.SPREAD_TOO_WIDE, f"Spread {spread}%")
            else:
                ok("spread")

            vol = quote.volume if quote.volume is not None else (contract.volume if contract else None)
            if vol is not None and vol < self.limits.minimum_volume:
                fail(RejectionCode.LOW_VOLUME, f"Volumen {vol}")
            else:
                ok("volume")

        dte = None
        if contract and contract.days_to_expiration is not None:
            dte = contract.days_to_expiration
        elif request.expiration_date:
            dte = (request.expiration_date - datetime.utcnow().date()).days
        if dte is not None:
            if dte < self.limits.minimum_days_to_expiration:
                fail(RejectionCode.EXPIRATION_TOO_NEAR, f"DTE={dte}")
            elif dte > self.limits.maximum_days_to_expiration:
                fail(RejectionCode.EXPIRATION_TOO_FAR, f"DTE={dte}")
            else:
                ok("expiration", f"DTE={dte}")

        if portfolio.daily_pnl <= -self.limits.maximum_daily_loss:
            self.activate_circuit_breaker(
                CircuitBreakerReason.DAILY_LOSS, f"Daily PnL {portfolio.daily_pnl}"
            )
            fail(RejectionCode.MAX_DAILY_LOSS, "Pérdida diaria máxima alcanzada")
        else:
            ok("daily_loss")

        if portfolio.weekly_pnl <= -self.limits.maximum_weekly_loss:
            fail(RejectionCode.MAX_WEEKLY_LOSS, "Pérdida semanal máxima")
        else:
            ok("weekly_loss")

        if portfolio.drawdown >= self.limits.maximum_drawdown:
            self.activate_circuit_breaker(
                CircuitBreakerReason.MAX_DRAWDOWN, f"Drawdown {portfolio.drawdown}"
            )
            fail(RejectionCode.MAX_DRAWDOWN, "Drawdown máximo")
        else:
            ok("drawdown")

        if portfolio.consecutive_losses >= self.limits.maximum_consecutive_losses:
            fail(RejectionCode.MAX_CONSECUTIVE_LOSSES, "Demasiadas pérdidas consecutivas")
        else:
            ok("consecutive_losses")

        if portfolio.trades_today >= self.limits.daily_trade_limit:
            fail(RejectionCode.DAILY_TRADE_LIMIT, "Límite diario de trades")
        else:
            ok("daily_trade_limit")

        if portfolio.last_loss_at is not None and self.limits.cooldown_after_loss_minutes > 0:
            elapsed = (datetime.utcnow() - portfolio.last_loss_at.replace(tzinfo=None)).total_seconds()
            if elapsed < self.limits.cooldown_after_loss_minutes * 60:
                fail(RejectionCode.COOLDOWN_ACTIVE, "Cooldown post-pérdida activo")
            else:
                ok("cooldown")
        else:
            ok("cooldown")

        if portfolio.open_positions >= self.limits.maximum_open_positions:
            fail(RejectionCode.MAX_OPEN_POSITIONS, "Máximo de posiciones abiertas")
        else:
            ok("open_positions")

        if und:
            count = portfolio.positions_by_underlying.get(und, 0)
            if count >= self.limits.maximum_positions_per_underlying:
                fail(RejectionCode.MAX_POSITIONS_PER_UNDERLYING, f"Máximo por subyacente {und}")
            else:
                ok("per_underlying")

        estimated_premium = None
        estimated_commission = None
        suggested = request.quantity
        if quote and quote.ask and quote.ask > 0:
            estimated_premium = quote.ask * request.quantity
            estimated_commission = estimated_premium * Decimal("0.001")
            total = estimated_premium + estimated_commission
            if total > portfolio.available_cash:
                fail(RejectionCode.INSUFFICIENT_CASH, "Saldo insuficiente")
            else:
                ok("cash")
            if portfolio.available_cash - total < self.limits.minimum_cash_reserve:
                fail(RejectionCode.MIN_CASH_RESERVE, "Reserva de caja insuficiente")
            else:
                ok("cash_reserve")
            if portfolio.total_premium + estimated_premium > self.limits.maximum_total_premium:
                fail(RejectionCode.MAX_TOTAL_PREMIUM, "Prima total máxima")
            else:
                ok("total_premium")
            max_notional = portfolio.equity * self.limits.maximum_position_percentage
            if estimated_premium > max_notional:
                fail(RejectionCode.MAX_POSITION_SIZE, "Tamaño de posición excedido")
            else:
                ok("position_size")
            if estimated_premium > self.limits.maximum_capital_at_risk:
                fail(RejectionCode.MAX_EXPOSURE, "Exposición total excedida")
            else:
                ok("exposure")
            suggested = self.size_position(request, quote, portfolio)

        approved = len(codes) == 0
        result = RiskValidationResult(
            approved=approved,
            codes=codes,
            messages=messages,
            suggested_quantity=suggested,
            estimated_premium=estimated_premium,
            estimated_commission=estimated_commission,
            exposure_metrics=self._exposure(portfolio),
            audit_trail=audit,
        )
        self._audit.append(
            {"symbol": request.symbol, "side": side, "approved": approved, "codes": codes}
        )
        if not approved:
            self.record_rejection()
        return result

    def _exposure(self, portfolio: PortfolioSnapshot) -> dict[str, Any]:
        return {
            "equity": str(portfolio.equity),
            "cash": str(portfolio.cash),
            "drawdown": str(portfolio.drawdown),
            "daily_pnl": str(portfolio.daily_pnl),
            "open_positions": portfolio.open_positions,
            "circuit_breaker": self._circuit_breaker_active,
            "circuit_breaker_reason": self._circuit_breaker_reason,
        }

    def _within_market_hours(self) -> bool:
        try:
            tz = ZoneInfo(self.settings.timezone)
            now = datetime.now(tz).time()
        except Exception:
            now = datetime.utcnow().time()
        open_t = time(self.settings.market_open_hour, 0)
        close_t = time(self.settings.market_close_hour, 0)
        return open_t <= now <= close_t

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

"""BasicOptionStrategy — estrategia simple, parametrizable y explicable."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from opciones.domain.enums import OptionType, OrderSide, SignalAction, TrendDirection
from opciones.domain.models import (
    DecisionRecord,
    MarketQuote,
    OptionChain,
    OptionContract,
    PortfolioSnapshot,
    Position,
    UnderlyingAsset,
)
from opciones.modules.option_chain.quality import QualityFilters, assess_operability
from opciones.modules.instruments.universe import load_byma_universe
from opciones.modules.strategy_engine.indicators import attach_iv_if_available, compute_indicators
from opciones.modules.strategy_engine.scoring import score_contract
from opciones.ports import RiskManager, Strategy


class BasicOptionStrategy(Strategy):
    """
    Solo compra calls/puts y vende posiciones largas.
    No lanza opciones ni crea shorts.
    No promete rentabilidad.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.risk_manager = risk_manager
        self.config = {
            "strategy_id": "basic_option_v1",
            "authorized_underlyings": load_byma_universe().symbols,
            "min_dte": 5,
            "max_dte": 45,
            "calls_enabled": True,
            "puts_enabled": True,
            "min_volume": 10,
            "max_spread_pct": 8.0,
            "max_capital_per_signal": 50000,
            "rsi_min": 30,
            "rsi_max": 70,
            "min_momentum_pct": 0.5,
            "fast_ma": 10,
            "slow_ma": 30,
            "take_profit_pct": 30.0,
            "stop_loss_pct": 20.0,
            "trailing_stop_pct": 15.0,
            "max_holding_days": 15,
            "min_seconds_between_trades": 300,
            "max_daily_trades": 10,
            "cooldown_after_loss_minutes": 30,
            "signal_confirm_cycles": 2,
            "atm_preference_pct": 5.0,
            **(config or {}),
        }
        self._last_trade_at: datetime | None = None
        self._recent_symbols: dict[str, datetime] = {}
        self._signal_counts: dict[str, int] = {}
        self._discarded: list[DecisionRecord] = []
        self._high_water: dict[str, Decimal] = {}

    @property
    def strategy_id(self) -> str:
        return str(self.config["strategy_id"])

    @property
    def discarded_signals(self) -> list[DecisionRecord]:
        return list(self._discarded)

    async def evaluate(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        decisions: list[DecisionRecord] = []
        indicators = compute_indicators(
            historical,
            fast_period=int(self.config["fast_ma"]),
            slow_period=int(self.config["slow_ma"]),
        )
        trend = indicators.get("trend", "UNKNOWN")

        if self.risk_manager.is_buying_blocked():
            rec = self._discard(
                underlying.symbol,
                indicators,
                "Circuit breaker / emergency stop activo",
                ["circuit_breaker_clear"],
            )
            decisions.append(rec)
            return decisions

        if underlying.symbol.upper() not in {
            s.upper() for s in self.config["authorized_underlyings"]
        }:
            decisions.append(
                self._discard(underlying.symbol, indicators, "Subyacente no autorizado", ["authorized"])
            )
            return decisions

        # Overtrading guards
        if portfolio.trades_today >= int(self.config["max_daily_trades"]):
            decisions.append(
                self._discard(underlying.symbol, indicators, "Máximo diario de operaciones", ["daily_limit"])
            )
            return decisions

        if self._last_trade_at:
            elapsed = (datetime.utcnow() - self._last_loss_safe()).total_seconds()
            # use last trade
            elapsed = (datetime.utcnow() - self._last_trade_at).total_seconds()
            if elapsed < int(self.config["min_seconds_between_trades"]):
                decisions.append(
                    self._discard(underlying.symbol, indicators, "Tiempo mínimo entre trades", ["min_interval"])
                )
                return decisions

        candidates: list[tuple[OptionContract, dict, Decimal]] = []
        quality = QualityFilters(
            max_spread_pct=Decimal(str(self.config["max_spread_pct"])),
            min_volume=int(self.config["min_volume"]),
            min_days_to_expiration=int(self.config["min_dte"]),
            max_days_to_expiration=int(self.config["max_dte"]),
        )

        want_calls = (
            self.config["calls_enabled"]
            and trend == TrendDirection.BULLISH
            and self._momentum_ok(indicators, bullish=True)
            and self._rsi_ok(indicators)
        )
        want_puts = (
            self.config["puts_enabled"]
            and trend == TrendDirection.BEARISH
            and self._momentum_ok(indicators, bullish=False)
            and self._rsi_ok(indicators)
        )

        if not want_calls and not want_puts:
            decisions.append(
                self._discard(
                    underlying.symbol,
                    indicators,
                    f"Sin setup direccional (trend={trend})",
                    ["trend", "momentum", "rsi"],
                )
            )
            return decisions

        for contract in chain.contracts:
            if contract.option_type == OptionType.CALL and not want_calls:
                continue
            if contract.option_type == OptionType.PUT and not want_puts:
                continue

            oper = assess_operability(contract, quality)
            if not oper.operable:
                self._discarded.append(
                    DecisionRecord(
                        strategy_id=self.strategy_id,
                        contract_symbol=contract.symbol,
                        underlying_symbol=underlying.symbol,
                        action=SignalAction.DISCARD,
                        indicators=indicators,
                        rules_failed=oper.reasons,
                        discard_reason="; ".join(oper.reasons),
                    )
                )
                continue

            # No recomprar el mismo contrato inmediatamente
            last_seen = self._recent_symbols.get(contract.symbol)
            if last_seen and (datetime.utcnow() - last_seen).total_seconds() < 3600:
                continue

            premium = contract.ask
            if premium is None or premium <= 0:
                continue
            if premium > Decimal(str(self.config["max_capital_per_signal"])):
                continue

            ind = attach_iv_if_available(indicators, contract.implied_volatility)
            scored = score_contract(contract, underlying.last_price, ind, self.config)
            candidates.append((contract, scored, premium))

        if not candidates:
            decisions.append(
                self._discard(underlying.symbol, indicators, "Sin contratos candidatos", ["liquidity_filters"])
            )
            return decisions

        candidates.sort(key=lambda x: x[1]["total"], reverse=True)
        best, score_info, premium = candidates[0]

        # Confirmación multi-ciclo
        key = f"{best.symbol}:{best.option_type}"
        self._signal_counts[key] = self._signal_counts.get(key, 0) + 1
        if self._signal_counts[key] < int(self.config["signal_confirm_cycles"]):
            decisions.append(
                DecisionRecord(
                    strategy_id=self.strategy_id,
                    contract_symbol=best.symbol,
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD,
                    indicators=indicators,
                    score=Decimal(str(score_info["total"])),
                    score_components=score_info["components"],
                    rules_passed=["candidate_selected"],
                    rules_failed=["awaiting_confirmation"],
                    discard_reason=f"Confirmación {self._signal_counts[key]}/{self.config['signal_confirm_cycles']}",
                    expected_price=premium,
                    correlation_id=str(uuid4()),
                )
            )
            return decisions

        # RiskManager obligatorio
        from opciones.domain.models import OrderRequest

        qty = max(1, int(Decimal(str(self.config["max_capital_per_signal"])) / premium))
        req = OrderRequest(
            symbol=best.symbol,
            side=OrderSide.BUY,
            order_type="MARKET",
            quantity=qty,
            underlying_symbol=underlying.symbol,
            expiration_date=best.expiration_date,
            option_type=best.option_type,
            strategy_id=self.strategy_id,
        )
        risk = await self.risk_manager.validate_order(
            req,
            best.to_quote(),
            portfolio,
            positions,
            contract=best,
        )
        if not risk.approved:
            decisions.append(
                DecisionRecord(
                    strategy_id=self.strategy_id,
                    contract_symbol=best.symbol,
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.DISCARD,
                    indicators=indicators,
                    score=Decimal(str(score_info["total"])),
                    score_components=score_info["components"],
                    rules_failed=risk.codes,
                    discard_reason="; ".join(risk.messages),
                    estimated_risk=risk.estimated_premium,
                    expected_price=premium,
                )
            )
            self._discarded.append(decisions[-1])
            return decisions

        final_qty = risk.suggested_quantity or qty
        self._signal_counts[key] = 0
        self._last_trade_at = datetime.utcnow()
        self._recent_symbols[best.symbol] = datetime.utcnow()

        decisions.append(
            DecisionRecord(
                strategy_id=self.strategy_id,
                contract_symbol=best.symbol,
                underlying_symbol=underlying.symbol,
                action=SignalAction.BUY,
                indicators=indicators,
                score=Decimal(str(score_info["total"])),
                score_components=score_info["components"],
                rules_passed=["trend", "momentum", "rsi", "liquidity", "risk_approved"],
                entry_reason=(
                    f"Compra {best.option_type} por tendencia {trend}; "
                    f"score={score_info['total']:.2f}"
                ),
                estimated_risk=premium * final_qty,
                expected_price=premium,
                correlation_id=str(uuid4()),
            )
        )
        decisions[-1].indicators = {
            **indicators,
            "suggested_quantity": final_qty,
            "order_side": OrderSide.BUY,
            "order_type": "MARKET",
        }
        return decisions

    async def evaluate_exits(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        indicators = compute_indicators(historical)
        decisions: list[DecisionRecord] = []
        trend = indicators.get("trend")

        for pos in positions:
            if pos.underlying_symbol.upper() != underlying.symbol.upper():
                continue
            quote = quotes.get(pos.symbol)
            mark = None
            if quote:
                mark = quote.bid or quote.last or quote.mid
            if mark is None:
                mark = pos.current_price or pos.average_price

            hw = self._high_water.get(pos.symbol, mark)
            if mark > hw:
                hw = mark
                self._high_water[pos.symbol] = hw

            pnl_pct = float((mark - pos.average_price) / pos.average_price * 100)
            dte = (pos.expiration_date - datetime.utcnow().date()).days
            holding_days = (datetime.utcnow() - pos.opened_at.replace(tzinfo=None)).days
            reasons: list[str] = []

            if pnl_pct >= float(self.config["take_profit_pct"]):
                reasons.append("take_profit")
            if pnl_pct <= -float(self.config["stop_loss_pct"]):
                reasons.append("stop_loss")
            trail = float((hw - mark) / hw * 100) if hw > 0 else 0
            if trail >= float(self.config["trailing_stop_pct"]) and pnl_pct > 0:
                reasons.append("trailing_stop")
            if holding_days >= int(self.config["max_holding_days"]):
                reasons.append("max_holding_time")
            if dte <= int(self.risk_manager.get_limits().force_exit_days_before_expiration):
                reasons.append("near_expiration")
            if quote and quote.volume is not None and quote.volume < int(self.config["min_volume"]):
                reasons.append("liquidity_lost")
            if pos.option_type == OptionType.CALL and trend == TrendDirection.BEARISH:
                reasons.append("trend_reversal")
            if pos.option_type == OptionType.PUT and trend == TrendDirection.BULLISH:
                reasons.append("trend_reversal")
            if portfolio.daily_pnl <= -self.risk_manager.get_limits().maximum_daily_loss:
                reasons.append("daily_loss_limit")
            if self.risk_manager.is_buying_blocked():
                # CB no fuerza salida automática siempre, pero estrategia puede cerrar por riesgo
                pass

            if reasons:
                decisions.append(
                    DecisionRecord(
                        strategy_id=self.strategy_id,
                        contract_symbol=pos.symbol,
                        underlying_symbol=pos.underlying_symbol,
                        action=SignalAction.SELL,
                        indicators={
                            **indicators,
                            "pnl_pct": pnl_pct,
                            "suggested_quantity": pos.quantity,
                            "order_side": OrderSide.SELL,
                            "order_type": "MARKET",
                        },
                        rules_passed=reasons,
                        exit_reason="; ".join(reasons),
                        expected_price=mark,
                        correlation_id=str(uuid4()),
                    )
                )
                self._high_water.pop(pos.symbol, None)
        return decisions

    def _rsi_ok(self, ind: dict) -> bool:
        rsi = ind.get("rsi")
        if rsi is None:
            return False
        return float(self.config["rsi_min"]) <= rsi <= float(self.config["rsi_max"])

    def _momentum_ok(self, ind: dict, bullish: bool) -> bool:
        mom = ind.get("momentum_pct")
        if mom is None:
            return False
        thr = float(self.config["min_momentum_pct"])
        return mom >= thr if bullish else mom <= -thr

    def _last_loss_safe(self) -> datetime:
        return self._last_trade_at or datetime.utcnow()

    def _discard(
        self,
        underlying: str,
        indicators: dict,
        reason: str,
        failed: list[str],
    ) -> DecisionRecord:
        rec = DecisionRecord(
            strategy_id=self.strategy_id,
            underlying_symbol=underlying,
            action=SignalAction.DISCARD,
            indicators=indicators,
            rules_failed=failed,
            discard_reason=reason,
        )
        self._discarded.append(rec)
        return rec

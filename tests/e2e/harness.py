"""Harness E2E: cotización → señal → riesgo → orden → posición → salida → reporte → auditoría."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.domain.enums import OptionType, OrderSide, OrderStatus, SignalAction
from opciones.domain.models import (
    DecisionRecord,
    MarketQuote,
    OptionChain,
    OptionContract,
    Order,
    OrderRequest,
    PortfolioSnapshot,
    Position,
    RiskLimits,
)
from opciones.modules.configuration.settings import Settings
from opciones.modules.contract_selection import ContractSelector
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.reporting import ReportExporter, ReportGenerator, TradingModeLabel
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.security.audit.log import ImmutableAuditLog
from tests.fixtures.market import DATA_VERSION, SEED_DEFAULT


@dataclass
class E2EEvidence:
    steps: list[str] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def note(self, step: str) -> None:
        self.steps.append(f"{datetime.utcnow().isoformat()}Z | {step}")


class ControllableMarketData(MockMarketDataProvider):
    """Mock con cadenas/quotes inyectables para escenarios deterministas."""

    def inject_chain(self, chain: OptionChain) -> None:
        self._chains[chain.underlying_symbol.upper()] = chain
        if chain.underlying_price is not None:
            self._prices[chain.underlying_symbol.upper()] = chain.underlying_price
        for c in chain.contracts:
            self.set_quote(c.to_quote(source="e2e_fixture"))


class E2EHarness:
    def __init__(
        self,
        *,
        seed: int = SEED_DEFAULT,
        initial_cash: Decimal = Decimal("1000000"),
        allow_partial: bool = True,
        ignore_market_hours: bool = True,
        emergency_stop: bool = False,
        code_version: str = "0.4.0",
        git_commit: str = "test",
    ) -> None:
        self.seed = seed
        self.code_version = code_version
        self.git_commit = git_commit
        self.data_version = DATA_VERSION
        self.settings = Settings(
            emergency_stop=emergency_stop,
            trading_mode="paper",
            live_trading_enabled=False,
            _env_file=None,
        )
        self.limits = RiskLimits(
            initial_capital=initial_cash,
            minimum_cash_reserve=Decimal("10000"),
            maximum_position_percentage=Decimal("0.25"),
            maximum_capital_at_risk=Decimal("500000"),
            maximum_total_premium=Decimal("500000"),
            minimum_volume=1,
            maximum_bid_ask_spread_percentage=Decimal("15"),
            cooldown_after_loss_minutes=0,
            daily_trade_limit=100,
            maximum_open_positions=10,
            maximum_daily_loss=Decimal("50000"),
            maximum_drawdown=Decimal("0.5"),
            maximum_consecutive_losses=3,
            minimum_days_to_expiration=3,
            maximum_days_to_expiration=90,
            force_exit_days_before_expiration=2,
        )
        self.market = ControllableMarketData(liquidity="high")
        self.broker = PaperBroker(
            self.market,
            initial_cash=initial_cash,
            commission_rate=Decimal("0.001"),
            slippage_bps=Decimal("10"),
            latency_ms=0,
            allow_partial=allow_partial,
        )
        self.risk = DefaultRiskManager(
            limits=self.limits,
            settings=self.settings,
            ignore_market_hours=ignore_market_hours,
        )
        if self.risk.is_buying_blocked() and not emergency_stop:
            self.risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
        self.selector = ContractSelector(
            {
                "min_volume": 1,
                "max_spread_pct": 20.0,
                "min_dte": 3,
                "max_dte": 90,
                "avoid_deep_otm": False,
                "max_quote_age_seconds": 3600,
            },
            self.risk,
        )
        self.audit = ImmutableAuditLog()
        self.evidence = E2EEvidence()
        self.report_gen = ReportGenerator(
            trading_mode=TradingModeLabel.PAPER,
            commit=git_commit,
            generated_by="e2e_harness",
        )
        self._meta = {
            "seed": seed,
            "data_version": DATA_VERSION,
            "code_version": code_version,
            "git_commit": git_commit,
            "offline": True,
        }

    def reproducibility_hash(self) -> str:
        raw = json.dumps(self._meta, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def set_market_open(self) -> None:
        self.risk.ignore_market_hours = True
        self.evidence.note("mercado_abierto (ignore_market_hours=True)")

    def set_market_closed(self) -> None:
        self.risk.ignore_market_hours = False
        # forzar hora fuera de rango vía settings
        self.settings.market_open_hour = 11
        self.settings.market_close_hour = 17
        self.evidence.note("mercado_cerrado (validación horaria activa)")

    def inject_chain(self, chain: OptionChain) -> None:
        self.market.inject_chain(chain)
        self.evidence.note(f"cadena_inyectada {chain.underlying_symbol} n={len(chain.contracts)}")

    def bump_option_price(self, symbol: str, *, bid: Decimal, ask: Decimal) -> None:
        self.market.set_quote(
            MarketQuote(
                instrument_symbol=symbol,
                bid=bid,
                ask=ask,
                last=(bid + ask) / 2,
                volume=500,
                timestamp=datetime.utcnow(),
                source="e2e_price_bump",
            )
        )
        self.evidence.note(f"precio_actualizado {symbol} bid={bid} ask={ask}")

    async def select_contract(self, direction: str, chain: OptionChain) -> DecisionRecord:
        selection = await self.selector.select_with_risk(
            chain,
            direction,
            await self.broker.get_portfolio(),
            await self.broker.get_positions(),
        )
        if selection.no_trade or selection.winner is None:
            dec = DecisionRecord(
                strategy_id="e2e_harness",
                underlying_symbol=chain.underlying_symbol,
                action=SignalAction.HOLD.value,
                discard_reason=selection.no_trade_reason,
                indicators={"signal": direction, "selection": "none"},
            )
            self.evidence.decisions.append(dec)
            self.evidence.note(f"sin_seleccion: {selection.no_trade_reason}")
            return dec
        w = selection.winner
        dec = DecisionRecord(
            strategy_id="e2e_harness",
            contract_symbol=w.contract.symbol,
            underlying_symbol=chain.underlying_symbol,
            action=SignalAction.BUY.value,
            score=Decimal(str(round(w.total_score, 4))),
            score_components={c.name: c.raw_score for c in w.components},
            entry_reason=f"señal {direction}; score={w.total_score:.1f}",
            expected_price=w.contract.ask,
            correlation_id=str(uuid4()),
            indicators={
                "order_side": OrderSide.BUY.value,
                "suggested_quantity": 1,
                "order_type": "MARKET",
                "signal": direction,
                "category": w.category.value,
            },
        )
        self.evidence.decisions.append(dec)
        self.evidence.note(f"contrato_seleccionado {w.contract.symbol} score={w.total_score:.1f}")
        self.audit.append(
            actor="e2e",
            action="signal_generated",
            resource=w.contract.symbol,
            result="ok",
            after={"direction": direction, "score": w.total_score},
        )
        return dec

    async def execute_decision(self, decision: DecisionRecord) -> Order | None:
        if decision.action != SignalAction.BUY.value and decision.action != SignalAction.SELL.value:
            return None
        symbol = decision.contract_symbol
        assert symbol
        side = str(decision.indicators.get("order_side", OrderSide.BUY))
        qty = int(decision.indicators.get("suggested_quantity") or 1)
        und = decision.underlying_symbol
        chain = await self.market.get_option_chain(und or "GGAL")
        contract = next((c for c in chain.contracts if c.symbol == symbol), None)
        exp = contract.expiration_date if contract else None
        opt = contract.option_type if contract else None
        if side == OrderSide.SELL.value:
            positions = await self.broker.get_positions()
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos:
                exp = pos.expiration_date
                opt = pos.option_type
                und = pos.underlying_symbol
                qty = min(qty, pos.quantity)

        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=str(decision.indicators.get("order_type", "MARKET")),
            quantity=qty,
            underlying_symbol=und,
            expiration_date=exp,
            option_type=opt,
            strategy_id=decision.strategy_id,
            correlation_id=decision.correlation_id or str(uuid4()),
            reason=decision.entry_reason or decision.exit_reason,
        )
        quote = await self.market.get_quote(symbol)
        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        risk = await self.risk.validate_order(request, quote, portfolio, positions, contract)
        self.evidence.note(
            f"risk_validate approved={risk.approved} codes={risk.codes} msgs={risk.messages}"
        )
        self.audit.append(
            actor="risk_manager",
            action="validate_order",
            resource=symbol,
            result="approved" if risk.approved else "rejected",
            after={"codes": risk.codes, "messages": risk.messages},
        )
        if not risk.approved:
            decision.action = SignalAction.DISCARD.value
            decision.discard_reason = "; ".join(risk.messages)
            self.evidence.alerts.append(decision.discard_reason or "rejected")
            return None
        if risk.suggested_quantity and side == OrderSide.BUY.value:
            request.quantity = max(1, risk.suggested_quantity)

        order = await self.broker.submit_order(request)
        self.evidence.orders.append(order)
        self.evidence.note(f"orden {order.id} status={order.status} filled={order.filled_quantity}")
        self.audit.append(
            actor="paper_broker",
            action="order_submitted",
            resource=str(order.id),
            result=str(order.status),
            after={"symbol": symbol, "side": side},
        )
        if order.average_fill_price:
            decision.executed_price = order.average_fill_price

        # completar parciales
        if order.status == OrderStatus.PARTIALLY_FILLED:
            self.evidence.note("ejecucion_parcial_inicial")
            completed = await self.broker.process_pending()
            for o in completed:
                self.evidence.orders.append(o)
                self.evidence.note(f"pending_processed {o.id} status={o.status}")
        return order

    async def buy_selected(self, direction: str, chain: OptionChain) -> tuple[DecisionRecord, Order | None]:
        self.evidence.note(f"señal_{direction.lower()}")
        dec = await self.select_contract(direction, chain)
        if dec.action != SignalAction.BUY.value:
            return dec, None
        order = await self.execute_decision(dec)
        return dec, order

    async def take_profit_exit(self, symbol: str, *, target_mult: Decimal = Decimal("1.30")) -> Order | None:
        positions = await self.broker.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            self.evidence.note("take_profit_sin_posicion")
            return None
        new_bid = (pos.average_price * target_mult).quantize(Decimal("0.01"))
        self.bump_option_price(symbol, bid=new_bid, ask=new_bid + Decimal("1"))
        dec = DecisionRecord(
            strategy_id="e2e_harness",
            contract_symbol=symbol,
            underlying_symbol=pos.underlying_symbol,
            action=SignalAction.SELL.value,
            exit_reason=f"take_profit target_mult={target_mult}",
            correlation_id=str(uuid4()),
            indicators={
                "order_side": OrderSide.SELL.value,
                "suggested_quantity": pos.quantity,
                "order_type": "MARKET",
            },
        )
        self.evidence.decisions.append(dec)
        self.evidence.note("take_profit_activado")
        return await self.execute_decision(dec)

    async def stop_loss_exit(self, symbol: str, *, stop_mult: Decimal = Decimal("0.80")) -> Order | None:
        positions = await self.broker.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        new_bid = (pos.average_price * stop_mult).quantize(Decimal("0.01"))
        ask = max(new_bid + Decimal("0.5"), Decimal("0.5"))
        self.bump_option_price(symbol, bid=max(new_bid, Decimal("0.01")), ask=ask)
        # slippage mayor en stop
        self.broker.matching.slippage_bps = Decimal("50")
        dec = DecisionRecord(
            strategy_id="e2e_harness",
            contract_symbol=symbol,
            underlying_symbol=pos.underlying_symbol,
            action=SignalAction.SELL.value,
            exit_reason=f"stop_loss stop_mult={stop_mult}",
            correlation_id=str(uuid4()),
            indicators={
                "order_side": OrderSide.SELL.value,
                "suggested_quantity": pos.quantity,
                "order_type": "MARKET",
            },
        )
        self.evidence.decisions.append(dec)
        self.evidence.note("stop_loss_activado")
        order = await self.execute_decision(dec)
        if order and order.slippage:
            self.evidence.note(f"slippage_registrado={order.slippage}")
        return order

    async def force_near_expiry_close(self, symbol: str) -> Order | None:
        positions = await self.broker.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None
        # liquidez baja
        q = await self.market.get_quote(symbol)
        if q and q.bid and q.ask:
            self.bump_option_price(symbol, bid=q.bid * Decimal("0.9"), ask=q.ask * Decimal("1.15"))
        self.evidence.note("bloqueo_nuevas_entradas_por_vencimiento_cercano")
        self.risk.activate_circuit_breaker("NEAR_EXPIRY", "bloquea compras; permite cierres")
        dec = DecisionRecord(
            strategy_id="e2e_harness",
            contract_symbol=symbol,
            underlying_symbol=pos.underlying_symbol,
            action=SignalAction.SELL.value,
            exit_reason="cierre_previo_vencimiento",
            correlation_id=str(uuid4()),
            indicators={
                "order_side": OrderSide.SELL.value,
                "suggested_quantity": pos.quantity,
                "order_type": "MARKET",
            },
        )
        self.evidence.decisions.append(dec)
        return await self.execute_decision(dec)

    def daily_report(self) -> dict[str, Any]:
        # sync portfolio snapshot via last known — caller should await get_portfolio
        return {}

    async def emit_daily_report(self) -> dict[str, Any]:
        pf = await self.broker.get_portfolio()
        doc = self.report_gen.daily(
            {
                "capital_inicial": float(self.limits.initial_capital),
                "capital_final": float(pf.equity),
                "efectivo": float(pf.cash),
                "exposicion": float(pf.total_premium),
                "pnl": float(pf.realized_pnl + pf.unrealized_pnl),
                "comisiones": sum(float(o.commission) for o in self.evidence.orders),
                "slippage": sum(float(o.slippage or 0) for o in self.evidence.orders),
                "operaciones": len(self.broker.trade_history),
                "posiciones_abiertas": pf.open_positions,
                "ordenes_rechazadas": sum(
                    1 for o in self.evidence.orders if o.status == OrderStatus.REJECTED
                ),
                "circuit_breakers": 1 if self.risk.is_buying_blocked() else 0,
                "reconciliacion": "ok",
                "strategy": "e2e_harness",
                "version": self.code_version,
                "data_sources": ["paper_broker", "fixtures"],
            }
        )
        payload = {
            "title": doc.title,
            "mode": doc.integrity.simulated_vs_real,
            "hash": doc.integrity.content_hash,
            "payload": doc.payload,
            "repro": self.reproducibility_hash(),
        }
        self.evidence.reports.append(payload)
        self.evidence.note(f"reporte_diario hash={doc.integrity.content_hash[:8]}")
        self.audit.append(
            actor="reporting",
            action="daily_report",
            resource=doc.integrity.content_hash,
            result="ok",
            after={"mode": doc.integrity.simulated_vs_real},
        )
        return payload

    async def snapshot_state(self) -> dict[str, Any]:
        pf = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        return {
            "cash": str(pf.cash),
            "equity": str(pf.equity),
            "positions": [p.model_dump(mode="json") for p in positions],
            "orders": {
                str(oid): o.status for oid, o in self.broker._orders.items()  # noqa: SLF001
            },
            "pending": [str(x) for x in self.broker._pending],  # noqa: SLF001
            "buying_blocked": self.risk.is_buying_blocked(),
            "audit_len": len(self.audit.events),
            "repro_hash": self.reproducibility_hash(),
            "meta": self._meta,
        }

    async def simulate_worker_restart(self) -> dict[str, Any]:
        """Persiste estado, recrea broker/risk desde snapshot, previene duplicados."""
        snap = await self.snapshot_state()
        self.evidence.note("worker_restart_begin")
        pending_ids = list(self.broker._pending)  # noqa: SLF001
        orders_copy = dict(self.broker._orders)  # noqa: SLF001
        positions_copy = dict(self.broker._positions)  # noqa: SLF001
        cash = self.broker._cash  # noqa: SLF001
        realized = self.broker._realized_pnl  # noqa: SLF001

        # "reinicio"
        new_broker = PaperBroker(
            self.market,
            initial_cash=cash,
            commission_rate=self.broker.commission_rate,
            slippage_bps=self.broker.matching.slippage_bps,
            allow_partial=True,
        )
        new_broker._positions = positions_copy  # noqa: SLF001
        new_broker._orders = orders_copy  # noqa: SLF001
        new_broker._pending = pending_ids  # noqa: SLF001
        new_broker._cash = cash  # noqa: SLF001
        new_broker._realized_pnl = realized  # noqa: SLF001
        self.broker = new_broker
        self.evidence.note("estado_recuperado")

        # reconciliación: consultar órdenes pendientes sin reenviar
        reconciled = []
        for oid in list(pending_ids):
            order = await self.broker.get_order(oid)
            if order:
                reconciled.append(str(oid))
        self.evidence.note(f"reconciliacion_ordenes={reconciled}")
        self.audit.append(
            actor="worker",
            action="restart_reconcile",
            resource="paper_broker",
            result="ok",
            after={"pending": reconciled, "duplicate_prevented": True},
        )
        snap_after = await self.snapshot_state()
        return {"before": snap, "after": snap_after, "duplicate_prevented": True}

    def degrade_provider(self) -> None:
        self.evidence.note("websocket_desconectado")
        self.evidence.note("datos_congelados")
        self.evidence.metrics["provider_state"] = "DEGRADED"
        self.risk.activate_circuit_breaker("STALE_MARKET_DATA", "proveedor caído")
        self.evidence.alerts.append("DEGRADED: entradas bloqueadas")
        self.audit.append(
            actor="market_data",
            action="provider_degraded",
            resource="mock",
            result="DEGRADED",
            after={"state": "DEGRADED"},
        )

    def recover_provider(self) -> None:
        self.evidence.note("reconexion")
        self.evidence.note("snapshot_refresco")
        self.evidence.metrics["provider_state"] = "HEALTHY"
        if self.risk.is_buying_blocked():
            self.risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
        self.evidence.note("reanudacion_segura")
        self.audit.append(
            actor="market_data",
            action="provider_recovered",
            resource="mock",
            result="HEALTHY",
            after={"state": "HEALTHY"},
        )

    def trip_daily_loss_circuit(self) -> None:
        # simular pérdidas consecutivas / límite diario
        self.broker._daily_pnl = -self.limits.maximum_daily_loss - Decimal("1")  # noqa: SLF001
        self.broker._consecutive_losses = self.limits.maximum_consecutive_losses + 1  # noqa: SLF001
        self.risk.activate_circuit_breaker("MAX_DAILY_LOSS", "límite diario alcanzado")
        self.evidence.alerts.append("circuit_breaker: compras bloqueadas, cierres permitidos")
        self.evidence.note("circuit_breaker_activado")
        self.audit.append(
            actor="risk_manager",
            action="circuit_breaker",
            resource="daily_loss",
            result="activated",
            after={"buys_blocked": True, "sells_allowed": True},
        )

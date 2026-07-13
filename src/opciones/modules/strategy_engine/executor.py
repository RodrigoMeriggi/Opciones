"""Ejecutor paper: conecta estrategia → risk → broker (sin saltarse RiskManager)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from opciones.domain.enums import OrderSide, SignalAction
from opciones.domain.models import DecisionRecord, Order, OrderRequest
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.paper_broker.expiration import ExpirationCloser
from opciones.ports import MarketDataProvider, RiskManager, Strategy


class StrategyExecutor:
    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        broker: PaperBroker,
        market_data: MarketDataProvider,
        expiration_closer: ExpirationCloser | None = None,
    ) -> None:
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.broker = broker
        self.market_data = market_data
        self.expiration_closer = expiration_closer or ExpirationCloser(broker, market_data)
        self.decisions: list[DecisionRecord] = []
        self.orders: list[Order] = []

    async def run_cycle(self, underlying_symbol: str) -> dict[str, Any]:
        exit_results = await self.expiration_closer.close_near_expiration()

        underlying = await self.market_data.get_underlying(underlying_symbol)
        if underlying is None:
            return {"error": f"Subyacente {underlying_symbol} no encontrado"}

        chain = await self.market_data.get_option_chain(underlying_symbol)
        end = datetime.utcnow()
        start = end - timedelta(days=90)
        historical = await self.market_data.get_historical_prices(underlying_symbol, start, end)
        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()

        quotes: dict = {}
        for p in positions:
            q = await self.market_data.get_quote(p.symbol)
            if q:
                quotes[p.symbol] = q

        exit_decisions = await self.strategy.evaluate_exits(
            positions, quotes, underlying, historical, portfolio
        )
        for dec in exit_decisions:
            self.decisions.append(dec)
            if dec.action == SignalAction.SELL and dec.contract_symbol:
                order = await self._execute_decision(dec)
                if order:
                    self.orders.append(order)

        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        entry_decisions = await self.strategy.evaluate(
            chain, underlying, historical, portfolio, positions
        )
        for dec in entry_decisions:
            self.decisions.append(dec)
            if dec.action == SignalAction.BUY and dec.contract_symbol:
                order = await self._execute_decision(dec)
                if order:
                    self.orders.append(order)

        return {
            "underlying": underlying_symbol,
            "forced_exits": exit_results,
            "decisions": len(entry_decisions) + len(exit_decisions),
            "orders_submitted": len(self.orders),
            "portfolio": (await self.broker.get_portfolio()).model_dump(mode="json"),
        }

    async def _execute_decision(self, decision: DecisionRecord) -> Order | None:
        side = str(decision.indicators.get("order_side", OrderSide.BUY))
        qty = int(decision.indicators.get("suggested_quantity") or 1)
        symbol = decision.contract_symbol
        assert symbol

        positions = await self.broker.get_positions()
        und = decision.underlying_symbol
        exp = None
        opt = None
        for p in positions:
            if p.symbol == symbol:
                exp = p.expiration_date
                opt = p.option_type
                und = p.underlying_symbol
                break

        if side in {OrderSide.BUY, "BUY"} and und:
            chain = await self.market_data.get_option_chain(und)
            for c in chain.contracts:
                if c.symbol == symbol:
                    exp = c.expiration_date
                    opt = c.option_type
                    break

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
        quote = await self.market_data.get_quote(symbol)
        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        contract = None
        if und:
            chain = await self.market_data.get_option_chain(und)
            contract = next((c for c in chain.contracts if c.symbol == symbol), None)

        risk = await self.risk_manager.validate_order(
            request, quote, portfolio, positions, contract=contract
        )
        if not risk.approved:
            decision.discard_reason = "; ".join(risk.messages)
            decision.action = SignalAction.DISCARD
            return None
        if risk.suggested_quantity and side in {OrderSide.BUY, "BUY"}:
            request.quantity = max(1, risk.suggested_quantity)

        order = await self.broker.submit_order(request)
        if order.average_fill_price:
            decision.executed_price = order.average_fill_price
        return order

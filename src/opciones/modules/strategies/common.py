"""Helpers compartidos para estrategias basadas en señales + ContractSelector."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from opciones.domain.enums import OrderSide, SignalAction
from opciones.domain.models import (
    DecisionRecord,
    MarketQuote,
    OptionChain,
    Order,
    PortfolioSnapshot,
    Position,
    UnderlyingAsset,
)
from opciones.modules.contract_selection import ContractSelector, SelectionResult
from opciones.modules.strategies.base import StrategyLifecycle, StrategyMeta
from opciones.ports import RiskManager


class SignalDrivenStrategy(StrategyLifecycle):
    def __init__(
        self,
        meta: StrategyMeta,
        risk_manager: RiskManager,
        selector: ContractSelector | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._meta = meta
        self.risk_manager = risk_manager
        self.config = {**(config or {})}
        self.selector = selector or ContractSelector(self.config.get("selector"), risk_manager)
        self._last_explanation: dict[str, Any] = {}
        self._last_chain: OptionChain | None = None
        self._initialized = False

    @property
    def meta(self) -> StrategyMeta:
        return self._meta

    def initialize(self, context: dict[str, Any]) -> None:
        self._initialized = True
        self._last_explanation = {"event": "initialize", "context_keys": list(context.keys())}

    def on_market_data(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        quote: MarketQuote | None,
    ) -> None:
        self._last_chain = chain

    def on_order_update(self, order: Order) -> None:
        self._last_explanation["last_order"] = str(order.id)

    def on_position_update(self, position: Position) -> None:
        self._last_explanation["last_position"] = position.symbol

    def shutdown(self) -> None:
        self._initialized = False

    def explain_last_decision(self) -> dict[str, Any]:
        return dict(self._last_explanation)

    def _direction_from_signal(self, signal: str | None) -> str | None:
        if signal in ("BULLISH", "BUY_CALL"):
            return "BULLISH"
        if signal in ("BEARISH", "BUY_PUT"):
            return "BEARISH"
        return None

    def _selection_to_decisions(
        self,
        selection: SelectionResult,
        indicators: dict[str, Any],
    ) -> list[DecisionRecord]:
        cid = str(uuid4())
        if selection.no_trade or selection.winner is None:
            rec = DecisionRecord(
                strategy_id=f"{self.meta.name}@{self.meta.version}",
                underlying_symbol=selection.underlying_symbol,
                action=SignalAction.HOLD.value,
                indicators=indicators,
                discard_reason=selection.no_trade_reason,
                correlation_id=cid,
                entry_reason="no_trade",
            )
            self._last_explanation = {
                "no_trade": True,
                "reason": selection.no_trade_reason,
                "candidates": len(selection.all_candidates),
                "discards": [
                    {"symbol": c.contract.symbol, "reasons": c.discard_reasons}
                    for c in selection.all_candidates
                    if c.discarded
                ],
            }
            return [rec]

        w = selection.winner
        components = {c.name: {"score": c.raw_score, "why": c.explanation} for c in w.components}
        rec = DecisionRecord(
            strategy_id=f"{self.meta.name}@{self.meta.version}",
            contract_symbol=w.contract.symbol,
            underlying_symbol=selection.underlying_symbol,
            action=SignalAction.BUY.value,
            indicators=indicators,
            score=Decimal(str(round(w.total_score, 4))),
            score_components=components,
            rules_passed=["filters", "score", "selector"],
            entry_reason=(
                f"señal {selection.signal_direction}; score={w.total_score:.1f}; "
                f"categoría={w.category}"
            ),
            expected_price=w.contract.ask,
            correlation_id=cid,
            estimated_risk=w.contract.ask,
        )
        self._last_explanation = {
            "winner": w.contract.symbol,
            "score": w.total_score,
            "runners_up": [r.contract.symbol for r in selection.runners_up],
            "components": components,
            "penalties": w.penalties,
            "assumptions": selection.assumptions,
        }
        return [rec]

    def evaluate_exit(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        # default: no exit logic in base — subclasses override
        return []

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        raise NotImplementedError

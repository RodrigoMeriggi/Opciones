"""Framework de estrategias extendido (Prompt 18)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opciones.domain.models import (
    DecisionRecord,
    MarketQuote,
    OptionChain,
    Order,
    PortfolioSnapshot,
    Position,
    UnderlyingAsset,
)
from opciones.ports import RiskManager, Strategy as LegacyStrategy


@dataclass
class StrategyMeta:
    name: str
    version: str
    parameters: dict[str, Any]
    commit: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    author: str = "system"
    approval_status: str = "paper_only"  # never auto-live
    allowed_environments: list[str] = field(
        default_factory=lambda: ["paper", "backtest", "shadow"]
    )


class StrategyLifecycle(ABC):
    """
    Interfaz completa. Compatible con LegacyStrategy vía adaptador.
    No envía órdenes directamente; no lanza opciones.
    """

    @property
    @abstractmethod
    def meta(self) -> StrategyMeta:
        ...

    @abstractmethod
    def initialize(self, context: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def on_market_data(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        quote: MarketQuote | None,
    ) -> None:
        ...

    @abstractmethod
    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        ...

    @abstractmethod
    def evaluate_exit(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        ...

    @abstractmethod
    def on_order_update(self, order: Order) -> None:
        ...

    @abstractmethod
    def on_position_update(self, position: Position) -> None:
        ...

    @abstractmethod
    def shutdown(self) -> None:
        ...

    @abstractmethod
    def explain_last_decision(self) -> dict[str, Any]:
        ...


class LifecycleToLegacyAdapter(LegacyStrategy):
    """Adapta StrategyLifecycle al puerto Strategy existente (executor/backtest)."""

    def __init__(self, inner: StrategyLifecycle, risk_manager: RiskManager) -> None:
        self.inner = inner
        self.risk_manager = risk_manager

    @property
    def strategy_id(self) -> str:
        return f"{self.inner.meta.name}@{self.inner.meta.version}"

    async def evaluate(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        self.inner.on_market_data(chain, underlying, None)
        return self.inner.generate_signals(chain, underlying, historical, portfolio, positions)

    async def evaluate_exits(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        return self.inner.evaluate_exit(positions, quotes, underlying, historical, portfolio)

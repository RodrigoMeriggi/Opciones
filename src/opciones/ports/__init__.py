"""Puertos (interfaces) de la arquitectura hexagonal."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

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
    RiskValidationResult,
    UnderlyingAsset,
)


class MarketDataProvider(ABC):
    """Proveedor de cotizaciones e instrumentos. Implementaciones: mock, ALyC futura."""

    @abstractmethod
    async def get_underlying(self, symbol: str) -> UnderlyingAsset | None:
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> MarketQuote | None:
        ...

    @abstractmethod
    async def get_option_chain(self, underlying_symbol: str) -> OptionChain:
        ...

    @abstractmethod
    async def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Serie histórica OHLCV. Fuente real pendiente de documentación ALyC."""
        ...

    @abstractmethod
    async def list_underlyings(self) -> list[UnderlyingAsset]:
        ...


class Broker(ABC):
    """Interfaz de broker. PaperBroker es la implementación inicial."""

    @abstractmethod
    async def submit_order(self, request: OrderRequest) -> Order:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: UUID) -> Order:
        ...

    @abstractmethod
    async def get_order(self, order_id: UUID) -> Order | None:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_portfolio(self) -> PortfolioSnapshot:
        ...

    @abstractmethod
    async def get_cash(self) -> Decimal:
        ...


class Strategy(ABC):
    """Estrategia intercambiable de generación de señales."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        ...

    @abstractmethod
    async def evaluate(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        ...

    @abstractmethod
    async def evaluate_exits(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        ...


class RiskManager(ABC):
    """Validación obligatoria de riesgo. Ninguna estrategia puede omitirlo."""

    @abstractmethod
    async def validate_order(
        self,
        request: OrderRequest,
        quote: MarketQuote | None,
        portfolio: PortfolioSnapshot,
        positions: list[Position],
        contract: OptionContract | None = None,
    ) -> RiskValidationResult:
        ...

    @abstractmethod
    def size_position(
        self,
        request: OrderRequest,
        quote: MarketQuote,
        portfolio: PortfolioSnapshot,
        stop_loss_price: Decimal | None = None,
    ) -> int:
        ...

    @abstractmethod
    def is_buying_blocked(self) -> bool:
        ...

    @abstractmethod
    def activate_circuit_breaker(self, reason: str, detail: str) -> None:
        ...

    @abstractmethod
    def reset_circuit_breaker(self, manual_confirmation: str) -> None:
        ...

    @abstractmethod
    def get_limits(self) -> RiskLimits:
        ...


class PortfolioRepository(ABC):
    @abstractmethod
    async def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        ...

    @abstractmethod
    async def get_latest_snapshot(self) -> PortfolioSnapshot | None:
        ...

    @abstractmethod
    async def save_position(self, position: Position) -> None:
        ...

    @abstractmethod
    async def list_open_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def delete_position(self, position_id: UUID) -> None:
        ...


class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None:
        ...

    @abstractmethod
    async def get(self, order_id: UUID) -> Order | None:
        ...

    @abstractmethod
    async def list_by_status(self, status: str) -> list[Order]:
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 100) -> list[Order]:
        ...


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...

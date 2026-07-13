"""Interfaces live broker — bloqueadas sin documentación oficial."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any
from uuid import UUID

from opciones.domain.models import (
    MarketQuote,
    OptionChain,
    Order,
    OrderRequest,
    PortfolioSnapshot,
    Position,
    UnderlyingAsset,
)
from opciones.modules.broker_adapters._shared.errors import BrokerErrorCode, MappedBrokerError
from opciones.ports import Broker, MarketDataProvider


class DocumentationMissingError(RuntimeError):
    def __init__(self, detail: str = "") -> None:
        msg = (
            "Integración live bloqueada: falta documentación oficial del proveedor "
            "en el repositorio. Ver docs/BROKER_INTEGRATION_GAPS.md. "
            f"{detail}"
        ).strip()
        super().__init__(msg)
        self.mapped = MappedBrokerError(
            BrokerErrorCode.DOCUMENTATION_MISSING,
            False,
            None,
            "Agregar documentación oficial y completar adaptador del proveedor",
            "critical",
            "No se puede operar live sin documentación del ALyC/proveedor",
        )


class BrokerAuthenticationClient(ABC):
    @abstractmethod
    async def authenticate(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def refresh_session(self) -> dict[str, Any]:
        ...


class BrokerOrderMapper(ABC):
    @abstractmethod
    def to_external(self, request: OrderRequest, client_order_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def from_external(self, payload: dict[str, Any]) -> Order:
        ...


class BrokerInstrumentMapper(ABC):
    @abstractmethod
    def to_underlying(self, payload: dict[str, Any]) -> UnderlyingAsset:
        ...

    @abstractmethod
    def to_option_chain(self, payload: dict[str, Any]) -> OptionChain:
        ...

    @abstractmethod
    def to_quote(self, payload: dict[str, Any]) -> MarketQuote:
        ...


class BrokerReconciliationAdapter(ABC):
    @abstractmethod
    async def compare_local_vs_remote(
        self,
        local_cash: Decimal,
        local_positions: dict[str, int],
    ) -> dict[str, Any]:
        ...


class LiveBrokerAdapter(Broker, ABC):
    """Reemplazo potencial de PaperBroker — no inventa endpoints."""

    @abstractmethod
    async def get_account_balance(self) -> Decimal:
        ...

    @abstractmethod
    async def get_buying_power(self) -> Decimal:
        ...

    @abstractmethod
    async def get_open_orders(self) -> list[Order]:
        ...

    @abstractmethod
    async def get_order_status(self, order_id: UUID | str) -> Order | None:
        ...

    @abstractmethod
    async def replace_order(self, order_id: UUID | str, request: OrderRequest) -> Order:
        ...

    @abstractmethod
    async def get_executions(self, order_id: UUID | str | None = None) -> list[dict[str, Any]]:
        ...


class LiveMarketDataAdapter(MarketDataProvider, ABC):
    @abstractmethod
    async def subscribe_quotes(self, symbols: list[str]) -> None:
        ...

    @abstractmethod
    async def unsubscribe_quotes(self, symbols: list[str]) -> None:
        ...


class BlockedLiveBrokerAdapter(LiveBrokerAdapter):
    """Implementación segura: todas las operaciones fallan hasta existir docs."""

    def _block(self) -> None:
        raise DocumentationMissingError()

    async def submit_order(self, request: OrderRequest) -> Order:
        self._block()

    async def cancel_order(self, order_id: UUID) -> Order:
        self._block()

    async def get_order(self, order_id: UUID) -> Order | None:
        self._block()

    async def get_positions(self) -> list[Position]:
        self._block()

    async def get_portfolio(self) -> PortfolioSnapshot:
        self._block()

    async def get_cash(self) -> Decimal:
        self._block()

    async def get_account_balance(self) -> Decimal:
        self._block()

    async def get_buying_power(self) -> Decimal:
        self._block()

    async def get_open_orders(self) -> list[Order]:
        self._block()

    async def get_order_status(self, order_id: UUID | str) -> Order | None:
        self._block()

    async def replace_order(self, order_id: UUID | str, request: OrderRequest) -> Order:
        self._block()

    async def get_executions(self, order_id: UUID | str | None = None) -> list[dict[str, Any]]:
        self._block()


class BlockedLiveMarketDataAdapter(LiveMarketDataAdapter):
    def _block(self) -> None:
        raise DocumentationMissingError()

    async def get_underlying(self, symbol: str) -> UnderlyingAsset | None:
        self._block()

    async def get_quote(self, symbol: str) -> MarketQuote | None:
        self._block()

    async def get_option_chain(self, underlying_symbol: str) -> OptionChain:
        self._block()

    async def get_historical_prices(self, symbol: str, start, end):  # type: ignore[no-untyped-def]
        self._block()

    async def list_underlyings(self) -> list[UnderlyingAsset]:
        self._block()

    async def subscribe_quotes(self, symbols: list[str]) -> None:
        self._block()

    async def unsubscribe_quotes(self, symbols: list[str]) -> None:
        self._block()

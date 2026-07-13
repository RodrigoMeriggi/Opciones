"""Adaptador broker real — SOLO interfaz placeholder.

DOCUMENTACIÓN FALTANTE (obligatoria antes de implementar):
- Nombre del ALyC / proveedor autorizado
- URL base de la API y versión
- Autenticación (OAuth2 / API key / certificados)
- Endpoints de: cotizaciones, cadena de opciones, envío/cancelación de órdenes,
  consulta de posiciones, saldos y estado de mercado
- Formato de símbolos BYMA
- Códigos de error y límites de rate
- Ambiente de certificación / paper oficial

NO inventar endpoints. LIVE_TRADING_ENABLED debe permanecer false.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from opciones.domain.models import Order, OrderRequest, PortfolioSnapshot, Position
from opciones.ports import Broker


class UnimplementedLiveBroker(Broker):
    """Lanza error explícito si se intenta usar sin documentación/credenciales."""

    async def submit_order(self, request: OrderRequest) -> Order:
        raise NotImplementedError(
            "Broker live no implementado. Falta documentación oficial del ALyC. "
            "Usar PaperBroker. Ver adapters/broker/README.md"
        )

    async def cancel_order(self, order_id: UUID) -> Order:
        raise NotImplementedError("Broker live no implementado")

    async def get_order(self, order_id: UUID) -> Order | None:
        raise NotImplementedError("Broker live no implementado")

    async def get_positions(self) -> list[Position]:
        raise NotImplementedError("Broker live no implementado")

    async def get_portfolio(self) -> PortfolioSnapshot:
        raise NotImplementedError("Broker live no implementado")

    async def get_cash(self) -> Decimal:
        raise NotImplementedError("Broker live no implementado")

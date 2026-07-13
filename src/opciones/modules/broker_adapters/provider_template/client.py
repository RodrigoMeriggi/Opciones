"""
Plantilla de proveedor — NO es un ALyC real.

Copiar este paquete a `broker_adapters/<provider_name>/` únicamente cuando
exista documentación oficial en `docs/brokers/<provider_name>/`.
"""

from __future__ import annotations

from typing import Any

from opciones.modules.broker_adapters._shared.interfaces import DocumentationMissingError


PROVIDER_NAME = "provider_template"
DOCS_PATH = "docs/brokers/<provider_name>/"


def require_official_docs() -> None:
    raise DocumentationMissingError(
        f"Plantilla '{PROVIDER_NAME}'. Colocar docs en {DOCS_PATH} antes de implementar."
    )


# --- Stubs tipados (todas lanzan DocumentationMissingError) ---

async def authenticate() -> dict[str, Any]:
    require_official_docs()


async def refresh_session() -> dict[str, Any]:
    require_official_docs()


async def get_account_balance() -> Any:
    require_official_docs()


async def get_buying_power() -> Any:
    require_official_docs()


async def get_portfolio() -> Any:
    require_official_docs()


async def get_open_positions() -> Any:
    require_official_docs()


async def get_open_orders() -> Any:
    require_official_docs()


async def get_order_status(order_id: str) -> Any:
    require_official_docs()


async def place_order(payload: dict[str, Any]) -> Any:
    require_official_docs()


async def cancel_order(order_id: str) -> Any:
    require_official_docs()


async def replace_order(order_id: str, payload: dict[str, Any]) -> Any:
    require_official_docs()


async def get_executions(order_id: str | None = None) -> Any:
    require_official_docs()


async def get_available_instruments() -> Any:
    require_official_docs()


async def get_option_chain(underlying: str) -> Any:
    require_official_docs()


async def subscribe_quotes(symbols: list[str]) -> None:
    require_official_docs()


async def unsubscribe_quotes(symbols: list[str]) -> None:
    require_official_docs()

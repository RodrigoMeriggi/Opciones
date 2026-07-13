"""Taxonomía de errores externos del broker (independiente del proveedor)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BrokerErrorCode(StrEnum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    INVALID_ORDER = "INVALID_ORDER"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    MARKET_CLOSED = "MARKET_CLOSED"
    INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    TEMPORARY_PROVIDER_ERROR = "TEMPORARY_PROVIDER_ERROR"
    PERMANENT_PROVIDER_ERROR = "PERMANENT_PROVIDER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN_EXTERNAL_ERROR = "UNKNOWN_EXTERNAL_ERROR"
    DOCUMENTATION_MISSING = "DOCUMENTATION_MISSING"
    LIVE_TRADING_DISABLED = "LIVE_TRADING_DISABLED"


@dataclass(frozen=True)
class MappedBrokerError:
    code: BrokerErrorCode
    retryable: bool
    retry_after_seconds: float | None
    action_required: str
    severity: str  # info|warning|high|critical
    operator_message: str  # sin secretos


class BrokerErrorMapper:
    """Mapea HTTP/status genéricos. Mapeos específicos del proveedor van en su módulo."""

    def from_http(self, status: int, body_safe: str = "") -> MappedBrokerError:
        if status in {401}:
            return MappedBrokerError(
                BrokerErrorCode.AUTHENTICATION_ERROR,
                False,
                None,
                "Reautenticar / rotar credenciales",
                "critical",
                "Fallo de autenticación con el proveedor",
            )
        if status in {403}:
            return MappedBrokerError(
                BrokerErrorCode.AUTHORIZATION_ERROR,
                False,
                None,
                "Revisar permisos de cuenta",
                "critical",
                "No autorizado ante el proveedor",
            )
        if status == 429:
            return MappedBrokerError(
                BrokerErrorCode.RATE_LIMIT_ERROR,
                True,
                5.0,
                "Respetar Retry-After y reducir ritmo",
                "high",
                "Límite de solicitudes alcanzado",
            )
        if status == 404:
            return MappedBrokerError(
                BrokerErrorCode.ORDER_NOT_FOUND,
                False,
                None,
                "Verificar ID de orden / instrumento",
                "warning",
                "Recurso no encontrado en el proveedor",
            )
        if 400 <= status < 500:
            return MappedBrokerError(
                BrokerErrorCode.INVALID_ORDER,
                False,
                None,
                "Corregir solicitud",
                "warning",
                f"Error de cliente HTTP {status}",
            )
        if status >= 500:
            return MappedBrokerError(
                BrokerErrorCode.TEMPORARY_PROVIDER_ERROR,
                True,
                2.0,
                "Reintentar con backoff",
                "high",
                f"Error temporal del proveedor HTTP {status}",
            )
        return MappedBrokerError(
            BrokerErrorCode.UNKNOWN_EXTERNAL_ERROR,
            False,
            None,
            "Investigar",
            "high",
            "Error externo desconocido",
        )

    def from_network(self, kind: str) -> MappedBrokerError:
        if kind == "timeout":
            return MappedBrokerError(
                BrokerErrorCode.TIMEOUT,
                True,
                1.0,
                "Reintentar / consultar estado de orden",
                "high",
                "Timeout de red con el proveedor",
            )
        return MappedBrokerError(
            BrokerErrorCode.NETWORK_ERROR,
            True,
            1.0,
            "Verificar conectividad",
            "high",
            "Error de red con el proveedor",
        )

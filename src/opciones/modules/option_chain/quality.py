"""Calidad de datos y filtros de operabilidad de opciones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from opciones.domain.enums import OptionStatus
from opciones.domain.models import OptionContract


@dataclass
class OperabilityResult:
    operable: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class QualityFilters:
    max_spread_pct: Decimal = Decimal("8")
    min_volume: int = 10
    min_days_to_expiration: int = 5
    max_days_to_expiration: int = 60
    max_quote_age_seconds: int = 120


def assess_operability(
    contract: OptionContract,
    filters: QualityFilters | None = None,
    now: datetime | None = None,
) -> OperabilityResult:
    """
    Una opción no es operable si incumple reglas de calidad.
    No se inventan datos faltantes.
    """
    f = filters or QualityFilters()
    reasons: list[str] = []
    ref_now = now or datetime.utcnow()

    if contract.bid is None or contract.ask is None:
        reasons.append("Falta bid o ask válido")
    else:
        if contract.ask <= 0:
            reasons.append("Ask menor o igual a cero")
        if contract.bid > contract.ask:
            reasons.append("Bid mayor que ask")
        if contract.ask > 0:
            spread_pct = ((contract.ask - contract.bid) / contract.ask) * Decimal("100")
            if spread_pct > f.max_spread_pct:
                reasons.append(f"Spread {spread_pct:.2f}% supera límite {f.max_spread_pct}%")

    if contract.status == OptionStatus.EXPIRED:
        reasons.append("Contrato vencido")

    if contract.days_to_expiration is not None:
        if contract.days_to_expiration < f.min_days_to_expiration:
            reasons.append("Vencimiento demasiado cerca")
        if contract.days_to_expiration > f.max_days_to_expiration:
            reasons.append("Vencimiento demasiado lejos")
    else:
        reasons.append("Faltan días al vencimiento")

    if contract.volume is None:
        reasons.append("Falta volumen")
    elif contract.volume < f.min_volume:
        reasons.append(f"Volumen {contract.volume} bajo mínimo {f.min_volume}")

    if contract.timestamp is None:
        reasons.append("Falta timestamp de cotización")
    else:
        age = (ref_now - contract.timestamp.replace(tzinfo=None)).total_seconds()
        if age > f.max_quote_age_seconds:
            reasons.append("Cotización desactualizada")

    essential = [
        contract.symbol,
        contract.underlying_symbol,
        contract.strike,
        contract.expiration_date,
        contract.option_type,
    ]
    if any(x is None for x in essential):
        reasons.append("Faltan datos esenciales")

    return OperabilityResult(operable=len(reasons) == 0, reasons=reasons)


def filter_operable(
    contracts: list[OptionContract],
    filters: QualityFilters | None = None,
) -> tuple[list[OptionContract], list[tuple[OptionContract, list[str]]]]:
    operable: list[OptionContract] = []
    rejected: list[tuple[OptionContract, list[str]]] = []
    for c in contracts:
        result = assess_operability(c, filters)
        if result.operable:
            operable.append(c)
        else:
            rejected.append((c, result.reasons))
    return operable, rejected

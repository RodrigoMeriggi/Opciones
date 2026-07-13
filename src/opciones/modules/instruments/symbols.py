"""Utilidades de instrumentos y normalización de símbolos BYMA."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from opciones.domain.enums import Moneyness, OptionType
from opciones.domain.models import MarketQuote, OptionContract


# Prefijos / sufijos frecuentes en feeds argentinos (normalización, no inventar datos)
_SYMBOL_CLEANUP = re.compile(r"[\s\-_./]+")


def normalize_symbol(raw: str) -> str:
    """Normaliza símbolos de distintos proveedores a forma canónica upper-case."""
    if not raw:
        raise ValueError("Símbolo vacío")
    cleaned = _SYMBOL_CLEANUP.sub("", raw.strip().upper())
    # Remover sufijos de mercado comunes
    for suffix in ("BYMA", "BCBA", "XMEV"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned


def days_to_expiration(expiration: date, as_of: date | None = None) -> int:
    ref = as_of or date.today()
    return (expiration - ref).days


def intrinsic_value(
    option_type: OptionType,
    strike: Decimal,
    underlying_price: Decimal | None,
) -> Decimal | None:
    if underlying_price is None:
        return None
    if option_type == OptionType.CALL:
        return max(underlying_price - strike, Decimal("0"))
    return max(strike - underlying_price, Decimal("0"))


def extrinsic_value(
    last_or_mid: Decimal | None,
    intrinsic: Decimal | None,
) -> Decimal | None:
    if last_or_mid is None or intrinsic is None:
        return None
    return last_or_mid - intrinsic


def moneyness(
    option_type: OptionType,
    strike: Decimal,
    underlying_price: Decimal | None,
    atm_threshold_pct: Decimal = Decimal("0.02"),
) -> Moneyness | None:
    if underlying_price is None or underlying_price <= 0:
        return None
    distance = abs(strike - underlying_price) / underlying_price
    if distance <= atm_threshold_pct:
        return Moneyness.ATM
    if option_type == OptionType.CALL:
        return Moneyness.ITM if underlying_price > strike else Moneyness.OTM
    return Moneyness.ITM if underlying_price < strike else Moneyness.OTM


def enrich_contract(
    contract: OptionContract,
    underlying_price: Decimal | None,
    as_of: date | None = None,
) -> OptionContract:
    """Calcula campos derivados sin inventar cotizaciones faltantes."""
    dte = days_to_expiration(contract.expiration_date, as_of)
    mid = None
    if contract.bid is not None and contract.ask is not None and contract.ask > 0:
        mid = (contract.bid + contract.ask) / 2
    price_ref = mid if mid is not None else contract.last_price
    iv = intrinsic_value(contract.option_type, contract.strike, underlying_price)
    ev = extrinsic_value(price_ref, iv)
    mn = moneyness(contract.option_type, contract.strike, underlying_price)
    return contract.model_copy(
        update={
            "days_to_expiration": dte,
            "intrinsic_value": iv,
            "extrinsic_value": ev,
            "moneyness": mn,
            "symbol": normalize_symbol(contract.symbol),
            "underlying_symbol": normalize_symbol(contract.underlying_symbol),
        }
    )


def absolute_spread(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    return ask - bid


def percentage_spread(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    abs_s = absolute_spread(bid, ask)
    if abs_s is None or ask is None or ask <= 0:
        return None
    return (abs_s / ask) * Decimal("100")


def is_quote_stale(timestamp: datetime | None, max_age_seconds: int = 120) -> bool:
    if timestamp is None:
        return True
    age = (datetime.utcnow() - timestamp.replace(tzinfo=None)).total_seconds()
    return age > max_age_seconds


def quote_from_contract(contract: OptionContract, source: str = "chain") -> MarketQuote:
    return MarketQuote(
        instrument_symbol=contract.symbol,
        bid=contract.bid,
        ask=contract.ask,
        last=contract.last_price,
        volume=contract.volume,
        timestamp=contract.timestamp,
        source=source,
    )

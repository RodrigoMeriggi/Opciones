"""Construcción y manipulación de cadenas de opciones."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from opciones.domain.enums import OptionType
from opciones.domain.models import OptionChain, OptionContract
from opciones.modules.instruments.symbols import enrich_contract, normalize_symbol
from opciones.modules.option_chain.quality import QualityFilters, filter_operable


def build_option_chain(
    underlying_symbol: str,
    contracts: list[OptionContract],
    underlying_price: Decimal | None = None,
    as_of: datetime | None = None,
) -> OptionChain:
    symbol = normalize_symbol(underlying_symbol)
    ref_date = (as_of or datetime.utcnow()).date()
    enriched = [
        enrich_contract(c.model_copy(update={"underlying_symbol": symbol}), underlying_price, ref_date)
        for c in contracts
    ]
    # Orden canónico: vencimiento, tipo, strike
    enriched.sort(key=lambda c: (c.expiration_date, c.option_type, c.strike))
    return OptionChain(
        underlying_symbol=symbol,
        underlying_price=underlying_price,
        as_of=as_of or datetime.utcnow(),
        contracts=enriched,
    )


def separate_calls_puts(
    chain: OptionChain,
) -> tuple[list[OptionContract], list[OptionContract]]:
    return chain.calls(), chain.puts()


def group_by_expiration(chain: OptionChain) -> dict[date, list[OptionContract]]:
    return chain.by_expiration()


def sort_by_strike(contracts: list[OptionContract]) -> list[OptionContract]:
    return sorted(contracts, key=lambda c: c.strike)


def filter_chain(
    chain: OptionChain,
    *,
    option_type: OptionType | None = None,
    min_dte: int | None = None,
    max_dte: int | None = None,
    max_spread_pct: Decimal | None = None,
    min_volume: int | None = None,
    only_operable: bool = True,
) -> OptionChain:
    filters = QualityFilters()
    if min_dte is not None:
        filters.min_days_to_expiration = min_dte
    if max_dte is not None:
        filters.max_days_to_expiration = max_dte
    if max_spread_pct is not None:
        filters.max_spread_pct = max_spread_pct
    if min_volume is not None:
        filters.minimum_volume = min_volume  # type: ignore[attr-defined]
        filters.min_volume = min_volume

    contracts = list(chain.contracts)
    if option_type is not None:
        contracts = [c for c in contracts if c.option_type == option_type]

    if only_operable:
        contracts, _ = filter_operable(contracts, filters)
    else:
        if min_dte is not None:
            contracts = [c for c in contracts if (c.days_to_expiration or 0) >= min_dte]
        if max_dte is not None:
            contracts = [c for c in contracts if (c.days_to_expiration or 0) <= max_dte]

    return OptionChain(
        underlying_symbol=chain.underlying_symbol,
        underlying_price=chain.underlying_price,
        as_of=chain.as_of,
        contracts=sort_by_strike(contracts) if option_type else contracts,
    )

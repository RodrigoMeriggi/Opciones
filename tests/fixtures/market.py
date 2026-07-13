"""Fixtures deterministas para pruebas E2E (sin Internet)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from opciones.domain.enums import OptionType
from opciones.domain.models import MarketQuote, OptionChain, OptionContract, UnderlyingAsset

DATA_VERSION = "fixtures-v1"
SEED_DEFAULT = 42


def fixture_root() -> Path:
    return Path(__file__).resolve().parent


def save_json(name: str, payload: dict[str, Any]) -> Path:
    path = fixture_root() / "data" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def make_underlying(
    symbol: str = "GGAL",
    price: Decimal = Decimal("4500"),
    *,
    volume: int = 100_000,
) -> UnderlyingAsset:
    return UnderlyingAsset(
        symbol=symbol,
        description=f"{symbol} test",
        last_price=price,
        bid=price * Decimal("0.999"),
        ask=price * Decimal("1.001"),
        volume=volume,
        timestamp=datetime.utcnow(),
    )


def make_contract(
    *,
    symbol: str,
    underlying: str = "GGAL",
    option_type: OptionType = OptionType.CALL,
    strike: Decimal = Decimal("4500"),
    dte: int = 30,
    bid: Decimal = Decimal("80"),
    ask: Decimal = Decimal("82"),
    volume: int = 500,
    open_interest: int = 1000,
    timestamp: datetime | None = None,
    stale_hours: float = 0,
) -> OptionContract:
    ts = timestamp or datetime.utcnow()
    if stale_hours:
        ts = ts - timedelta(hours=stale_hours)
    return OptionContract(
        symbol=symbol,
        underlying_symbol=underlying,
        option_type=option_type,
        strike=strike,
        expiration_date=date.today() + timedelta(days=dte),
        contract_size=1,
        bid=bid,
        ask=ask,
        last_price=(bid + ask) / 2,
        volume=volume,
        open_interest=open_interest,
        days_to_expiration=dte,
        timestamp=ts,
    )


def liquid_call_chain(spot: Decimal = Decimal("4500")) -> OptionChain:
    und = "GGAL"
    contracts = [
        make_contract(symbol=f"{und}C{int(s)}", strike=s, option_type=OptionType.CALL, bid=Decimal("90") - (s - spot) / 50, ask=Decimal("92") - (s - spot) / 50)
        for s in (spot - 200, spot - 100, spot, spot + 100, spot + 200)
    ]
    # ensure positive premiums
    for c in contracts:
        if c.bid is not None and c.bid < 5:
            c.bid = Decimal("5")
        if c.ask is not None and c.ask < 6:
            c.ask = Decimal("6")
    return OptionChain(underlying_symbol=und, underlying_price=spot, contracts=contracts)


def liquid_put_chain(spot: Decimal = Decimal("4500")) -> OptionChain:
    und = "GGAL"
    contracts = [
        make_contract(
            symbol=f"{und}P{int(s)}",
            strike=s,
            option_type=OptionType.PUT,
            bid=Decimal("90") + (s - spot) / 50,
            ask=Decimal("92") + (s - spot) / 50,
        )
        for s in (spot - 200, spot - 100, spot, spot + 100, spot + 200)
    ]
    for c in contracts:
        if c.bid is not None and c.bid < 5:
            c.bid = Decimal("5")
        if c.ask is not None and c.ask < 6:
            c.ask = Decimal("6")
    return OptionChain(underlying_symbol=und, underlying_price=spot, contracts=contracts)


def wide_spread_contract() -> OptionContract:
    return make_contract(symbol="GGALCWIDE", bid=Decimal("10"), ask=Decimal("50"), volume=200)


def stale_contract() -> OptionContract:
    return make_contract(symbol="GGALCSTALE", stale_hours=5)


def low_liquidity_contract(*, dte: int = 2) -> OptionContract:
    return make_contract(
        symbol="GGALCILLIQ",
        dte=dte,
        bid=Decimal("20"),
        ask=Decimal("28"),
        volume=1,
        open_interest=0,
    )


def corrupt_quote(symbol: str = "GGALCBAD") -> MarketQuote:
    return MarketQuote(
        instrument_symbol=symbol,
        bid=Decimal("50"),
        ask=Decimal("10"),  # inconsistente
        last=Decimal("30"),
        volume=10,
        timestamp=datetime.utcnow(),
        source="fixture_corrupt",
    )


def holiday_calendar() -> list[str]:
    return ["2026-01-01", "2026-05-01", "2026-07-09", "2026-12-25"]


def fixture_manifest() -> dict[str, Any]:
    return {
        "data_version": DATA_VERSION,
        "seed_default": SEED_DEFAULT,
        "offline": True,
        "holidays": holiday_calendar(),
    }

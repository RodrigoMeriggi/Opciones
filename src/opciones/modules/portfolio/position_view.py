"""Serialización enriquecida de posiciones para el dashboard."""

from __future__ import annotations

import re
from decimal import Decimal

from opciones.domain.models import MarketQuote, Position, UnderlyingAsset
from opciones.modules.instruments.byma_symbols import parse_byma_option_symbol


_LEGACY_STRIKE_RE = re.compile(r"[CP](\d+(?:\.\d+)?)$", re.I)


def parse_strike_from_symbol(symbol: str) -> Decimal | None:
    parsed = parse_byma_option_symbol(symbol)
    if parsed is not None:
        return parsed["strike"]
    m = _LEGACY_STRIKE_RE.search(symbol.upper().replace(" ", ""))
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except Exception:
        return None


def enrich_position(
    position: Position,
    *,
    underlying: UnderlyingAsset | None = None,
    quote: MarketQuote | None = None,
) -> dict:
    data = position.model_dump(mode="json")
    byma = parse_byma_option_symbol(position.symbol)
    strike = byma["strike"] if byma else parse_strike_from_symbol(position.symbol)
    entry = position.average_price
    qty = position.quantity
    cost = entry * qty
    und_px = underlying.last_price if underlying else None

    last = quote.last if quote else None
    bid = quote.bid if quote else None
    ask = quote.ask if quote else None
    mid = quote.mid if quote else None
    # Mark para PnL: mid → last → current_price de la posición
    mark = mid or last or position.current_price
    if mark is not None:
        position.current_price = mark
    market_value = position.market_value
    unrealized = position.unrealized_pnl

    moneyness = None
    if strike is not None and und_px is not None and und_px > 0:
        if position.option_type.value == "CALL":
            moneyness = "ITM" if und_px > strike else ("ATM" if und_px == strike else "OTM")
        else:
            moneyness = "ITM" if und_px < strike else ("ATM" if und_px == strike else "OTM")

    short = (
        f"{byma['root']}{byma['kind']}{int(byma['strike'])}"
        if byma
        else position.symbol
    )
    label = (
        f"{short} · {position.option_type.value} {position.underlying_symbol} "
        f"strike {strike if strike is not None else '?'} · vto {position.expiration_date}"
    )
    data.update(
        {
            "strike": str(strike) if strike is not None else None,
            "byma_short": short if byma else None,
            "label": label,
            "premium_paid": str(cost),
            "market_value": str(market_value) if market_value is not None else None,
            "unrealized_pnl": str(unrealized) if unrealized is not None else None,
            "pnl_pct": (
                str(((mark - entry) / entry * 100).quantize(Decimal("0.01")))
                if mark is not None and entry > 0
                else None
            ),
            "underlying_price": str(und_px) if und_px is not None else None,
            "moneyness": moneyness,
            "side": "LONG",
            "instrument_kind": "OPTION",
            "current_price": str(mark) if mark is not None else None,
            "last_price": str(last) if last is not None else None,
            "bid": str(bid) if bid is not None else None,
            "ask": str(ask) if ask is not None else None,
            "mid": str(mid) if mid is not None else None,
            "quote_source": quote.source if quote else None,
        }
    )
    return data

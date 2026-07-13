"""Cliente de panel libre de opciones BYMADATA (delayed).

Fuente: https://open.bymadata.com.ar/#/options
POST /vanoms-be-core/rest/api/bymadata/free/options
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from opciones.domain.enums import Currency, OptionStatus, OptionType
from opciones.domain.models import OptionChain, OptionContract
from opciones.modules.instruments.symbols import normalize_symbol
from opciones.modules.option_chain.builder import build_option_chain
from opciones.modules.option_chain.listed_series import parse_listed_symbol

logger = logging.getLogger(__name__)

BYMADATA_OPTIONS_URL = (
    "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/options"
)
BYMADATA_EQUITY_URL = (
    "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/leading-equity"
)
BYMADATA_PANEL_URL = "https://open.bymadata.com.ar/#/options"


def _post_json(url: str, *, timeout_s: float = 12.0) -> Any:
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OpcionesPaper/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bymadata_options(*, timeout_s: float = 12.0) -> list[dict[str, Any]]:
    payload = _post_json(BYMADATA_OPTIONS_URL, timeout_s=timeout_s)
    if not isinstance(payload, list):
        raise ValueError("Respuesta BYMADATA options inesperada")
    return payload


def fetch_bymadata_underlying_spot(
    symbol: str,
    *,
    timeout_s: float = 12.0,
) -> Decimal | None:
    """Último / mid del subyacente desde el panel de acciones (delayed)."""
    payload = _post_json(BYMADATA_EQUITY_URL, timeout_s=timeout_s)
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    want = normalize_symbol(symbol)
    for row in rows:
        if normalize_symbol(str(row.get("symbol") or "")) != want:
            continue
        trade = _dec(row.get("trade"))
        bid = _dec(row.get("bidPrice"))
        ask = _dec(row.get("offerPrice"))
        if trade is not None:
            return trade
        if bid is not None and ask is not None:
            return ((bid + ask) / 2).quantize(Decimal("0.01"))
        return bid or ask
    return None


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except Exception:
        return None
    return d if d > 0 else None


def row_to_contract(row: dict[str, Any], *, as_of: datetime | None = None) -> OptionContract | None:
    symbol = normalize_symbol(str(row.get("symbol") or ""))
    parsed = parse_listed_symbol(symbol)
    if parsed is None:
        return None
    und = normalize_symbol(str(row.get("underlyingSymbol") or ""))
    if not und:
        return None
    mat = row.get("maturityDate")
    if not mat:
        return None
    bid = _dec(row.get("bidPrice"))
    ask = _dec(row.get("offerPrice"))
    last = (
        _dec(row.get("trade"))
        or _dec(row.get("closingPrice"))
        or _dec(row.get("settlementPrice"))
        or _dec(row.get("previousSettlementPrice"))
        or _dec(row.get("previousClosingPrice"))
    )
    if last is None and bid is not None and ask is not None:
        last = ((bid + ask) / 2).quantize(Decimal("0.01"))
    # Sin puntas en panel delayed: spread mínimo alrededor del último/settlement
    # para que el paper pueda comprar (ask) y vender (bid) como en real.
    if bid is None and ask is None and last is not None:
        half = max((last * Decimal("0.02")).quantize(Decimal("0.01")), Decimal("0.01"))
        bid = max(last - half, Decimal("0.01"))
        ask = last + half
    elif bid is None and ask is not None:
        bid = max((ask * Decimal("0.98")).quantize(Decimal("0.01")), Decimal("0.01"))
        if bid >= ask:
            bid = max(ask - Decimal("0.01"), Decimal("0.01"))
    elif ask is None and bid is not None:
        ask = (bid * Decimal("1.02")).quantize(Decimal("0.01"))
        if ask <= bid:
            ask = bid + Decimal("0.01")
    if last is None and bid is not None and ask is not None:
        last = ((bid + ask) / 2).quantize(Decimal("0.01"))
    vol = int(row.get("tradeVolume") or row.get("volume") or 0)
    oi = int(row.get("openInterest") or 0)
    opt = OptionType.CALL if str(row.get("optionType", "")).upper().startswith("C") else parsed.option_type
    return OptionContract(
        symbol=symbol,
        underlying_symbol=und,
        option_type=opt,
        strike=parsed.strike,
        expiration_date=date.fromisoformat(str(mat)[:10]),
        contract_size=1,
        currency=Currency.ARS,
        bid=bid,
        ask=ask,
        last_price=last,
        volume=vol,
        open_interest=oi,
        status=OptionStatus.ACTIVE,
        timestamp=as_of or datetime.utcnow(),
    )


def build_chain_from_bymadata(
    underlying_symbol: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    underlying_price: Decimal | None = None,
    around_atm: int | None = 8,
    as_of: datetime | None = None,
) -> OptionChain:
    und = normalize_symbol(underlying_symbol)
    as_of = as_of or datetime.utcnow()
    rows = rows if rows is not None else fetch_bymadata_options()
    contracts: list[OptionContract] = []
    for row in rows:
        if normalize_symbol(str(row.get("underlyingSymbol") or "")) != und:
            continue
        c = row_to_contract(row, as_of=as_of)
        if c is not None:
            contracts.append(c)

    if around_atm is not None and underlying_price is not None and contracts:
        # Quedarse con bases cercanas al spot por vencimiento
        by_exp: dict[date, list[OptionContract]] = {}
        for c in contracts:
            by_exp.setdefault(c.expiration_date, []).append(c)
        trimmed: list[OptionContract] = []
        for exp, group in by_exp.items():
            strikes = sorted({c.strike for c in group})
            if not strikes:
                continue
            nearest_i = min(range(len(strikes)), key=lambda i: abs(strikes[i] - underlying_price))
            lo = max(0, nearest_i - around_atm)
            hi = min(len(strikes), nearest_i + around_atm + 1)
            keep = set(strikes[lo:hi])
            trimmed.extend(c for c in group if c.strike in keep)
        contracts = trimmed

    return build_option_chain(und, contracts, underlying_price=underlying_price, as_of=as_of)

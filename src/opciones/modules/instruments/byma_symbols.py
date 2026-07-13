"""Convención de tickers de opciones estilo BYMA (paper / display).

No es un feed oficial: replica el formato habitual de pantallas
(ej. GGAL call → GFGC8230AG) para que el paper sea reconocible.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from opciones.domain.enums import OptionType
from opciones.modules.instruments.symbols import normalize_symbol


# Raíces públicas habituales (subyacente → serie de opciones)
# Completado con universo BYMADATA; load_byma_universe puede ampliarlo en runtime.
OPTION_ROOTS: dict[str, str] = {
    "ALUA": "ALU",
    "BBAR": "BBA",
    "BHIP": "BHI",
    "BMA": "BMA",
    "BYMA": "BYM",
    "CECO2": "CEC",
    "CEPU": "CEP",
    "COME": "COM",
    "CRES": "CRE",
    "EDN": "EDN",
    "GGAL": "GFG",
    "LOMA": "LOM",
    "METR": "MET",
    "MIRG": "MIR",
    "PAMP": "PAM",
    "SUPV": "SUP",
    "TECO2": "TEC",
    "TGNO4": "TGN",
    "TGSU2": "TGS",
    "TRAN": "TRA",
    "TXAR": "TXA",
    "VIST": "VST",
    "YPFD": "YPF",
}


def _merge_universe_roots() -> None:
    try:
        from opciones.modules.instruments.universe import load_byma_universe

        OPTION_ROOTS.update(load_byma_universe().root_map())
    except Exception:
        pass


_merge_universe_roots()

# Sufijo de mes como suele verse en tableros (EN, FB, … AG, …)
MONTH_CODES: dict[int, str] = {
    1: "EN",
    2: "FB",
    3: "MZ",
    4: "AB",
    5: "MY",
    6: "JN",
    7: "JL",
    8: "AG",
    9: "SE",
    10: "OC",
    11: "NV",
    12: "DI",
}

_BYMA_RE = re.compile(
    r"^(?P<root>[A-Z]{2,5})(?P<kind>[CV])(?P<strike>\d+)(?P<month>[A-Z]{2})?(?P<day>\d{2})?$",
    re.I,
)


def option_root(underlying_symbol: str) -> str:
    und = normalize_symbol(underlying_symbol)
    return OPTION_ROOTS.get(und, und[:3])


def format_byma_option_symbol(
    underlying_symbol: str,
    option_type: OptionType,
    strike: Decimal | int | float,
    expiration: date,
    *,
    include_month: bool = True,
) -> str:
    """Ej.: CALL GGAL 8230 ago → GFGC8230AG; PUT → GFGV8230AG."""
    root = option_root(underlying_symbol)
    kind = "C" if option_type == OptionType.CALL else "V"
    strike_i = int(Decimal(str(strike)))
    if include_month:
        return f"{root}{kind}{strike_i}{MONTH_CODES[expiration.month]}"
    return f"{root}{kind}{strike_i}"


def parse_byma_option_symbol(symbol: str) -> dict | None:
    """Parsea GFGC8230 / GFGC8230AG (y equivalentes)."""
    cleaned = normalize_symbol(symbol)
    m = _BYMA_RE.match(cleaned)
    if not m:
        return None
    return {
        "root": m.group("root").upper(),
        "kind": m.group("kind").upper(),
        "strike": Decimal(m.group("strike")),
        "month": (m.group("month") or "").upper() or None,
        "option_type": OptionType.CALL if m.group("kind").upper() == "C" else OptionType.PUT,
    }

"""Carga series de opciones listadas (BYMADATA / comunicados), sin inventar tickers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from opciones.domain.enums import OptionType
from opciones.modules.instruments.symbols import normalize_symbol


_REPO_ROOT = Path(__file__).resolve().parents[4]
_SERIES_DIR = _REPO_ROOT / "config" / "byma_listed_series"

_SYM_RE = re.compile(r"^(?P<root>[A-Z]{2,5})(?P<kind>[CV])(?P<strike>\d+)(?P<month>[A-Z]+)$", re.I)


@dataclass(frozen=True)
class ListedContractRef:
    symbol: str
    option_type: OptionType
    strike: Decimal
    month_code: str


@dataclass(frozen=True)
class ListedExpiration:
    month_code: str
    expiration_date: date
    strikes: tuple[Decimal, ...]
    symbols: tuple[str, ...]
    source: str

    def contracts(self) -> list[ListedContractRef]:
        out: list[ListedContractRef] = []
        for sym in self.symbols:
            parsed = parse_listed_symbol(sym)
            if parsed is None:
                continue
            out.append(parsed)
        if out:
            return out
        # Fallback solo si el YAML trae strikes sin symbols
        for strike in self.strikes:
            for kind, ot in (("C", OptionType.CALL), ("V", OptionType.PUT)):
                # No inventar: requiere root externo — omitido a propósito
                _ = (kind, ot, strike)
        return out


@dataclass(frozen=True)
class ListedUnderlyingSeries:
    underlying: str
    root: str
    spot_reference: Decimal | None
    expirations: tuple[ListedExpiration, ...]
    sources: tuple[str, ...]
    source_url: str | None = None


def _series_path(underlying: str) -> Path:
    return _SERIES_DIR / f"{normalize_symbol(underlying).lower()}.yaml"


def has_listed_series(underlying: str) -> bool:
    return _series_path(underlying).is_file()


def parse_listed_symbol(symbol: str) -> ListedContractRef | None:
    m = _SYM_RE.match(normalize_symbol(symbol))
    if not m:
        return None
    kind = m.group("kind").upper()
    return ListedContractRef(
        symbol=normalize_symbol(symbol),
        option_type=OptionType.CALL if kind == "C" else OptionType.PUT,
        strike=Decimal(m.group("strike")),
        month_code=m.group("month").upper(),
    )


@lru_cache(maxsize=16)
def load_listed_series(underlying: str) -> ListedUnderlyingSeries | None:
    path = _series_path(underlying)
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    exps: list[ListedExpiration] = []
    for month_code, block in (raw.get("expirations") or {}).items():
        strikes = tuple(Decimal(str(s)) for s in block.get("strikes") or [])
        symbols = tuple(str(s) for s in block.get("symbols") or [])
        exps.append(
            ListedExpiration(
                month_code=str(month_code).upper(),
                expiration_date=date.fromisoformat(str(block["expiration_date"])),
                strikes=strikes,
                symbols=symbols,
                source=str(block.get("source") or ""),
            )
        )
    spot = raw.get("spot_reference")
    sources = [str(s) for s in (raw.get("sources") or [])]
    if raw.get("source_url"):
        sources.append(str(raw["source_url"]))
    return ListedUnderlyingSeries(
        underlying=normalize_symbol(str(raw.get("underlying") or underlying)),
        root=str(raw.get("root") or "").upper(),
        spot_reference=Decimal(str(spot)) if spot is not None else None,
        expirations=tuple(exps),
        sources=tuple(sources),
        source_url=str(raw["source_url"]) if raw.get("source_url") else None,
    )


def clear_listed_series_cache() -> None:
    load_listed_series.cache_clear()

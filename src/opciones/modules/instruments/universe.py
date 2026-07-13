"""Universo de subyacentes con opciones en BYMA (panel BYMADATA)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from opciones.modules.instruments.symbols import normalize_symbol

_REPO_ROOT = Path(__file__).resolve().parents[4]
_UNIVERSE_PATH = _REPO_ROOT / "config" / "byma_universe.yaml"

# Fallback si no hay YAML (panel del 2026-07-13)
_DEFAULT_SYMBOLS = (
    "ALUA",
    "BBAR",
    "BHIP",
    "BMA",
    "BYMA",
    "CECO2",
    "CEPU",
    "COME",
    "CRES",
    "EDN",
    "GGAL",
    "LOMA",
    "METR",
    "MIRG",
    "PAMP",
    "SUPV",
    "TECO2",
    "TGNO4",
    "TGSU2",
    "TRAN",
    "TXAR",
    "VIST",
    "YPFD",
)


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    option_root: str
    spot_reference: Decimal | None = None


@dataclass(frozen=True)
class BymaUniverse:
    entries: tuple[UniverseEntry, ...]
    source: str = "BYMADATA"

    @property
    def symbols(self) -> list[str]:
        return [e.symbol for e in self.entries]

    def root_map(self) -> dict[str, str]:
        return {e.symbol: e.option_root for e in self.entries}

    def spot_map(self) -> dict[str, Decimal]:
        return {e.symbol: e.spot_reference for e in self.entries if e.spot_reference is not None}


@lru_cache(maxsize=1)
def load_byma_universe() -> BymaUniverse:
    if not _UNIVERSE_PATH.is_file():
        return BymaUniverse(
            entries=tuple(UniverseEntry(symbol=s, option_root=s[:3]) for s in _DEFAULT_SYMBOLS),
            source="fallback",
        )
    raw = yaml.safe_load(_UNIVERSE_PATH.read_text(encoding="utf-8")) or {}
    entries: list[UniverseEntry] = []
    for item in raw.get("underlyings") or []:
        if isinstance(item, str):
            sym = normalize_symbol(item)
            entries.append(UniverseEntry(symbol=sym, option_root=sym[:3]))
            continue
        sym = normalize_symbol(str(item.get("symbol") or ""))
        if not sym:
            continue
        root = str(item.get("option_root") or sym[:3]).upper()
        spot = item.get("spot_reference")
        entries.append(
            UniverseEntry(
                symbol=sym,
                option_root=root,
                spot_reference=Decimal(str(spot)) if spot is not None else None,
            )
        )
    if not entries:
        entries = [UniverseEntry(symbol=s, option_root=s[:3]) for s in _DEFAULT_SYMBOLS]
    return BymaUniverse(
        entries=tuple(entries),
        source=str(raw.get("source") or "BYMADATA"),
    )


def clear_universe_cache() -> None:
    load_byma_universe.cache_clear()


def refresh_universe_from_bymadata() -> BymaUniverse:
    """Actualiza YAML + cache desde el panel free de opciones."""
    from collections import Counter, defaultdict
    import re
    from datetime import datetime, timezone

    from opciones.adapters.market_data.bymadata_options import (
        fetch_bymadata_options,
        fetch_bymadata_underlying_spot,
    )

    rows = fetch_bymadata_options()
    roots: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        und = normalize_symbol(str(r.get("underlyingSymbol") or ""))
        sym = normalize_symbol(str(r.get("symbol") or ""))
        m = re.match(r"^([A-Z]{2,5})[CV]\d+", sym)
        if und and m:
            roots[und].append(m.group(1))

    lines = [
        "# Universo de opciones BYMA (panel BYMADATA free/options)",
        "# https://open.bymadata.com.ar/#/options",
        f"# captured_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "source: BYMADATA",
        "underlyings:",
    ]
    entries: list[UniverseEntry] = []
    for und in sorted(roots):
        root = Counter(roots[und]).most_common(1)[0][0]
        spot = None
        try:
            spot = fetch_bymadata_underlying_spot(und)
        except Exception:
            spot = None
        lines.append(f"  - symbol: {und}")
        lines.append(f"    option_root: {root}")
        if spot is not None:
            lines.append(f'    spot_reference: "{spot}"')
        entries.append(UniverseEntry(symbol=und, option_root=root, spot_reference=spot))

    _UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _UNIVERSE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    clear_universe_cache()
    return load_byma_universe()

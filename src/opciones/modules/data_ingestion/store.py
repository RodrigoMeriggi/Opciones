"""Almacén en memoria + índices para datos históricos ingeridos."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from opciones.modules.data_ingestion.types import ClassifiedRecord, ImportResult, ImportVersion, RecordClass


class HistoricalStore:
    """Persistencia operativa en memoria (Postgres vía ORM en migración)."""

    def __init__(self) -> None:
        self.imports: dict[UUID, ImportVersion] = {}
        self.records: dict[UUID, list[ClassifiedRecord]] = {}
        self.underlyings: list[dict[str, Any]] = []
        self.options: list[dict[str, Any]] = []
        # índices
        self.by_symbol: dict[str, list[dict[str, Any]]] = {}
        self.by_underlying: dict[str, list[dict[str, Any]]] = {}
        self.by_expiration: dict[str, list[dict[str, Any]]] = {}

    def persist(self, result: ImportResult, kind: str = "underlying") -> int:
        self.imports[result.version.id] = result.version
        self.records[result.version.id] = result.records
        count = 0
        for c in result.records:
            if c.classification == RecordClass.REJECTED or not c.normalized:
                continue
            row = dict(c.normalized)
            row["_import_id"] = str(result.version.id)
            row["_classification"] = c.classification.value
            row["_reason"] = c.reason
            sym = str(row.get("symbol", "")).upper()
            self.by_symbol.setdefault(sym, []).append(row)
            if kind == "underlying":
                self.underlyings.append(row)
            else:
                self.options.append(row)
                und = str(row.get("underlying_symbol", "")).upper()
                self.by_underlying.setdefault(und, []).append(row)
                exp = str(row.get("expiration_date", ""))
                self.by_expiration.setdefault(exp, []).append(row)
            count += 1
        return count

    def coverage(self, symbol: str) -> dict[str, Any]:
        rows = self.by_symbol.get(symbol.upper(), [])
        if not rows:
            return {"symbol": symbol, "count": 0}
        tss = [r["timestamp"] for r in rows if isinstance(r.get("timestamp"), datetime)]
        return {
            "symbol": symbol.upper(),
            "count": len(rows),
            "start": min(tss).isoformat() if tss else None,
            "end": max(tss).isoformat() if tss else None,
        }

    def range_query(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        return [
            r
            for r in self.by_symbol.get(symbol.upper(), [])
            if isinstance(r.get("timestamp"), datetime) and start <= r["timestamp"] <= end
        ]

    def list_instruments(self) -> list[str]:
        return sorted(self.by_symbol.keys())

    def list_expirations(self, underlying: str | None = None) -> list[str]:
        if underlying:
            exps = {
                str(r.get("expiration_date"))
                for r in self.by_underlying.get(underlying.upper(), [])
            }
            return sorted(e for e in exps if e and e != "None")
        return sorted(k for k in self.by_expiration if k and k != "None")

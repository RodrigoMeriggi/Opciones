"""Lectores CSV / JSON / Parquet + interfaz API abstracta."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class HistoricalApiSource(ABC):
    """
    Interfaz para proveedores vía API.

    DOCUMENTACIÓN FALTANTE: URL, auth y esquemas del proveedor concreto.
    No inventar endpoints.
    """

    @abstractmethod
    async def fetch_bars(self, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def fetch_options(self, underlying: str, start: str, end: str) -> list[dict[str, Any]]:
        ...


class UnimplementedApiSource(HistoricalApiSource):
    async def fetch_bars(self, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Fuente API no implementada — falta documentación oficial del proveedor"
        )

    async def fetch_options(self, underlying: str, start: str, end: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Fuente API no implementada — falta documentación oficial del proveedor"
        )


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_json(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if not isinstance(data, list):
        raise ValueError("JSON debe ser lista de registros o {records: [...]}")
    return data


def read_parquet(path: str | Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("Instalar pyarrow para soporte Parquet: pip install pyarrow") from exc
    table = pq.read_table(path)
    return table.to_pylist()


def read_file(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return read_csv(p)
    if suffix == ".json":
        return read_json(p)
    if suffix in {".parquet", ".pq"}:
        return read_parquet(p)
    raise ValueError(f"Formato no soportado: {suffix}")

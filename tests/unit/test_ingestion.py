"""Pruebas de ingesta de datos históricos."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from opciones.modules.data_ingestion.pipeline.core import IngestionPipeline
from opciones.modules.data_ingestion.readers.formats import read_csv, read_json
from opciones.modules.data_ingestion.store import HistoricalStore
from opciones.modules.data_ingestion.types import RecordClass

ROOT = Path(__file__).resolve().parents[2]


def test_csv_import_and_quality():
    path = ROOT / "data/sample/csv/ggal_bars.csv"
    records = read_csv(path)
    pipe = IngestionPipeline(kind="underlying", known_symbols={"GGAL"})
    result = pipe.run(
        records,
        source="sample",
        filename=path.name,
        raw_bytes=path.read_bytes(),
        initiated_by="test",
    )
    assert result.quality.overall_quality in {"GOOD", "FAIR", "POOR"}
    assert result.version.content_hash
    store = HistoricalStore()
    n = store.persist(result, "underlying")
    assert n > 0
    assert "GGAL" in store.list_instruments()


def test_duplicate_import_blocked():
    path = ROOT / "data/sample/csv/ggal_bars.csv"
    records = read_csv(path)
    pipe = IngestionPipeline(kind="underlying")
    raw = path.read_bytes()
    pipe.run(records, source="s", filename="a.csv", raw_bytes=raw)
    with pytest.raises(ValueError, match="duplicada"):
        pipe.run(records, source="s", filename="a.csv", raw_bytes=raw)


def test_json_options_corrupt_and_traceability():
    path = ROOT / "data/sample/json/options_sample.json"
    records = read_json(path)
    pipe = IngestionPipeline(kind="option", known_symbols={"GGAL", "GGALJAN24C4500", "GGALJAN24P4500", "BAD"})
    result = pipe.run(records, source="sample", filename=path.name, raw_bytes=path.read_text())
    rejected = [r for r in result.records if r.classification == RecordClass.REJECTED]
    assert rejected
    assert all(r.reason for r in rejected)
    # No silent drop: len(records) == classified
    assert len(result.records) == len(records)


def test_timezone_normalization():
    pipe = IngestionPipeline(kind="underlying", known_symbols={"GGAL"})
    records = [
        {
            "symbol": "GGAL",
            "timestamp": "2024-01-02T20:00:00+00:00",  # UTC
            "close": 4500,
            "bid": 4499,
            "ask": 4501,
            "volume": 10,
        }
    ]
    result = pipe.run(records, source="tz", filename="tz.json", raw_bytes="x1")
    ts = result.records[0].normalized["timestamp"]
    assert isinstance(ts, datetime)
    # Converted to America/Argentina (UTC-3) => 17:00
    assert ts.hour == 17


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "symbol": ["GGAL", "GGAL"],
            "timestamp": ["2024-01-02T17:00:00", "2024-01-03T17:00:00"],
            "close": [4500.0, 4520.0],
            "bid": [4499.0, 4519.0],
            "ask": [4501.0, 4521.0],
            "volume": [100, 110],
        }
    )
    path = tmp_path / "bars.parquet"
    pq.write_table(table, path)
    from opciones.modules.data_ingestion.readers.formats import read_parquet

    rows = read_parquet(path)
    assert len(rows) == 2
    pipe = IngestionPipeline(kind="underlying")
    result = pipe.run(rows, source="pq", filename="bars.parquet", raw_bytes=path.read_bytes())
    assert result.persisted >= 0
    assert result.quality.by_class

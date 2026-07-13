"""Tipos del pipeline de ingesta histórica."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RecordClass(StrEnum):
    VALID = "VALID"
    CORRECTABLE = "CORRECTABLE"
    SUSPICIOUS = "SUSPICIOUS"
    REJECTED = "REJECTED"


class ClassifiedRecord(BaseModel):
    classification: RecordClass
    reason: str | None = None
    original: dict[str, Any]
    normalized: dict[str, Any] | None = None


class ImportVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source: str
    filename: str
    content_hash: str
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = "1.0"
    record_count: int = 0
    error_count: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    initiated_by: str = "system"
    allow_duplicate: bool = False


class QualityReport(BaseModel):
    import_id: UUID
    temporal_coverage: dict[str, Any] = Field(default_factory=dict)
    missing_pct: float = 0.0
    duplicates: int = 0
    invalid_values: int = 0
    instruments: list[str] = Field(default_factory=list)
    expirations: list[str] = Field(default_factory=list)
    spread_distribution: dict[str, float] = Field(default_factory=dict)
    volume_distribution: dict[str, float] = Field(default_factory=dict)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    overall_quality: str = "UNKNOWN"
    by_class: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    version: ImportVersion
    records: list[ClassifiedRecord]
    quality: QualityReport
    persisted: int = 0

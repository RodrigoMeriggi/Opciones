"""Pipeline de validación, normalización y clasificación (sin descartar en silencio)."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from opciones.modules.data_ingestion.types import (
    ClassifiedRecord,
    ImportResult,
    ImportVersion,
    QualityReport,
    RecordClass,
)
from opciones.modules.instruments.symbols import normalize_symbol


class IngestionPipeline:
    SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        timezone: str = "America/Argentina/Buenos_Aires",
        market_open: int = 11,
        market_close: int = 17,
        known_symbols: set[str] | None = None,
        abnormal_jump_pct: float = 0.25,
        kind: str = "underlying",  # underlying | option
    ) -> None:
        self.tz = ZoneInfo(timezone)
        self.market_open = market_open
        self.market_close = market_close
        self.known_symbols = {s.upper() for s in (known_symbols or set())}
        self.abnormal_jump_pct = abnormal_jump_pct
        self.kind = kind
        self._seen_hashes: set[str] = set()
        self._import_hashes: set[str] = set()

    def content_hash(self, raw: bytes | str) -> str:
        data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def run(
        self,
        records: list[dict[str, Any]],
        *,
        source: str,
        filename: str,
        raw_bytes: bytes | str = "",
        initiated_by: str = "system",
        allow_duplicate_import: bool = False,
    ) -> ImportResult:
        h = self.content_hash(raw_bytes or json_dumps(records))
        if h in self._import_hashes and not allow_duplicate_import:
            raise ValueError(
                f"Importación duplicada detectada (hash={h[:12]}…). "
                "Pasar allow_duplicate_import=True para forzar."
            )
        self._import_hashes.add(h)

        classified: list[ClassifiedRecord] = []
        prev_close: dict[str, Decimal] = {}

        for rec in records:
            classified.append(self._process_one(rec, prev_close))

        version = ImportVersion(
            source=source,
            filename=filename,
            content_hash=h,
            schema_version=self.SCHEMA_VERSION,
            record_count=len(records),
            error_count=sum(1 for c in classified if c.classification == RecordClass.REJECTED),
            initiated_by=initiated_by,
            allow_duplicate=allow_duplicate_import,
        )
        timestamps = []
        for c in classified:
            n = c.normalized or c.original
            ts = n.get("timestamp")
            if isinstance(ts, datetime):
                timestamps.append(ts)
        if timestamps:
            version.period_start = min(timestamps)
            version.period_end = max(timestamps)

        quality = self._quality(version, classified)
        persisted = sum(1 for c in classified if c.classification in {
            RecordClass.VALID, RecordClass.CORRECTABLE, RecordClass.SUSPICIOUS
        })
        return ImportResult(version=version, records=classified, quality=quality, persisted=persisted)

    def _process_one(
        self, rec: dict[str, Any], prev_close: dict[str, Decimal]
    ) -> ClassifiedRecord:
        reasons: list[str] = []
        classification = RecordClass.VALID
        normalized: dict[str, Any] = dict(rec)

        # Formato / campos
        try:
            sym_raw = rec.get("symbol") or rec.get("Symbol")
            if not sym_raw:
                return ClassifiedRecord(
                    RecordClass.REJECTED, "Símbolo faltante", rec, None
                )
            normalized["symbol"] = normalize_symbol(str(sym_raw))
        except Exception as exc:
            return ClassifiedRecord(RecordClass.REJECTED, f"Símbolo inválido: {exc}", rec, None)

        if self.known_symbols and normalized["symbol"] not in self.known_symbols:
            reasons.append("Símbolo desconocido")
            classification = RecordClass.SUSPICIOUS

        # Timestamp + timezone
        ts = self._parse_ts(rec.get("timestamp") or rec.get("datetime") or rec.get("date"))
        if ts is None:
            return ClassifiedRecord(RecordClass.REJECTED, "Fecha inválida", rec, None)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=self.tz)
        else:
            ts = ts.astimezone(self.tz)
        normalized["timestamp"] = ts.replace(tzinfo=None)  # store naive AR local

        # Horario
        if not (self.market_open <= ts.hour < self.market_close) and self.kind == "underlying":
            # daily bars often at close hour exactly
            if ts.hour != self.market_close:
                reasons.append("Cotización fuera de horario")
                classification = _worse(classification, RecordClass.SUSPICIOUS)

        # Precios
        for field in ("open", "high", "low", "close", "bid", "ask", "last", "last_price"):
            if field in rec and rec[field] not in (None, ""):
                try:
                    val = Decimal(str(rec[field]))
                except (InvalidOperation, ValueError):
                    reasons.append(f"{field} no numérico")
                    classification = RecordClass.REJECTED
                    continue
                if val < 0:
                    reasons.append(f"{field} negativo")
                    classification = RecordClass.REJECTED
                normalized[field] = val

        bid = normalized.get("bid")
        ask = normalized.get("ask")
        if bid is not None and ask is not None and bid > ask:
            reasons.append("Bid > Ask")
            classification = RecordClass.REJECTED

        vol = rec.get("volume")
        if vol not in (None, ""):
            try:
                v = int(vol)
                if v < 0:
                    reasons.append("Volumen negativo")
                    classification = RecordClass.REJECTED
                normalized["volume"] = v
            except (TypeError, ValueError):
                reasons.append("Volumen inválido")
                classification = _worse(classification, RecordClass.CORRECTABLE)

        # Options-specific
        if self.kind == "option":
            und = rec.get("underlying") or rec.get("underlying_symbol")
            if not und:
                reasons.append("Datos sin subyacente")
                classification = RecordClass.REJECTED
            else:
                normalized["underlying_symbol"] = normalize_symbol(str(und))
            opt = (rec.get("option_type") or rec.get("type") or "").upper()
            if opt not in {"CALL", "PUT"}:
                reasons.append("Opción sin tipo CALL/PUT")
                classification = RecordClass.REJECTED
            else:
                normalized["option_type"] = opt
            if rec.get("strike") in (None, ""):
                reasons.append("Opción sin strike")
                classification = RecordClass.REJECTED
            else:
                normalized["strike"] = Decimal(str(rec["strike"]))
            exp = self._parse_date(rec.get("expiration") or rec.get("expiration_date"))
            if exp is None:
                reasons.append("Vencimiento inválido")
                classification = RecordClass.REJECTED
            else:
                normalized["expiration_date"] = exp
                if exp < ts.date():
                    reasons.append("Vencimiento anterior a cotización / contrato vencido")
                    classification = RecordClass.REJECTED

        # Duplicados
        fingerprint = self._fingerprint(normalized)
        if fingerprint in self._seen_hashes:
            reasons.append("Registro duplicado")
            classification = _worse(classification, RecordClass.SUSPICIOUS)
        else:
            self._seen_hashes.add(fingerprint)

        # Saltos anormales
        close = normalized.get("close") or normalized.get("last") or normalized.get("last_price")
        sym = normalized["symbol"]
        if isinstance(close, Decimal) and sym in prev_close and prev_close[sym] > 0:
            jump = abs(close - prev_close[sym]) / prev_close[sym]
            if float(jump) > self.abnormal_jump_pct:
                reasons.append(f"Salto de precio anormal ({float(jump):.1%})")
                classification = _worse(classification, RecordClass.SUSPICIOUS)
        if isinstance(close, Decimal):
            prev_close[sym] = close

        # Corregibles: campos renombrados ya normalizados
        if classification == RecordClass.VALID and reasons:
            classification = RecordClass.CORRECTABLE

        return ClassifiedRecord(
            classification=classification,
            reason="; ".join(reasons) if reasons else None,
            original=rec,
            normalized=normalized if classification != RecordClass.REJECTED else None,
        )

    def _quality(self, version: ImportVersion, records: list[ClassifiedRecord]) -> QualityReport:
        by_class: dict[str, int] = {}
        for c in records:
            by_class[c.classification.value] = by_class.get(c.classification.value, 0) + 1
        instruments = sorted({
            (c.normalized or {}).get("symbol") or c.original.get("symbol")
            for c in records
            if (c.normalized or c.original).get("symbol")
        })
        expirations = sorted({
            str((c.normalized or {}).get("expiration_date"))
            for c in records
            if c.normalized and c.normalized.get("expiration_date")
        })
        spreads = []
        volumes = []
        for c in records:
            n = c.normalized
            if not n:
                continue
            if n.get("bid") is not None and n.get("ask") and n["ask"] > 0:
                spreads.append(float((n["ask"] - n["bid"]) / n["ask"] * 100))
            if n.get("volume") is not None:
                volumes.append(float(n["volume"]))
        gaps = self._detect_gaps(records)
        invalid = by_class.get(RecordClass.REJECTED.value, 0)
        total = len(records) or 1
        missing_pct = 100.0 * invalid / total
        if missing_pct < 5 and by_class.get(RecordClass.SUSPICIOUS.value, 0) < total * 0.1:
            overall = "GOOD"
        elif missing_pct < 20:
            overall = "FAIR"
        else:
            overall = "POOR"
        return QualityReport(
            import_id=version.id,
            temporal_coverage={
                "start": version.period_start.isoformat() if version.period_start else None,
                "end": version.period_end.isoformat() if version.period_end else None,
            },
            missing_pct=missing_pct,
            duplicates=sum(1 for c in records if c.reason and "duplicado" in c.reason.lower()),
            invalid_values=invalid,
            instruments=[str(i) for i in instruments if i],
            expirations=expirations,
            spread_distribution=_dist(spreads),
            volume_distribution=_dist(volumes),
            gaps=gaps,
            overall_quality=overall,
            by_class=by_class,
            notes=["Ningún registro se eliminó en silencio; todos quedan clasificados."],
        )

    def _detect_gaps(self, records: list[ClassifiedRecord]) -> list[dict[str, Any]]:
        by_sym: dict[str, list[datetime]] = {}
        for c in records:
            n = c.normalized
            if not n or not isinstance(n.get("timestamp"), datetime):
                continue
            by_sym.setdefault(n["symbol"], []).append(n["timestamp"])
        gaps = []
        for sym, tss in by_sym.items():
            tss = sorted(tss)
            for a, b in zip(tss, tss[1:]):
                delta = (b - a).days
                if delta > 3:  # más de un fin de semana
                    gaps.append({"symbol": sym, "from": a.isoformat(), "to": b.isoformat(), "days": delta})
        return gaps

    def _parse_ts(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(text.replace("Z", "+0000"), fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_date(self, value: Any):
        ts = self._parse_ts(value)
        return ts.date() if ts else None

    def _fingerprint(self, normalized: dict[str, Any]) -> str:
        parts = [
            str(normalized.get("symbol")),
            str(normalized.get("timestamp")),
            str(normalized.get("close") or normalized.get("last") or normalized.get("ask")),
            str(normalized.get("strike", "")),
            str(normalized.get("option_type", "")),
        ]
        return "|".join(parts)


def _worse(current: RecordClass, new: RecordClass) -> RecordClass:
    order = [
        RecordClass.VALID,
        RecordClass.CORRECTABLE,
        RecordClass.SUSPICIOUS,
        RecordClass.REJECTED,
    ]
    return new if order.index(new) > order.index(current) else current


def _dist(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    values = sorted(values)
    n = len(values)
    return {
        "min": values[0],
        "p50": values[n // 2],
        "p90": values[min(n - 1, int(n * 0.9))],
        "max": values[-1],
        "mean": sum(values) / n,
    }


def json_dumps(obj: Any) -> str:
    import json
    from datetime import date, datetime
    from decimal import Decimal

    def default(o: Any):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        return str(o)

    return json.dumps(obj, default=default, sort_keys=True)

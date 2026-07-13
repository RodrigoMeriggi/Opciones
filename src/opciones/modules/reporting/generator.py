"""Sistema de reportes automáticos (Prompt 20)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class ReportType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    STRATEGY = "strategy"
    UNDERLYING = "underlying"
    OPTION_TYPE = "option_type"
    RISK = "risk"
    INCIDENTS = "incidents"
    PAPER_VS_REAL = "paper_vs_real"
    BACKTEST = "backtest"
    STRESS = "stress"
    TRADE = "trade"


class TradingModeLabel(StrEnum):
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    REAL = "REAL"
    SIMULATED = "SIMULATED"


@dataclass
class ReportIntegrity:
    generated_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    environment: str
    trading_mode: TradingModeLabel
    strategy: str | None
    version: str | None
    commit: str | None
    data_sources: list[str]
    content_hash: str
    generated_by: str
    reconciliation_status: str
    simulated_vs_real: str  # "SIMULATED" | "REAL" | "MIXED"


@dataclass
class AttributionBreakdown:
    underlying_move: float | None = None
    volatility_change: float | None = None
    time_decay: float | None = None
    spread: float | None = None
    slippage: float | None = None
    commission: float | None = None
    contract_selection: float | None = None
    entry_timing: float | None = None
    exit_timing: float | None = None
    residual: float | None = None
    estimated_flags: dict[str, bool] = field(default_factory=dict)


@dataclass
class DeteriorationAlert:
    metric: str
    severity: str
    message: str
    critical_limit: bool = False


@dataclass
class ReportDocument:
    report_type: ReportType
    title: str
    payload: dict[str, Any]
    integrity: ReportIntegrity
    alerts: list[DeteriorationAlert] = field(default_factory=list)
    disclaimer: str = (
        "Diferenciar siempre resultados simulados de reales. "
        "Los reportes no garantizan rentabilidad futura."
    )


class ReportDistributor(Protocol):
    def distribute(self, report: ReportDocument, destination: str) -> None: ...


class NullEmailDistributor:
    def distribute(self, report: ReportDocument, destination: str) -> None:
        # no credentials; stub
        return None


class NullSlackDistributor:
    def distribute(self, report: ReportDocument, destination: str) -> None:
        return None


class NullTelegramDistributor:
    def distribute(self, report: ReportDocument, destination: str) -> None:
        return None


class NullS3Distributor:
    def distribute(self, report: ReportDocument, destination: str) -> None:
        return None


def attribute_pnl(
    total_pnl: float,
    *,
    underlying_move: float | None = None,
    vol_change: float | None = None,
    theta: float | None = None,
    spread: float | None = None,
    slippage: float | None = None,
    commission: float | None = None,
) -> AttributionBreakdown:
    known = [
        underlying_move,
        vol_change,
        theta,
        spread,
        slippage,
        commission,
    ]
    explained = sum(x for x in known if x is not None)
    residual = total_pnl - explained
    flags = {
        "underlying_move": underlying_move is None,
        "volatility_change": vol_change is None,
        "time_decay": theta is None,
        "spread": spread is None,
        "slippage": slippage is None,
        "commission": commission is None,
        "residual": True,
    }
    return AttributionBreakdown(
        underlying_move=underlying_move,
        volatility_change=vol_change,
        time_decay=theta,
        spread=spread,
        slippage=slippage,
        commission=commission,
        residual=residual,
        estimated_flags={k: v for k, v in flags.items() if v},
    )


def detect_deterioration(
    current: dict[str, float],
    baseline: dict[str, float],
    *,
    critical_drawdown: float = 0.25,
) -> list[DeteriorationAlert]:
    alerts: list[DeteriorationAlert] = []
    wr_c, wr_b = current.get("win_rate"), baseline.get("win_rate")
    if wr_c is not None and wr_b is not None and wr_c < wr_b - 0.15:
        alerts.append(
            DeteriorationAlert("win_rate", "warning", f"win rate {wr_c:.2f} << baseline {wr_b:.2f}")
        )
    dd = current.get("drawdown", 0)
    if dd > critical_drawdown:
        alerts.append(
            DeteriorationAlert(
                "drawdown",
                "critical",
                f"drawdown {dd:.2%} supera límite crítico",
                critical_limit=True,
            )
        )
    if current.get("slippage", 0) > baseline.get("slippage", 0) * 2 + 1e-9:
        alerts.append(DeteriorationAlert("slippage", "warning", "slippage aumentó vs baseline"))
    if current.get("rejections", 0) > baseline.get("rejections", 0) * 2 + 1:
        alerts.append(DeteriorationAlert("rejections", "warning", "aumentaron rechazos"))
    if abs(current.get("paper_real_gap", 0)) > 0.1:
        alerts.append(
            DeteriorationAlert(
                "paper_vs_real",
                "warning",
                "diferencia significativa paper vs real",
            )
        )
    if abs(current.get("backtest_paper_gap", 0)) > 0.15:
        alerts.append(
            DeteriorationAlert(
                "backtest_vs_paper",
                "warning",
                "diferencia significativa backtest vs paper",
            )
        )
    # no suspender por una sola métrica aislada salvo crítica
    return alerts


class ReportGenerator:
    def __init__(
        self,
        *,
        environment: str = "local",
        trading_mode: TradingModeLabel = TradingModeLabel.PAPER,
        generated_by: str = "ReportGenerator",
        commit: str | None = None,
    ) -> None:
        self.environment = environment
        self.trading_mode = trading_mode
        self.generated_by = generated_by
        self.commit = commit
        self.history: list[ReportDocument] = []

    def _integrity(
        self,
        payload: dict[str, Any],
        *,
        report_type: ReportType,
        strategy: str | None = None,
        version: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        recon: str = "unknown",
        data_sources: list[str] | None = None,
    ) -> ReportIntegrity:
        raw = json.dumps(payload, sort_keys=True, default=str)
        h = hashlib.sha256(raw.encode()).hexdigest()
        mode = self.trading_mode
        sim = (
            "REAL"
            if mode == TradingModeLabel.REAL
            else "SIMULATED"
            if mode in {TradingModeLabel.PAPER, TradingModeLabel.BACKTEST, TradingModeLabel.SIMULATED}
            else "MIXED"
        )
        return ReportIntegrity(
            generated_at=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
            environment=self.environment,
            trading_mode=mode,
            strategy=strategy,
            version=version,
            commit=self.commit,
            data_sources=data_sources or [],
            content_hash=h,
            generated_by=self.generated_by,
            reconciliation_status=recon,
            simulated_vs_real=sim,
        )

    def daily(self, data: dict[str, Any]) -> ReportDocument:
        payload = {
            "capital_inicial": data.get("capital_inicial"),
            "capital_final": data.get("capital_final"),
            "efectivo": data.get("efectivo"),
            "exposicion": data.get("exposicion"),
            "pnl": data.get("pnl"),
            "comisiones": data.get("comisiones"),
            "slippage": data.get("slippage"),
            "operaciones": data.get("operaciones"),
            "posiciones_abiertas": data.get("posiciones_abiertas"),
            "ordenes_rechazadas": data.get("ordenes_rechazadas"),
            "ejecuciones_parciales": data.get("ejecuciones_parciales"),
            "senales_descartadas": data.get("senales_descartadas"),
            "circuit_breakers": data.get("circuit_breakers"),
            "incidentes": data.get("incidentes"),
            "reconciliacion": data.get("reconciliacion"),
            "uso_limites": data.get("uso_limites"),
            "mode_label": self.trading_mode.value,
        }
        alerts = detect_deterioration(
            {
                "drawdown": float(data.get("drawdown", 0) or 0),
                "slippage": float(data.get("slippage", 0) or 0),
                "rejections": float(data.get("ordenes_rechazadas", 0) or 0),
                "win_rate": float(data.get("win_rate", 0.5) or 0.5),
            },
            {
                "drawdown": float(data.get("baseline_drawdown", 0.1) or 0.1),
                "slippage": float(data.get("baseline_slippage", 1) or 1),
                "rejections": float(data.get("baseline_rejections", 2) or 2),
                "win_rate": float(data.get("baseline_win_rate", 0.5) or 0.5),
            },
        )
        doc = ReportDocument(
            report_type=ReportType.DAILY,
            title=f"Reporte diario [{self.trading_mode.value}]",
            payload=payload,
            integrity=self._integrity(
                payload,
                report_type=ReportType.DAILY,
                strategy=data.get("strategy"),
                version=data.get("version"),
                recon=str(data.get("reconciliacion", "unknown")),
                data_sources=list(data.get("data_sources", ["ledger"])),
            ),
            alerts=alerts,
        )
        self.history.append(doc)
        return doc

    def trade(self, trade: dict[str, Any]) -> ReportDocument:
        payload = {
            "estrategia": trade.get("estrategia"),
            "senal": trade.get("senal"),
            "subyacente": trade.get("subyacente"),
            "contrato": trade.get("contrato"),
            "tipo": trade.get("tipo"),
            "strike": trade.get("strike"),
            "vencimiento": trade.get("vencimiento"),
            "entrada": trade.get("entrada"),
            "salida": trade.get("salida"),
            "precio_esperado": trade.get("precio_esperado"),
            "precio_ejecutado": trade.get("precio_ejecutado"),
            "cantidad": trade.get("cantidad"),
            "comision": trade.get("comision"),
            "slippage": trade.get("slippage"),
            "resultado": trade.get("resultado"),
            "motivo_entrada": trade.get("motivo_entrada"),
            "motivo_salida": trade.get("motivo_salida"),
            "indicadores": trade.get("indicadores"),
            "score_contrato": trade.get("score_contrato"),
            "riesgo_aprobado": trade.get("riesgo_aprobado"),
            "duracion": trade.get("duracion"),
            "attribution": asdict(
                attribute_pnl(
                    float(trade.get("resultado", 0) or 0),
                    underlying_move=trade.get("attr_underlying"),
                    vol_change=trade.get("attr_vol"),
                    theta=trade.get("attr_theta"),
                    spread=trade.get("attr_spread"),
                    slippage=trade.get("attr_slippage"),
                    commission=trade.get("attr_commission"),
                )
            ),
        }
        doc = ReportDocument(
            report_type=ReportType.TRADE,
            title="Reporte por operación",
            payload=payload,
            integrity=self._integrity(payload, report_type=ReportType.TRADE),
        )
        self.history.append(doc)
        return doc

    def comparison(self, rows: dict[str, float], label: str = "comparison") -> ReportDocument:
        payload = {
            "benchmarks": rows,
            "vs_no_trade": rows.get("no_trade"),
            "vs_buy_hold": rows.get("buy_hold"),
            "vs_base_strategy": rows.get("base"),
            "vs_previous_version": rows.get("previous_version"),
            "vs_previous_params": rows.get("previous_params"),
            "vs_backtest_expected": rows.get("backtest_expected"),
            "vs_paper_expected": rows.get("paper_expected"),
            "vs_real": rows.get("real"),
            "label": label,
        }
        doc = ReportDocument(
            report_type=ReportType.PAPER_VS_REAL,
            title="Comparación de resultados",
            payload=payload,
            integrity=self._integrity(payload, report_type=ReportType.PAPER_VS_REAL),
        )
        self.history.append(doc)
        return doc

    def from_stress(self, stress_payload: dict[str, Any]) -> ReportDocument:
        payload = {"stress": stress_payload, "mode_label": "SIMULATED"}
        doc = ReportDocument(
            report_type=ReportType.STRESS,
            title="Reporte de stress testing",
            payload=payload,
            integrity=self._integrity(
                payload,
                report_type=ReportType.STRESS,
                data_sources=["stress_engine"],
            ),
        )
        self.history.append(doc)
        return doc


class ReportExporter:
    def to_json(self, report: ReportDocument) -> str:
        return json.dumps(
            {
                "type": report.report_type.value,
                "title": report.title,
                "payload": report.payload,
                "integrity": asdict(report.integrity),
                "alerts": [asdict(a) for a in report.alerts],
                "disclaimer": report.disclaimer,
            },
            indent=2,
            default=str,
        )

    def to_csv(self, report: ReportDocument) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["key", "value"])
        for k, v in report.payload.items():
            writer.writerow([k, v])
        writer.writerow(["content_hash", report.integrity.content_hash])
        writer.writerow(["simulated_vs_real", report.integrity.simulated_vs_real])
        return buf.getvalue()

    def to_html(self, report: ReportDocument) -> str:
        rows = "".join(
            f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in report.payload.items()
        )
        mode = report.integrity.trading_mode.value
        sim = report.integrity.simulated_vs_real
        alerts = "".join(f"<li>{a.severity}: {a.message}</li>" for a in report.alerts)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{report.title}</title>
<style>
body{{font-family:Georgia,serif;margin:2rem;background:#f7f5f0;color:#1a1a1a}}
.banner{{padding:0.75rem 1rem;background:#1f4b3f;color:#f2efe8;font-weight:bold}}
.sim{{background:#8a5a00}} .real{{background:#7a1020}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}}
td,th{{border:1px solid #ccc;padding:0.4rem;text-align:left}}
.disclaimer{{margin-top:1.5rem;font-size:0.9rem;color:#444}}
</style></head><body>
<div class="banner {'sim' if sim!='REAL' else 'real'}">{mode} — {sim}</div>
<h1>{report.title}</h1>
<p>Hash: {report.integrity.content_hash} · Recon: {report.integrity.reconciliation_status}</p>
<table><tbody>{rows}</tbody></table>
<ul>{alerts}</ul>
<p class="disclaimer">{report.disclaimer}</p>
</body></html>"""

    def to_pdf_stub(self, report: ReportDocument) -> bytes:
        """PDF mínimo sin dependencia externa (texto embebido como bytes)."""
        text = self.to_html(report)
        # stub: almacenar HTML etiquetado; integración real PDF requiere librería aprobada
        return ("PDF_STUB\n" + text).encode("utf-8")

    def notification_summary(self, report: ReportDocument) -> str:
        pnl = report.payload.get("pnl") or report.payload.get("resultado")
        return (
            f"[{report.integrity.simulated_vs_real}] {report.title}: "
            f"pnl={pnl} hash={report.integrity.content_hash[:8]}"
        )

    def dashboard_summary(self, report: ReportDocument) -> dict[str, Any]:
        return {
            "title": report.title,
            "mode": report.integrity.trading_mode.value,
            "sim_vs_real": report.integrity.simulated_vs_real,
            "hash": report.integrity.content_hash,
            "alerts": len(report.alerts),
            "keys": list(report.payload.keys())[:12],
        }

    def save(self, report: ReportDocument, directory: Path, *, formats: list[str] | None = None) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        formats = formats or ["json", "html", "csv"]
        stamp = report.integrity.generated_at.strftime("%Y%m%dT%H%M%S")
        base = f"{report.report_type.value}_{stamp}_{report.integrity.content_hash[:8]}"
        paths: list[Path] = []
        if "json" in formats:
            p = directory / f"{base}.json"
            p.write_text(self.to_json(report), encoding="utf-8")
            paths.append(p)
        if "html" in formats:
            p = directory / f"{base}.html"
            p.write_text(self.to_html(report), encoding="utf-8")
            paths.append(p)
        if "csv" in formats:
            p = directory / f"{base}.csv"
            p.write_text(self.to_csv(report), encoding="utf-8")
            paths.append(p)
        if "pdf" in formats:
            p = directory / f"{base}.pdf.txt"
            p.write_bytes(self.to_pdf_stub(report))
            paths.append(p)
        return paths


class ReportScheduler:
    """Programación declarativa; el caller invoca tick()."""

    def __init__(self, generator: ReportGenerator) -> None:
        self.generator = generator
        self.jobs: list[dict[str, Any]] = []

    def schedule(self, when: str, report_factory: str, kwargs: dict[str, Any] | None = None) -> None:
        self.jobs.append({"when": when, "factory": report_factory, "kwargs": kwargs or {}})

    def due(self, event: str) -> list[dict[str, Any]]:
        return [j for j in self.jobs if j["when"] == event]

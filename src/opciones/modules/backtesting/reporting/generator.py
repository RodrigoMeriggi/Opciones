"""Generador de reportes JSON / CSV / HTML + gráficos SVG simples."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from opciones.modules.backtesting.types import BacktestResult


class BacktestReportGenerator:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_all(self, result: BacktestResult, name: str = "backtest") -> dict[str, str]:
        paths = {
            "json": str(self.write_json(result, name)),
            "csv": str(self.write_csv(result, name)),
            "html": str(self.write_html(result, name)),
            "equity_svg": str(self.write_equity_svg(result, name)),
            "drawdown_svg": str(self.write_drawdown_svg(result, name)),
        }
        return paths

    def write_json(self, result: BacktestResult, name: str) -> Path:
        path = self.output_dir / f"{name}.json"
        path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_csv(self, result: BacktestResult, name: str) -> Path:
        path = self.output_dir / f"{name}_trades.csv"
        fields = [
            "timestamp",
            "symbol",
            "underlying",
            "option_type",
            "side",
            "quantity",
            "price",
            "commission",
            "slippage",
            "pnl",
            "partial",
            "rejected",
            "entry_reason",
            "exit_reason",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for t in result.trades:
                row = t.model_dump(mode="json")
                writer.writerow({k: row.get(k) for k in fields})
        # equity csv
        eq_path = self.output_dir / f"{name}_equity.csv"
        with eq_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["timestamp", "equity", "cash", "exposure", "drawdown"]
            )
            writer.writeheader()
            for p in result.equity_curve:
                writer.writerow(
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "equity": str(p.equity),
                        "cash": str(p.cash),
                        "exposure": str(p.exposure),
                        "drawdown": str(p.drawdown),
                    }
                )
        return path

    def write_html(self, result: BacktestResult, name: str) -> Path:
        m = result.metrics
        path = self.output_dir / f"{name}.html"
        rows = "".join(
            f"<tr><td>{k}</td><td>{v}</td></tr>"
            for k, v in m.model_dump(mode="json").items()
        )
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <title>Backtest Report — {name}</title>
  <style>
    body {{ font-family: "IBM Plex Sans", system-ui, sans-serif; margin: 2rem; background: #0f1419; color: #e7ecf1; }}
    h1 {{ color: #7dd3fc; }}
    .banner {{ background: #1e3a5f; border-left: 4px solid #38bdf8; padding: 1rem; margin-bottom: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
    td, th {{ border-bottom: 1px solid #334155; padding: 0.5rem; text-align: left; }}
    .warn {{ color: #fbbf24; }}
    img {{ max-width: 100%; background: #1a2332; padding: 0.5rem; margin: 1rem 0; }}
  </style>
</head>
<body>
  <div class="banner">
    <strong>PAPER / SIMULACIÓN</strong> — Resultados históricos simulados.
    <span class="warn">No constituyen garantía de rentabilidad futura.</span>
  </div>
  <h1>Backtest: {name}</h1>
  <p>Período: {result.config.start_date} → {result.config.end_date}</p>
  <p>Universo: {", ".join(result.config.universe)}</p>
  <h2>Métricas</h2>
  <table>{rows}</table>
  <h2>Equity</h2>
  <img src="{name}_equity.svg" alt="equity curve"/>
  <h2>Drawdown</h2>
  <img src="{name}_drawdown.svg" alt="drawdown curve"/>
</body>
</html>
"""
        path.write_text(html, encoding="utf-8")
        return path

    def write_equity_svg(self, result: BacktestResult, name: str) -> Path:
        return self._line_svg(
            result.series.get("equity", []),
            self.output_dir / f"{name}_equity.svg",
            "Equity",
            "#38bdf8",
        )

    def write_drawdown_svg(self, result: BacktestResult, name: str) -> Path:
        return self._line_svg(
            result.series.get("drawdown", []),
            self.output_dir / f"{name}_drawdown.svg",
            "Drawdown",
            "#f87171",
        )

    def _line_svg(
        self, points: list[dict[str, Any]], path: Path, title: str, color: str
    ) -> Path:
        w, h, pad = 800, 280, 40
        if len(points) < 2:
            path.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
                f'<text x="20" y="40" fill="#94a3b8">{title}: sin datos</text></svg>',
                encoding="utf-8",
            )
            return path
        ys = [float(p["v"]) for p in points]
        ymin, ymax = min(ys), max(ys)
        span = (ymax - ymin) or 1.0

        def xy(i: int, v: float) -> tuple[float, float]:
            x = pad + i * (w - 2 * pad) / (len(ys) - 1)
            y = h - pad - ((v - ymin) / span) * (h - 2 * pad)
            return x, y

        coords = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}" for i, v in enumerate(ys))
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="#0f1419"/>
  <text x="{pad}" y="24" fill="#e2e8f0" font-family="sans-serif" font-size="14">{title}</text>
  <polyline fill="none" stroke="{color}" stroke-width="2" points="{coords}"/>
</svg>"""
        path.write_text(svg, encoding="utf-8")
        return path

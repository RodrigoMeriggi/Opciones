"""Registro de métricas en memoria (exportable a CloudWatch/Prometheus)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsRegistry:
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    labels: dict[str, dict[str, str]] = field(default_factory=dict)

    def inc(self, name: str, value: float = 1.0, **label: str) -> None:
        key = self._key(name, label)
        self.counters[key] += value

    def set_gauge(self, name: str, value: float, **label: str) -> None:
        key = self._key(name, label)
        self.gauges[key] = value

    def observe(self, name: str, value: float, **label: str) -> None:
        key = self._key(name, label)
        self.histograms[key].append(value)
        if len(self.histograms[key]) > 5000:
            self.histograms[key] = self.histograms[key][-2500:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "avg": (sum(v) / len(v)) if v else 0,
                    "p95": sorted(v)[int(len(v) * 0.95)] if v else 0,
                }
                for k, v in self.histograms.items()
            },
        }

    @staticmethod
    def _key(name: str, label: dict[str, str]) -> str:
        if not label:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(label.items()))
        return f"{name}{{{parts}}}"


# Singletons de proceso
TECH_METRICS = MetricsRegistry()
MARKET_METRICS = MetricsRegistry()
STRATEGY_METRICS = MetricsRegistry()
ORDER_METRICS = MetricsRegistry()
RISK_METRICS = MetricsRegistry()

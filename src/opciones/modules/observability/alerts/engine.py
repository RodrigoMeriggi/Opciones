"""Motor de alertas operativas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    code: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class AlertEngine:
    alerts: list[Alert] = field(default_factory=list)
    on_critical: list[Callable[[Alert], None]] = field(default_factory=list)
    block_entries: bool = False

    def emit(self, code: str, severity: AlertSeverity, message: str, **metadata: Any) -> Alert:
        alert = Alert(code=code, severity=severity, message=message, metadata=metadata)
        self.alerts.append(alert)
        if severity == AlertSeverity.CRITICAL:
            self.block_entries = True
            for cb in self.on_critical:
                cb(alert)
        return alert

    def evaluate_market_age(self, age_seconds: float, threshold: float = 120) -> Alert | None:
        if age_seconds > threshold:
            return self.emit(
                "MARKET_DATA_FROZEN",
                AlertSeverity.CRITICAL,
                f"Datos de mercado congelados ({age_seconds:.0f}s)",
                age_seconds=age_seconds,
            )
        return None

    def evaluate_daily_loss(self, daily_pnl: float, max_loss: float) -> Alert | None:
        if daily_pnl <= -abs(max_loss):
            return self.emit(
                "MAX_DAILY_LOSS",
                AlertSeverity.CRITICAL,
                "Pérdida diaria máxima alcanzada",
                daily_pnl=daily_pnl,
            )
        return None

    def recent(self, limit: int = 50) -> list[Alert]:
        return self.alerts[-limit:]


ALERTS = AlertEngine()

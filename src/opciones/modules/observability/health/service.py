"""Health checks diferenciados."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class DependencyStatus:
    name: str
    ok: bool
    detail: str = ""
    latency_ms: float | None = None


@dataclass
class HealthService:
    trading_enabled: bool = False
    market_data_fresh: bool = True
    broker_reachable: bool = True  # paper = True
    db_ok: bool = True
    redis_ok: bool = True
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    degraded_reasons: list[str] = field(default_factory=list)
    checkers: dict[str, Callable[[], DependencyStatus]] = field(default_factory=dict)

    def live(self) -> dict[str, Any]:
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

    def ready(self) -> dict[str, Any]:
        ready = self.db_ok and self.redis_ok
        return {
            "status": "ready" if ready else "not_ready",
            "db_ok": self.db_ok,
            "redis_ok": self.redis_ok,
        }

    def dependencies(self) -> dict[str, Any]:
        results = []
        for name, fn in self.checkers.items():
            results.append(fn().__dict__)
        results.append(DependencyStatus("database", self.db_ok).__dict__)
        results.append(DependencyStatus("redis", self.redis_ok).__dict__)
        return {"dependencies": results}

    def trading(self) -> dict[str, Any]:
        apt = (
            self.trading_enabled
            and self.market_data_fresh
            and self.broker_reachable
            and not self.degraded_reasons
        )
        return {
            "alive": True,
            "trading_enabled": self.trading_enabled,
            "apt_for_trading": apt,
            "degraded_reasons": list(self.degraded_reasons),
            "note": "Un proceso puede estar vivo pero no apto para operar",
        }

    def market_data(self) -> dict[str, Any]:
        return {
            "fresh": self.market_data_fresh,
            "status": "ok" if self.market_data_fresh else "stale",
        }

    def broker(self) -> dict[str, Any]:
        return {
            "reachable": self.broker_reachable,
            "mode": "paper_default",
        }

    def mark_degraded(self, reason: str) -> None:
        if reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)

    def clear_degraded(self, reason: str | None = None) -> None:
        if reason is None:
            self.degraded_reasons.clear()
        elif reason in self.degraded_reasons:
            self.degraded_reasons.remove(reason)


HEALTH = HealthService()

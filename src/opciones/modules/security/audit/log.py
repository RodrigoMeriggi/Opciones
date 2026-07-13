"""Auditoría append-only con cadena de hashes (inmutable desde la app)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    id: str
    timestamp: str
    actor: str
    action: str
    resource: str
    result: str
    ip: str | None
    user_agent: str | None
    session_id: str | None
    correlation_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    prev_hash: str
    event_hash: str


class ImmutableAuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._alerts: list[dict[str, Any]] = []

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._events)

    @property
    def security_alerts(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    def append(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        result: str,
        ip: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AuditEvent:
        prev = self._events[-1].event_hash if self._events else "GENESIS"
        payload = {
            "id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "actor": actor,
            "action": action,
            "resource": resource,
            "result": result,
            "ip": ip,
            "user_agent": user_agent,
            "session_id": session_id,
            "correlation_id": correlation_id,
            "before": before,
            "after": after,
            "reason": reason,
            "prev_hash": prev,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        event = AuditEvent(**payload, event_hash=digest)
        self._events.append(event)
        self._maybe_alert(event)
        return event

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for e in self._events:
            if e.prev_hash != prev:
                return False
            payload = {k: getattr(e, k) for k in (
                "id", "timestamp", "actor", "action", "resource", "result",
                "ip", "user_agent", "session_id", "correlation_id",
                "before", "after", "reason", "prev_hash",
            )}
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            if digest != e.event_hash:
                return False
            prev = e.event_hash
        return True

    def _maybe_alert(self, event: AuditEvent) -> None:
        critical_actions = {
            "live_trading.approve_request",
            "live_trading.approve",
            "emergency_stop.deactivate",
            "settings.critical_change",
            "secrets.access",
            "role.elevate",
            "login.failed_burst",
        }
        if event.action in critical_actions or event.result == "DENIED":
            self._alerts.append(
                {
                    "severity": "CRITICAL" if "live" in event.action or "secret" in event.action else "HIGH",
                    "event_id": event.id,
                    "action": event.action,
                    "actor": event.actor,
                    "timestamp": event.timestamp,
                }
            )

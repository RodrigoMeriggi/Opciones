"""Doble aprobación para acciones críticas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from opciones.modules.security.audit.log import ImmutableAuditLog
from opciones.modules.security.rbac.permissions import Permission


CRITICAL_ACTIONS = {
    "enable_live_trading",
    "increase_risk_limits",
    "change_max_daily_loss",
    "deactivate_emergency_after_critical",
    "add_broker_credentials",
    "change_broker_account",
    "authorize_strategy_for_live",
}


@dataclass
class ApprovalRequest:
    id: str
    action: str
    requester: str
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
    expires_at: datetime
    approver: str | None = None
    approved_at: datetime | None = None
    status: str = "PENDING"  # PENDING|APPROVED|REJECTED|EXPIRED
    ip: str | None = None
    session_id: str | None = None


@dataclass
class DualApprovalService:
    audit: ImmutableAuditLog
    ttl_hours: int = 24
    requests: dict[str, ApprovalRequest] = field(default_factory=dict)

    def request(
        self,
        *,
        action: str,
        requester: str,
        reason: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip: str | None = None,
        session_id: str | None = None,
    ) -> ApprovalRequest:
        if action not in CRITICAL_ACTIONS:
            raise ValueError(f"Acción no requiere doble aprobación: {action}")
        req = ApprovalRequest(
            id=str(uuid4()),
            action=action,
            requester=requester,
            reason=reason,
            before=before,
            after=after,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=self.ttl_hours),
            ip=ip,
            session_id=session_id,
        )
        self.requests[req.id] = req
        self.audit.append(
            actor=requester,
            action=f"{action}.request",
            resource=req.id,
            result="PENDING",
            ip=ip,
            session_id=session_id,
            before=before,
            after=after,
            reason=reason,
        )
        return req

    def approve(self, request_id: str, approver: str, *, role: str) -> ApprovalRequest:
        if role != "ADMIN":
            raise PermissionError("Solo ADMIN puede aprobar")
        req = self.requests[request_id]
        if req.status != "PENDING":
            raise ValueError("Solicitud no pendiente")
        if datetime.utcnow() > req.expires_at:
            req.status = "EXPIRED"
            raise ValueError("Solicitud expirada")
        if approver == req.requester:
            raise PermissionError("El aprobador debe ser distinto del solicitante")
        req.approver = approver
        req.approved_at = datetime.utcnow()
        req.status = "APPROVED"
        self.audit.append(
            actor=approver,
            action=f"{req.action}.approve",
            resource=req.id,
            result="APPROVED",
            session_id=req.session_id,
            ip=req.ip,
            before=req.before,
            after=req.after,
            reason=req.reason,
        )
        return req

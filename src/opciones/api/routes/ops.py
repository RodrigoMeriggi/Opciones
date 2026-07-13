"""Rutas de health / observabilidad / seguridad / transición."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from opciones.api.deps.auth import TokenPayload, current_user, require_roles
from opciones.modules.observability.alerts.engine import ALERTS
from opciones.modules.observability.health.service import HEALTH
from opciones.modules.observability.metrics.registry import (
    MARKET_METRICS,
    ORDER_METRICS,
    RISK_METRICS,
    STRATEGY_METRICS,
    TECH_METRICS,
)
from opciones.modules.security.approvals.dual import DualApprovalService
from opciones.modules.security.audit.log import ImmutableAuditLog
from opciones.modules.security.auth.sessions import (
    SessionManager,
    UserStore,
    bootstrap_default_users,
)
from opciones.modules.security.rbac.permissions import Permission, has_permission
from opciones.modules.live_transition.service import (
    LiveTransitionService,
    PaperValidationCriteria,
    StrategyLifecycleState,
)

router = APIRouter()

_users = UserStore()
bootstrap_default_users(_users)
_sessions = SessionManager()
_audit = ImmutableAuditLog()
_approvals = DualApprovalService(_audit)
_transition = LiveTransitionService(_audit, _approvals)


class SecureLogin(BaseModel):
    username: str
    password: str


@router.post("/auth/v2/login")
async def login_v2(body: SecureLogin, request: Request) -> dict:
    user = _users.authenticate(body.username, body.password)
    if not user:
        fails = _sessions.record_failed_login(body.username)
        _audit.append(
            actor=body.username,
            action="login.failed",
            resource="auth",
            result="DENIED",
            ip=request.client.host if request.client else None,
        )
        if fails >= 5:
            _audit.append(
                actor=body.username,
                action="login.failed_burst",
                resource="auth",
                result="DENIED",
                ip=request.client.host if request.client else None,
            )
        raise HTTPException(401, "Credenciales inválidas")
    access, refresh = _sessions.create_session(
        user,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _audit.append(
        actor=user.username,
        action="login",
        resource="auth",
        result="OK",
        session_id=access.session_id,
        ip=request.client.host if request.client else None,
    )
    return {
        "access_token": access.token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "expires_at": access.expires_at,
    }


@router.post("/auth/v2/logout")
async def logout_v2(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    # Best-effort: legacy token may not map 1:1; audit anyway
    _audit.append(actor=user.sub, action="logout", resource="auth", result="OK")
    return {"ok": True}


@router.get("/health/live")
async def health_live() -> dict:
    return HEALTH.live()


@router.get("/health/ready")
async def health_ready() -> dict:
    return HEALTH.ready()


@router.get("/health/dependencies")
async def health_deps() -> dict:
    return HEALTH.dependencies()


@router.get("/health/trading")
async def health_trading() -> dict:
    return HEALTH.trading()


@router.get("/health/market-data")
async def health_md() -> dict:
    return HEALTH.market_data()


@router.get("/health/broker")
async def health_broker() -> dict:
    return HEALTH.broker()


@router.get("/observability/metrics")
async def metrics(user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER", "VIEWER"))]) -> dict:
    return {
        "tech": TECH_METRICS.snapshot(),
        "market": MARKET_METRICS.snapshot(),
        "strategy": STRATEGY_METRICS.snapshot(),
        "orders": ORDER_METRICS.snapshot(),
        "risk": RISK_METRICS.snapshot(),
    }


@router.get("/observability/alerts")
async def alerts(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    return {
        "alerts": [
            {
                "code": a.code,
                "severity": a.severity.value,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in ALERTS.recent()
        ],
        "entries_blocked": ALERTS.block_entries,
    }


@router.get("/audit")
async def audit_list(user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))]) -> dict:
    if not has_permission(user.role, Permission.AUDIT_READ):
        raise HTTPException(403)
    return {
        "events": [e.__dict__ for e in _audit.events[-200:]],
        "chain_valid": _audit.verify_chain(),
        "security_alerts": _audit.security_alerts[-50:],
    }


class TransitionValidate(BaseModel):
    strategy_id: str
    trading_days: int
    trades: int
    max_drawdown: float
    critical_errors: int = 0
    risk_violations: int = 0
    reconciliation_ok: bool = True
    out_of_sample_ok: bool = True
    used_real_market_data: bool = False
    realistic_costs: bool = True


@router.post("/transition/register")
async def register_strategy(
    body: dict[str, Any],
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    rec = _transition.register(
        body["strategy_id"],
        version=body.get("version", "0.1.0"),
        git_commit=body.get("git_commit", "unknown"),
        environment=body.get("environment", "local"),
    )
    return {"strategy_id": rec.strategy_id, "state": rec.state.value}


@router.post("/transition/paper-validate")
async def paper_validate(
    body: TransitionValidate,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    if body.strategy_id not in _transition.strategies:
        _transition.register(body.strategy_id, version="0.1.0", git_commit="dev")
        _transition.transition(body.strategy_id, StrategyLifecycleState.PAPER_TRADING, user.sub)
    ok, failures = _transition.evaluate_paper_validated(
        body.strategy_id,
        trading_days=body.trading_days,
        trades=body.trades,
        max_drawdown=body.max_drawdown,
        critical_errors=body.critical_errors,
        risk_violations=body.risk_violations,
        reconciliation_ok=body.reconciliation_ok,
        out_of_sample_ok=body.out_of_sample_ok,
        used_real_market_data=body.used_real_market_data,
        realistic_costs=body.realistic_costs,
    )
    return {"validated": ok, "failures": failures, "note": "No se valida solo por rentabilidad"}


class LiveRequest(BaseModel):
    strategy_id: str
    reason: str


@router.post("/transition/live-request")
async def live_request(
    body: LiveRequest,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    req = _transition.request_live_restricted(body.strategy_id, user.sub, body.reason)
    return {"approval_id": req.id, "status": req.status}


class LiveApprove(BaseModel):
    strategy_id: str
    approval_id: str
    checklist: dict[str, bool] = Field(default_factory=dict)


@router.post("/transition/live-approve")
async def live_approve(
    body: LiveApprove,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    # Live sigue deshabilitado a nivel plataforma
    rec = _transition.apply_live_restricted_approval(
        body.strategy_id, body.approval_id, user.sub, checklist=body.checklist
    )
    return {
        "state": rec.state.value,
        "live_trading_enabled_platform": False,
        "note": "Estado LIVE_RESTRICTED registrado; LIVE_TRADING_ENABLED permanece false hasta activación operativa controlada",
    }

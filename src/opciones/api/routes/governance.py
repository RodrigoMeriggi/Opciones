"""API de gobierno, configuración y asistente operativo (solo lectura en assistant)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from opciones.api.deps.auth import require_roles
from opciones.modules.config_service import ConfigCategory, ConfigurationService
from opciones.modules.governance import (
    GovernanceStatus,
    StrategyDefinition,
    StrategyGovernanceService,
)
from opciones.modules.operational_assistant import OperationalAssistantService, ReadOnlyDataGateway

router = APIRouter(tags=["governance-config-assistant"])

_governance = StrategyGovernanceService()
_config = ConfigurationService()
_assistant = OperationalAssistantService(
    ReadOnlyDataGateway(
        {
            "mode": "PAPER",
            "decisions": [],
            "orders": [],
            "positions": [],
            "audit": [],
            "metrics": {"exposure_pct": 0.12},
            "reports": [],
            "config_public": {"trading_mode": "paper"},
            "incidents": [],
            "active_strategy": {"name": "NoTrade", "version": "1.0.0"},
            "deployed_version": {"app": "0.4.0", "commit": "local"},
            "circuit_breaker": {"active": False},
        }
    )
)


class PromoteBody(BaseModel):
    name: str
    version: str
    target: GovernanceStatus
    reason: str
    evidence_flags: list[str] = Field(default_factory=list)


class ConfigDraftBody(BaseModel):
    category: ConfigCategory
    payload: dict[str, Any]
    version: str = "1.0.0"
    environment: str = "local"


class AssistantAskBody(BaseModel):
    question: str
    role: str = "VIEWER"


class RegisterStrategyBody(BaseModel):
    name: str
    description: str = ""
    owner: str
    version: str
    code_commit: str = "unknown"
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


@router.post("/governance/strategies/register")
async def register_strategy(
    body: RegisterStrategyBody,
    user=Depends(require_roles("ADMIN", "TRADER")),
) -> dict:
    defn = _governance.register(
        StrategyDefinition(
            name=body.name,
            description=body.description,
            owner=body.owner,
            version=body.version,
            code_commit=body.code_commit,
            parameters_schema=body.parameters_schema,
        )
    )
    return {"id": defn.id, "status": defn.status.value, "key": f"{defn.name}@{defn.version}"}


@router.post("/governance/strategies/promote")
async def promote_strategy(body: PromoteBody, user=Depends(require_roles("ADMIN"))) -> dict:
    for flag in body.evidence_flags:
        _governance.add_evidence(body.name, body.version, flag)
    try:
        defn = _governance.promote(
            body.name,
            body.version,
            body.target,
            actor=user.sub,
            reason=body.reason,
        )
    except (PermissionError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": defn.status.value, "approved_at": defn.approved_at}


@router.get("/governance/strategies")
async def list_strategies(user=Depends(require_roles("ADMIN", "TRADER", "VIEWER"))) -> dict:
    return {
        k: {"status": v.status.value, "version": v.version, "owner": v.owner}
        for k, v in _governance.definitions.items()
    }


@router.post("/config/drafts")
async def create_config_draft(body: ConfigDraftBody, user=Depends(require_roles("ADMIN"))) -> dict:
    try:
        ver = _config.create_draft(
            category=body.category,
            payload=body.payload,
            created_by=user.sub,
            environment=body.environment,
            version=body.version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"hash": ver.content_hash, "status": ver.status.value, "critical": ver.critical}


@router.post("/config/{content_hash}/approve")
async def approve_config(content_hash: str, user=Depends(require_roles("ADMIN"))) -> dict:
    try:
        _config.submit_for_approval(content_hash)
        ver = _config.approve(content_hash, user.sub)
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": ver.status.value}


@router.post("/config/{content_hash}/apply")
async def apply_config(content_hash: str, user=Depends(require_roles("ADMIN"))) -> dict:
    try:
        ver = _config.apply_atomic(content_hash, user.sub)
    except (KeyError, PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": ver.status.value, "effective_at": ver.effective_at}


@router.get("/config/resolved")
async def resolved_config(user=Depends(require_roles("ADMIN", "TRADER", "VIEWER"))) -> dict:
    data = _config.resolve()
    # nunca devolver secretos
    return {k: v for k, v in data.items() if "secret" not in k.lower() and "password" not in k.lower()}


@router.post("/assistant/ask")
async def assistant_ask(body: AssistantAskBody, user=Depends(require_roles("ADMIN", "TRADER", "VIEWER"))) -> dict:
    user_role = user.role
    rank = {"VIEWER": 0, "TRADER": 1, "ADMIN": 2}
    role = body.role.upper()
    effective = role if rank.get(role, 0) <= rank.get(user_role, 0) else user_role
    answer = _assistant.ask(body.question, role=effective)
    return {
        "summary": answer.summary,
        "confidence": answer.confidence,
        "data_mode": answer.data_mode.value,
        "missing_data": answer.missing_data,
        "evidence": [
            {
                "source": e.source,
                "timestamp": e.timestamp,
                "identifiers": e.identifiers,
                "snippet": e.snippet,
            }
            for e in answer.evidence
        ],
        "candidates": answer.candidates,
        "refused_action": answer.refused_action,
        "links": answer.internal_links,
        "note": "Asistente de solo lectura; no envía órdenes ni cambia configuración.",
    }

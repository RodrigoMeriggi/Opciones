"""Gobierno del ciclo de vida de estrategias (Prompt 23)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from opciones.modules.security.audit.log import ImmutableAuditLog


class GovernanceStatus(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    BACKTESTED = "BACKTESTED"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_RESTRICTED = "LIVE_RESTRICTED"
    LIVE_APPROVED = "LIVE_APPROVED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


PROMOTION_REQUIREMENTS: dict[GovernanceStatus, set[str]] = {
    GovernanceStatus.RESEARCH: {"documentation"},
    GovernanceStatus.BACKTESTED: {"tests", "documentation", "reproducible_results"},
    GovernanceStatus.PAPER_APPROVED: {
        "tests",
        "documentation",
        "reproducible_results",
        "stress_testing",
        "risk_review",
        "technical_review",
        "versioning",
    },
    GovernanceStatus.LIVE_RESTRICTED: {
        "tests",
        "documentation",
        "reproducible_results",
        "stress_testing",
        "risk_review",
        "technical_review",
        "operational_review",
        "approvals",
        "versioning",
    },
    GovernanceStatus.LIVE_APPROVED: {
        "tests",
        "documentation",
        "reproducible_results",
        "stress_testing",
        "risk_review",
        "technical_review",
        "operational_review",
        "approvals",
        "versioning",
    },
}

ALLOWED: dict[GovernanceStatus, set[GovernanceStatus]] = {
    GovernanceStatus.DRAFT: {GovernanceStatus.RESEARCH, GovernanceStatus.RETIRED},
    GovernanceStatus.RESEARCH: {GovernanceStatus.BACKTESTED, GovernanceStatus.SUSPENDED, GovernanceStatus.RETIRED},
    GovernanceStatus.BACKTESTED: {
        GovernanceStatus.PAPER_APPROVED,
        GovernanceStatus.RESEARCH,
        GovernanceStatus.SUSPENDED,
    },
    GovernanceStatus.PAPER_APPROVED: {
        GovernanceStatus.LIVE_RESTRICTED,
        GovernanceStatus.SUSPENDED,
        GovernanceStatus.BACKTESTED,
    },
    GovernanceStatus.LIVE_RESTRICTED: {
        GovernanceStatus.LIVE_APPROVED,
        GovernanceStatus.SUSPENDED,
        GovernanceStatus.PAPER_APPROVED,
    },
    GovernanceStatus.LIVE_APPROVED: {GovernanceStatus.SUSPENDED, GovernanceStatus.LIVE_RESTRICTED},
    GovernanceStatus.SUSPENDED: {
        GovernanceStatus.PAPER_APPROVED,
        GovernanceStatus.RESEARCH,
        GovernanceStatus.RETIRED,
    },
    GovernanceStatus.RETIRED: set(),
}

INVALIDATION_TRIGGERS = {
    "strategy_code",
    "critical_parameters",
    "asset_universe",
    "risk_limits",
    "input_data",
    "pricing_model",
    "broker",
    "execution_format",
    "temporal_frequency",
}


@dataclass
class StrategyDefinition:
    name: str
    description: str
    owner: str
    version: str
    status: GovernanceStatus = GovernanceStatus.DRAFT
    code_commit: str = "unknown"
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class StrategyRelease:
    strategy_version: str
    environment: str
    approved_parameters: dict[str, Any]
    risk_limits: dict[str, Any]
    allowed_assets: list[str]
    allowed_hours: dict[str, int]
    approval_status: str
    approvers: list[str] = field(default_factory=list)
    effective_from: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class ExperimentRecord:
    dataset_version: str
    code_version: str
    parameters: dict[str, Any]
    results: dict[str, Any]
    metrics: dict[str, Any]
    artifacts: list[str]
    author: str
    date: datetime = field(default_factory=datetime.utcnow)
    reproducibility_hash: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class ModelRiskAssessment:
    assumptions: list[str]
    limitations: list[str]
    data_dependencies: list[str]
    failure_modes: list[str]
    sensitivity: dict[str, Any]
    known_risks: list[str]
    residual_risk: str
    reviewer: str
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class DecisionLogEntry:
    who: str
    what: str
    when: datetime
    reason: str
    evidence: list[str]
    comments: str
    conditions: list[str]
    expires_at: datetime | None
    approved: bool


@dataclass
class VersionDiff:
    code_changed: list[str]
    parameters_changed: dict[str, tuple[Any, Any]]
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    drawdown_before: float | None
    drawdown_after: float | None
    costs_before: float | None
    costs_after: float | None
    trades_before: int | None
    trades_after: int | None
    sensitivity: dict[str, Any]
    new_risks: list[str]


class StrategyGovernanceService:
    """Impide promoción a producción sin evidencia, revisión y trazabilidad."""

    def __init__(self, audit: ImmutableAuditLog | None = None) -> None:
        self.audit = audit or ImmutableAuditLog()
        self.definitions: dict[str, StrategyDefinition] = {}
        self.releases: list[StrategyRelease] = []
        self.experiments: list[ExperimentRecord] = []
        self.assessments: dict[str, ModelRiskAssessment] = {}
        self.decisions: list[DecisionLogEntry] = []
        self.evidence_flags: dict[str, set[str]] = {}
        self._invalidated: set[str] = set()

    def register(self, definition: StrategyDefinition) -> StrategyDefinition:
        key = f"{definition.name}@{definition.version}"
        self.definitions[key] = definition
        self.evidence_flags[key] = set()
        self.audit.append(
            actor=definition.owner,
            action="strategy_registered",
            resource=key,
            result="ok",
            after={"status": definition.status.value},
        )
        return definition

    def add_evidence(self, name: str, version: str, flag: str) -> None:
        key = f"{name}@{version}"
        self.evidence_flags.setdefault(key, set()).add(flag)

    def promote(
        self,
        name: str,
        version: str,
        target: GovernanceStatus,
        *,
        actor: str,
        reason: str,
        evidence: list[str] | None = None,
    ) -> StrategyDefinition:
        key = f"{name}@{version}"
        if key in self._invalidated:
            raise PermissionError("aprobación invalidada; requiere nueva evidencia")
        defn = self.definitions[key]
        if target not in ALLOWED.get(defn.status, set()):
            raise ValueError(f"transición ilegal {defn.status} → {target}")
        required = PROMOTION_REQUIREMENTS.get(target, set())
        have = self.evidence_flags.get(key, set())
        missing = required - have
        if missing:
            raise PermissionError(f"faltan requisitos: {sorted(missing)}")
        prev = defn.status
        defn.status = target
        if target in {GovernanceStatus.PAPER_APPROVED, GovernanceStatus.LIVE_APPROVED, GovernanceStatus.LIVE_RESTRICTED}:
            defn.approved_at = datetime.utcnow()
        entry = DecisionLogEntry(
            who=actor,
            what=f"promote {prev.value}→{target.value}",
            when=datetime.utcnow(),
            reason=reason,
            evidence=evidence or sorted(have),
            comments="",
            conditions=sorted(required),
            expires_at=datetime.utcnow() + timedelta(days=90),
            approved=True,
        )
        self.decisions.append(entry)
        self.audit.append(
            actor=actor,
            action="strategy_promoted",
            resource=key,
            result=target.value,
            reason=reason,
            before={"status": prev.value},
            after={"status": target.value},
        )
        return defn

    def invalidate(self, name: str, version: str, trigger: str, actor: str) -> None:
        if trigger not in INVALIDATION_TRIGGERS:
            raise ValueError(f"trigger desconocido: {trigger}")
        key = f"{name}@{version}"
        self._invalidated.add(key)
        defn = self.definitions[key]
        if defn.status in {
            GovernanceStatus.PAPER_APPROVED,
            GovernanceStatus.LIVE_RESTRICTED,
            GovernanceStatus.LIVE_APPROVED,
        }:
            defn.status = GovernanceStatus.SUSPENDED
        self.audit.append(
            actor=actor,
            action="approval_invalidated",
            resource=key,
            result="SUSPENDED",
            reason=trigger,
        )

    def compare_versions(
        self,
        *,
        code_changed: list[str],
        params_before: dict[str, Any],
        params_after: dict[str, Any],
        metrics_before: dict[str, float],
        metrics_after: dict[str, float],
        new_risks: list[str] | None = None,
    ) -> VersionDiff:
        changed = {
            k: (params_before.get(k), params_after.get(k))
            for k in set(params_before) | set(params_after)
            if params_before.get(k) != params_after.get(k)
        }
        return VersionDiff(
            code_changed=code_changed,
            parameters_changed=changed,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            drawdown_before=metrics_before.get("drawdown"),
            drawdown_after=metrics_after.get("drawdown"),
            costs_before=metrics_before.get("costs"),
            costs_after=metrics_after.get("costs"),
            trades_before=int(metrics_before["trades"]) if "trades" in metrics_before else None,
            trades_after=int(metrics_after["trades"]) if "trades" in metrics_after else None,
            sensitivity={"param_delta_count": len(changed)},
            new_risks=new_risks or [],
        )

    def create_release(self, release: StrategyRelease) -> StrategyRelease:
        self.releases.append(release)
        return release

    def retire(self, name: str, version: str, actor: str, reason: str) -> StrategyDefinition:
        key = f"{name}@{version}"
        defn = self.definitions[key]
        defn.status = GovernanceStatus.RETIRED
        self.decisions.append(
            DecisionLogEntry(
                who=actor,
                what="retire",
                when=datetime.utcnow(),
                reason=reason,
                evidence=[],
                comments="historial conservado; sin nuevas operaciones",
                conditions=[],
                expires_at=None,
                approved=True,
            )
        )
        self.audit.append(
            actor=actor, action="strategy_retired", resource=key, result="RETIRED", reason=reason
        )
        return defn

    def due_for_review(self, name: str, version: str, *, trades: int, drawdown: float) -> list[str]:
        reasons = []
        key = f"{name}@{version}"
        defn = self.definitions[key]
        if defn.approved_at and datetime.utcnow() - defn.approved_at > timedelta(days=90):
            reasons.append("tiempo")
        if trades >= 100:
            reasons.append("cantidad_operaciones")
        if drawdown >= 0.1:
            reasons.append("drawdown")
        return reasons

"""Transición controlada paper → live."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from opciones.modules.security.approvals.dual import DualApprovalService
from opciones.modules.security.audit.log import ImmutableAuditLog


class StrategyLifecycleState(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    BACKTEST_ONLY = "BACKTEST_ONLY"
    PAPER_TRADING = "PAPER_TRADING"
    PAPER_VALIDATED = "PAPER_VALIDATED"
    LIVE_RESTRICTED = "LIVE_RESTRICTED"
    LIVE_LIMITED = "LIVE_LIMITED"
    LIVE_APPROVED = "LIVE_APPROVED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


ALLOWED_TRANSITIONS: dict[StrategyLifecycleState, set[StrategyLifecycleState]] = {
    StrategyLifecycleState.DEVELOPMENT: {
        StrategyLifecycleState.BACKTEST_ONLY,
        StrategyLifecycleState.PAPER_TRADING,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.BACKTEST_ONLY: {
        StrategyLifecycleState.PAPER_TRADING,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.PAPER_TRADING: {
        StrategyLifecycleState.PAPER_VALIDATED,
        StrategyLifecycleState.SUSPENDED,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.PAPER_VALIDATED: {
        StrategyLifecycleState.LIVE_RESTRICTED,
        StrategyLifecycleState.PAPER_TRADING,
        StrategyLifecycleState.SUSPENDED,
    },
    StrategyLifecycleState.LIVE_RESTRICTED: {
        StrategyLifecycleState.LIVE_LIMITED,
        StrategyLifecycleState.SUSPENDED,
        StrategyLifecycleState.PAPER_TRADING,
    },
    StrategyLifecycleState.LIVE_LIMITED: {
        StrategyLifecycleState.LIVE_APPROVED,
        StrategyLifecycleState.LIVE_RESTRICTED,
        StrategyLifecycleState.SUSPENDED,
    },
    StrategyLifecycleState.LIVE_APPROVED: {
        StrategyLifecycleState.LIVE_LIMITED,
        StrategyLifecycleState.SUSPENDED,
    },
    StrategyLifecycleState.SUSPENDED: {
        StrategyLifecycleState.PAPER_TRADING,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.RETIRED: set(),
}


@dataclass
class PaperValidationCriteria:
    min_trading_days: int = 20
    min_trades: int = 30
    max_drawdown: float = 0.15
    require_real_market_data: bool = True
    require_realistic_costs: bool = True
    require_no_critical_errors: bool = True
    require_no_risk_violations: bool = True
    require_reconciliation_ok: bool = True
    require_out_of_sample: bool = True


@dataclass
class LiveRestrictedLimits:
    max_capital: float = 50_000
    max_per_trade: float = 5_000
    max_daily_loss: float = 2_000
    max_daily_trades: int = 3
    max_positions: int = 1
    allowed_underlyings: list[str] = field(default_factory=lambda: ["GGAL"])
    market_orders_only_emergency: bool = True
    kill_switch: bool = True


@dataclass
class StrategyApprovalRecord:
    strategy_id: str
    state: StrategyLifecycleState
    version: str
    git_commit: str
    data_model_version: str
    params: dict[str, Any]
    limits: dict[str, Any]
    provider: str | None
    account: str | None
    environment: str
    approved_at: datetime | None = None
    approvers: list[str] = field(default_factory=list)
    activation_expires_at: datetime | None = None
    checklist: dict[str, bool] = field(default_factory=dict)


@dataclass
class CanaryResult:
    executed: bool
    paused: bool
    details: dict[str, Any]


@dataclass
class ShadowComparison:
    signal_match: bool
    expected_price_diff: float | None
    executed_price_diff: float | None
    latency_ms_diff: float | None
    notes: list[str] = field(default_factory=list)


class LiveTransitionService:
    def __init__(self, audit: ImmutableAuditLog, approvals: DualApprovalService) -> None:
        self.audit = audit
        self.approvals = approvals
        self.strategies: dict[str, StrategyApprovalRecord] = {}
        self.suspension_reasons: dict[str, str] = {}

    def register(
        self,
        strategy_id: str,
        *,
        version: str,
        git_commit: str,
        environment: str = "local",
    ) -> StrategyApprovalRecord:
        rec = StrategyApprovalRecord(
            strategy_id=strategy_id,
            state=StrategyLifecycleState.DEVELOPMENT,
            version=version,
            git_commit=git_commit,
            data_model_version="1.0",
            params={},
            limits={},
            provider=None,
            account=None,
            environment=environment,
        )
        self.strategies[strategy_id] = rec
        return rec

    def transition(self, strategy_id: str, new_state: StrategyLifecycleState, actor: str) -> StrategyApprovalRecord:
        rec = self.strategies[strategy_id]
        allowed = ALLOWED_TRANSITIONS.get(rec.state, set())
        if new_state not in allowed:
            raise ValueError(f"Transición ilegal {rec.state} → {new_state}")
        before = {"state": rec.state.value}
        rec.state = new_state
        self.audit.append(
            actor=actor,
            action="strategy.lifecycle_transition",
            resource=strategy_id,
            result="OK",
            before=before,
            after={"state": new_state.value},
        )
        return rec

    def evaluate_paper_validated(
        self,
        strategy_id: str,
        *,
        trading_days: int,
        trades: int,
        max_drawdown: float,
        critical_errors: int,
        risk_violations: int,
        reconciliation_ok: bool,
        out_of_sample_ok: bool,
        used_real_market_data: bool,
        realistic_costs: bool,
        criteria: PaperValidationCriteria | None = None,
    ) -> tuple[bool, list[str]]:
        c = criteria or PaperValidationCriteria()
        failures: list[str] = []
        # No validar solo por rentabilidad
        if trading_days < c.min_trading_days:
            failures.append("días operativos insuficientes")
        if trades < c.min_trades:
            failures.append("operaciones insuficientes")
        if max_drawdown > c.max_drawdown:
            failures.append("drawdown excedido")
        if c.require_no_critical_errors and critical_errors > 0:
            failures.append("errores críticos")
        if c.require_no_risk_violations and risk_violations > 0:
            failures.append("violaciones de riesgo")
        if c.require_reconciliation_ok and not reconciliation_ok:
            failures.append("reconciliación fallida")
        if c.require_out_of_sample and not out_of_sample_ok:
            failures.append("sin validación fuera de muestra")
        if c.require_real_market_data and not used_real_market_data:
            failures.append("faltan datos de mercado reales")
        if c.require_realistic_costs and not realistic_costs:
            failures.append("costos no realistas")
        ok = not failures
        if ok:
            self.transition(strategy_id, StrategyLifecycleState.PAPER_VALIDATED, "system")
        return ok, failures

    def request_live_restricted(
        self,
        strategy_id: str,
        requester: str,
        reason: str,
        limits: LiveRestrictedLimits | None = None,
    ):
        rec = self.strategies[strategy_id]
        if rec.state != StrategyLifecycleState.PAPER_VALIDATED:
            raise ValueError("Requiere PAPER_VALIDATED")
        limits = limits or LiveRestrictedLimits()
        return self.approvals.request(
            action="enable_live_trading",
            requester=requester,
            reason=reason,
            before={"state": rec.state.value},
            after={"state": StrategyLifecycleState.LIVE_RESTRICTED.value, "limits": limits.__dict__},
        )

    def apply_live_restricted_approval(
        self,
        strategy_id: str,
        approval_id: str,
        approver: str,
        *,
        checklist: dict[str, bool],
        activation_hours: int = 48,
    ) -> StrategyApprovalRecord:
        required = {
            "docs_complete",
            "code_review",
            "tests_passed",
            "security_tests",
            "emergency_tests",
            "backtest_done",
            "walk_forward_done",
            "paper_done",
            "two_admin_approvals",
            "limits_confirmed",
            "account_confirmed",
            "environment_confirmed",
            "credentials_confirmed",
        }
        missing = [k for k in required if not checklist.get(k)]
        if missing:
            raise ValueError(f"Checklist incompleto: {missing}")
        self.approvals.approve(approval_id, approver, role="ADMIN")
        rec = self.transition(strategy_id, StrategyLifecycleState.LIVE_RESTRICTED, approver)
        rec.approvers = list({*rec.approvers, approver})
        rec.approved_at = datetime.utcnow()
        rec.activation_expires_at = datetime.utcnow() + timedelta(hours=activation_hours)
        rec.checklist = checklist
        rec.limits = LiveRestrictedLimits().__dict__
        return rec

    def invalidate_on_version_change(self, strategy_id: str, new_commit: str, actor: str) -> None:
        rec = self.strategies[strategy_id]
        if new_commit != rec.git_commit and rec.state.value.startswith("LIVE"):
            self.transition(strategy_id, StrategyLifecycleState.SUSPENDED, actor)
            self.suspension_reasons[strategy_id] = "versión/código cambió — requiere nueva aprobación"
            rec.git_commit = new_commit

    def auto_suspend(self, strategy_id: str, reason: str, actor: str = "system") -> None:
        rec = self.strategies[strategy_id]
        if rec.state in {
            StrategyLifecycleState.LIVE_RESTRICTED,
            StrategyLifecycleState.LIVE_LIMITED,
            StrategyLifecycleState.LIVE_APPROVED,
        }:
            self.transition(strategy_id, StrategyLifecycleState.SUSPENDED, actor)
            self.suspension_reasons[strategy_id] = reason

    def run_canary(self, strategy_id: str) -> CanaryResult:
        rec = self.strategies[strategy_id]
        if rec.state != StrategyLifecycleState.LIVE_RESTRICTED:
            raise ValueError("Canary solo en LIVE_RESTRICTED")
        if rec.activation_expires_at and datetime.utcnow() > rec.activation_expires_at:
            raise ValueError("Activación expirada")
        # Una sola operación simulada de supervisión — no envía a broker real aquí
        details = {
            "mode": "canary",
            "max_positions": 1,
            "market_orders": False,
            "pause_after": True,
        }
        self.audit.append(
            actor="system",
            action="canary.execute",
            resource=strategy_id,
            result="OK",
            after=details,
        )
        return CanaryResult(executed=True, paused=True, details=details)

    def compare_shadow(
        self,
        live_signal: dict[str, Any],
        paper_signal: dict[str, Any],
    ) -> ShadowComparison:
        notes = []
        match = live_signal.get("symbol") == paper_signal.get("symbol") and live_signal.get(
            "side"
        ) == paper_signal.get("side")
        if not match:
            notes.append("señales divergentes")
        exp = None
        if live_signal.get("expected_price") is not None and paper_signal.get("expected_price") is not None:
            exp = float(live_signal["expected_price"]) - float(paper_signal["expected_price"])
        exe = None
        if live_signal.get("executed_price") is not None and paper_signal.get("executed_price") is not None:
            exe = float(live_signal["executed_price"]) - float(paper_signal["executed_price"])
        return ShadowComparison(
            signal_match=match,
            expected_price_diff=exp,
            executed_price_diff=exe,
            latency_ms_diff=None,
            notes=notes,
        )

    def pre_session_checklist(self, checks: dict[str, bool]) -> tuple[bool, list[str]]:
        required = [
            "market_open",
            "credentials_valid",
            "balance_ok",
            "portfolio_reconciled",
            "no_unknown_orders",
            "fresh_data",
            "emergency_stop_available",
            "notifications_ok",
            "db_ok",
            "redis_ok",
            "single_worker",
            "limits_loaded",
            "strategy_approved",
            "version_approved",
            "authorized_hours",
        ]
        missing = [k for k in required if not checks.get(k)]
        return len(missing) == 0, missing

    def daily_report(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": strategy_id,
            "state": self.strategies[strategy_id].state.value,
            "generated_at": datetime.utcnow().isoformat(),
            "disclaimer": "Reporte operativo. No garantiza de rentabilidad.",
            **payload,
        }

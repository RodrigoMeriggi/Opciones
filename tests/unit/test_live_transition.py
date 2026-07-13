"""Transición paper → live."""

from __future__ import annotations

import pytest

from opciones.modules.live_transition.service import (
    LiveRestrictedLimits,
    LiveTransitionService,
    StrategyLifecycleState,
)
from opciones.modules.security.approvals.dual import DualApprovalService
from opciones.modules.security.audit.log import ImmutableAuditLog


def _svc():
    audit = ImmutableAuditLog()
    return LiveTransitionService(audit, DualApprovalService(audit)), audit


def test_paper_validated_not_by_profit_alone():
    svc, _ = _svc()
    svc.register("s1", version="1", git_commit="abc")
    svc.transition("s1", StrategyLifecycleState.PAPER_TRADING, "admin")
    ok, failures = svc.evaluate_paper_validated(
        "s1",
        trading_days=2,
        trades=2,
        max_drawdown=0.01,
        critical_errors=0,
        risk_violations=0,
        reconciliation_ok=True,
        out_of_sample_ok=True,
        used_real_market_data=True,
        realistic_costs=True,
    )
    assert not ok
    assert "días operativos" in failures[0] or failures


def test_live_requires_dual_approval_and_checklist():
    svc, _ = _svc()
    svc.register("s2", version="1", git_commit="abc")
    svc.transition("s2", StrategyLifecycleState.PAPER_TRADING, "a")
    ok, _ = svc.evaluate_paper_validated(
        "s2",
        trading_days=30,
        trades=40,
        max_drawdown=0.05,
        critical_errors=0,
        risk_violations=0,
        reconciliation_ok=True,
        out_of_sample_ok=True,
        used_real_market_data=True,
        realistic_costs=True,
    )
    assert ok
    req = svc.request_live_restricted("s2", "admin1", "canary start")
    checklist = {k: True for k in [
        "docs_complete", "code_review", "tests_passed", "security_tests",
        "emergency_tests", "backtest_done", "walk_forward_done", "paper_done",
        "two_admin_approvals", "limits_confirmed", "account_confirmed",
        "environment_confirmed", "credentials_confirmed",
    ]}
    rec = svc.apply_live_restricted_approval("s2", req.id, "admin2", checklist=checklist)
    assert rec.state == StrategyLifecycleState.LIVE_RESTRICTED
    canary = svc.run_canary("s2")
    assert canary.paused


def test_version_change_suspends_live():
    svc, _ = _svc()
    svc.register("s3", version="1", git_commit="aaa")
    svc.strategies["s3"].state = StrategyLifecycleState.LIVE_RESTRICTED
    svc.invalidate_on_version_change("s3", "bbb", "ci")
    assert svc.strategies["s3"].state == StrategyLifecycleState.SUSPENDED


def test_auto_suspend_and_shadow():
    svc, _ = _svc()
    svc.register("s4", version="1", git_commit="c")
    svc.strategies["s4"].state = StrategyLifecycleState.LIVE_LIMITED
    svc.auto_suspend("s4", "portfolio mismatch")
    assert svc.strategies["s4"].state == StrategyLifecycleState.SUSPENDED
    cmp = svc.compare_shadow(
        {"symbol": "X", "side": "BUY", "expected_price": 10, "executed_price": 11},
        {"symbol": "X", "side": "BUY", "expected_price": 10, "executed_price": 10.5},
    )
    assert cmp.signal_match
    assert cmp.executed_price_diff == 0.5


def test_pre_session_checklist():
    svc, _ = _svc()
    ok, missing = svc.pre_session_checklist({})
    assert not ok and missing

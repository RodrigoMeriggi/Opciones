"""Tests gobierno, configuración y asistente."""

from __future__ import annotations

import pytest

from opciones.modules.config_service import ConfigCategory, ConfigurationService
from opciones.modules.governance import GovernanceStatus, StrategyDefinition, StrategyGovernanceService
from opciones.modules.operational_assistant import OperationalAssistantService, ReadOnlyDataGateway


def test_governance_promotion_requires_evidence():
    gov = StrategyGovernanceService()
    gov.register(
        StrategyDefinition(name="Trend", description="t", owner="alice", version="1.0.0")
    )
    gov.add_evidence("Trend", "1.0.0", "documentation")
    gov.promote("Trend", "1.0.0", GovernanceStatus.RESEARCH, actor="alice", reason="ok")
    with pytest.raises(PermissionError):
        gov.promote("Trend", "1.0.0", GovernanceStatus.BACKTESTED, actor="alice", reason="no")


def test_governance_full_paper_path():
    gov = StrategyGovernanceService()
    gov.register(StrategyDefinition(name="T", description="", owner="a", version="1.0.0"))
    for flag in (
        "documentation",
        "tests",
        "reproducible_results",
        "stress_testing",
        "risk_review",
        "technical_review",
        "versioning",
    ):
        gov.add_evidence("T", "1.0.0", flag)
    gov.promote("T", "1.0.0", GovernanceStatus.RESEARCH, actor="a", reason="doc")
    gov.promote("T", "1.0.0", GovernanceStatus.BACKTESTED, actor="a", reason="bt")
    gov.promote("T", "1.0.0", GovernanceStatus.PAPER_APPROVED, actor="a", reason="paper")
    assert gov.definitions["T@1.0.0"].status == GovernanceStatus.PAPER_APPROVED


def test_invalidation_suspends():
    gov = StrategyGovernanceService()
    gov.register(StrategyDefinition(name="T", description="", owner="a", version="1.0.0"))
    for flag in ("documentation", "tests", "reproducible_results", "stress_testing", "risk_review", "technical_review", "versioning"):
        gov.add_evidence("T", "1.0.0", flag)
    gov.promote("T", "1.0.0", GovernanceStatus.RESEARCH, actor="a", reason="x")
    gov.promote("T", "1.0.0", GovernanceStatus.BACKTESTED, actor="a", reason="x")
    gov.promote("T", "1.0.0", GovernanceStatus.PAPER_APPROVED, actor="a", reason="x")
    gov.invalidate("T", "1.0.0", "strategy_code", "a")
    assert gov.definitions["T@1.0.0"].status == GovernanceStatus.SUSPENDED


def test_config_atomic_apply_and_hot_reload_guard():
    cfg = ConfigurationService()
    cfg.set_layer(
        "defaults",
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "emergency_stop": True,
            "max_daily_loss": 50000,
            "max_per_trade": 5000,
            "max_capital": 100000,
            "max_drawdown": 0.15,
            "max_positions": 5,
            "allowed_assets": ["GGAL"],
            "stop_loss_pct": 0.2,
        },
    )
    draft = cfg.create_draft(
        category=ConfigCategory.RISK,
        payload={
            "max_daily_loss": 40000,
            "max_per_trade": 4000,
            "max_capital": 100000,
            "max_drawdown": 0.12,
            "max_positions": 4,
            "allowed_assets": ["GGAL"],
            "stop_loss_pct": 0.2,
        },
        created_by="admin",
    )
    assert draft.critical
    cfg.submit_for_approval(draft.content_hash)
    cfg.approve(draft.content_hash, "admin2")
    active = cfg.apply_atomic(draft.content_hash, "admin2")
    assert active.status.value == "ACTIVE"
    with pytest.raises(PermissionError):
        cfg.hot_reload("trading_mode", "live")
    cfg.hot_reload("log_level", "DEBUG")


def test_config_rejects_live_with_emergency_stop():
    cfg = ConfigurationService()
    with pytest.raises(ValueError):
        cfg.create_draft(
            category=ConfigCategory.APPLICATION,
            payload={
                "trading_mode": "live",
                "live_trading_enabled": True,
                "emergency_stop": True,
            },
            created_by="admin",
        )


def test_assistant_readonly_and_modes():
    gw = ReadOnlyDataGateway(
        {
            "mode": "PAPER",
            "decisions": [
                {
                    "id": "1",
                    "timestamp": "2026-07-13T10:00:00",
                    "contract_symbol": "GGALC4500",
                    "action": "BUY",
                    "entry_reason": "tendencia alcista",
                    "score": 72,
                }
            ],
            "orders": [],
            "positions": [],
            "audit": [],
            "metrics": {"exposure_pct": 0.2},
            "circuit_breaker": {"active": True, "reason": "daily_loss"},
            "active_strategy": {"name": "Trend", "version": "1.0.0"},
            "deployed_version": {"app": "0.4.0"},
            "incidents": [],
            "api_key": "SHOULD_NOT_LEAK",
        }
    )
    # gateway get on secret key
    with pytest.raises(PermissionError):
        gw.get("api_key")
    asst = OperationalAssistantService(gw)
    ans = asst.ask("¿Por qué compró esta opción?", role="TRADER")
    assert ans.data_mode.value == "PAPER"
    assert "GGALC4500" in ans.summary or ans.evidence
    refused = asst.ask("Crear orden de compra ahora", role="ADMIN")
    assert refused.refused_action == "forbidden_action"
    missing = asst.ask("¿Qué incidentes ocurrieron?", role="ADMIN")
    assert missing.missing_data or missing.confidence < 1

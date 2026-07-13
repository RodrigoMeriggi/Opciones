"""Pruebas de seguridad."""

from __future__ import annotations

import pytest

from opciones.modules.security.approvals.dual import DualApprovalService
from opciones.modules.security.audit.log import ImmutableAuditLog
from opciones.modules.security.auth.sessions import (
    SessionManager,
    UserStore,
    hash_password,
    verify_password,
)
from opciones.modules.security.rbac.permissions import Permission, has_permission
from opciones.modules.security.secrets.provider import (
    LocalDevelopmentSecretProvider,
    redact,
)


def test_password_hashing_not_plaintext():
    h = hash_password("secret-pass")
    assert "secret-pass" not in h
    assert verify_password("secret-pass", h)
    assert not verify_password("wrong", h)


def test_roles_permissions():
    assert has_permission("ADMIN", Permission.LIVE_TRADING_APPROVE)
    assert not has_permission("TRADER", Permission.LIVE_TRADING_APPROVE)
    assert not has_permission("VIEWER", Permission.ORDERS_CANCEL)


def test_sessions_refresh_and_revoke():
    store = UserStore()
    user = store.create("alice", "pw", "ADMIN")
    sm = SessionManager(access_ttl=60, refresh_ttl=3600, max_sessions_per_user=2)
    access, refresh = sm.create_session(user, ip="1.1.1.1")
    parsed = sm.parse_access(access.token)
    assert parsed.username == "alice"
    access2, refresh2 = sm.refresh(refresh)
    assert refresh2 != refresh
    with pytest.raises(PermissionError):
        sm.refresh(refresh)  # rotated
    sm.revoke(access2.session_id)
    with pytest.raises(PermissionError):
        sm.parse_access(access2.token)


def test_audit_immutable_chain():
    log = ImmutableAuditLog()
    log.append(actor="a", action="login", resource="auth", result="OK")
    log.append(actor="a", action="settings.write", resource="risk", result="OK", before={"x": 1}, after={"x": 2})
    assert log.verify_chain()
    # mutación externa no expuesta: lista es copia
    events = log.events
    assert events[0].prev_hash == "GENESIS"


def test_dual_approval_requires_different_admin():
    audit = ImmutableAuditLog()
    svc = DualApprovalService(audit)
    req = svc.request(
        action="enable_live_trading",
        requester="admin1",
        reason="canary",
        after={"state": "LIVE_RESTRICTED"},
    )
    with pytest.raises(PermissionError):
        svc.approve(req.id, "admin1", role="ADMIN")
    approved = svc.approve(req.id, "admin2", role="ADMIN")
    assert approved.status == "APPROVED"


def test_secrets_not_logged_via_redact():
    assert redact("super-secret") == "***REDACTED***"
    p = LocalDevelopmentSecretProvider()
    p.set("BROKER_API_KEY", "abc")
    assert p.get("BROKER_API_KEY") == "abc"

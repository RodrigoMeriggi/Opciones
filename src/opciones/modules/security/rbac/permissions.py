"""RBAC: roles + permisos granulares."""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"
    SETTINGS_CRITICAL = "settings.critical"
    STRATEGY_READ = "strategy.read"
    STRATEGY_WRITE = "strategy.write"
    ORDERS_READ = "orders.read"
    ORDERS_CANCEL = "orders.cancel"
    POSITIONS_READ = "positions.read"
    POSITIONS_CLOSE = "positions.close"
    RISK_READ = "risk.read"
    RISK_WRITE = "risk.write"
    EMERGENCY_STOP_ACTIVATE = "emergency_stop.activate"
    EMERGENCY_STOP_DEACTIVATE = "emergency_stop.deactivate"
    LIVE_TRADING_APPROVE = "live_trading.approve"
    AUDIT_READ = "audit.read"


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "ADMIN": set(Permission),
    "TRADER": {
        Permission.SETTINGS_READ,
        Permission.STRATEGY_READ,
        Permission.STRATEGY_WRITE,
        Permission.ORDERS_READ,
        Permission.ORDERS_CANCEL,
        Permission.POSITIONS_READ,
        Permission.POSITIONS_CLOSE,
        Permission.RISK_READ,
        Permission.EMERGENCY_STOP_ACTIVATE,
    },
    "VIEWER": {
        Permission.SETTINGS_READ,
        Permission.STRATEGY_READ,
        Permission.ORDERS_READ,
        Permission.POSITIONS_READ,
        Permission.RISK_READ,
        Permission.AUDIT_READ,
    },
}


def has_permission(role: str, permission: Permission | str) -> bool:
    perm = permission if isinstance(permission, Permission) else Permission(permission)
    return perm in ROLE_PERMISSIONS.get(role, set())

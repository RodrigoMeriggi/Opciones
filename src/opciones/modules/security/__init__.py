"""Security package exports."""

from opciones.modules.security.approvals.dual import DualApprovalService
from opciones.modules.security.audit.log import ImmutableAuditLog
from opciones.modules.security.auth.sessions import SessionManager, UserStore, hash_password
from opciones.modules.security.rbac.permissions import Permission, has_permission
from opciones.modules.security.secrets.provider import (
    CloudSecretProvider,
    EnvironmentSecretProvider,
    LocalDevelopmentSecretProvider,
    SecretProvider,
)

__all__ = [
    "DualApprovalService",
    "ImmutableAuditLog",
    "SessionManager",
    "UserStore",
    "hash_password",
    "Permission",
    "has_permission",
    "SecretProvider",
    "EnvironmentSecretProvider",
    "LocalDevelopmentSecretProvider",
    "CloudSecretProvider",
]

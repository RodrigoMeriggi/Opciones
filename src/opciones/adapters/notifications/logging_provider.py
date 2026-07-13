"""Notificaciones — stub local. Integración externa pendiente de documentación."""

from __future__ import annotations

import logging

from opciones.ports import NotificationProvider

logger = logging.getLogger(__name__)


class LoggingNotificationProvider(NotificationProvider):
    """Implementación inicial: solo registra en logs.

    DOCUMENTACIÓN FALTANTE para proveedores reales (email/Slack/Telegram):
    - Endpoint o credenciales del canal elegido
    - Formato de payload y autenticación
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        payload = {"subject": subject, "message": message, "severity": severity}
        self.messages.append(payload)
        logger.log(
            logging.WARNING if severity in {"warning", "error", "critical"} else logging.INFO,
            "NOTIFY [%s] %s — %s",
            severity,
            subject,
            message,
        )

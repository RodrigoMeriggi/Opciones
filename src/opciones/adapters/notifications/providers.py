"""Notificaciones — console + stubs documentados."""

from __future__ import annotations

from opciones.adapters.notifications.logging_provider import LoggingNotificationProvider
from opciones.ports import NotificationProvider


class ConsoleNotificationProvider(LoggingNotificationProvider):
    """Alias explícito pedido por el servicio autónomo."""


class EmailNotificationProvider(NotificationProvider):
    """DOCUMENTACIÓN FALTANTE: SMTP/API del proveedor de email."""

    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        raise NotImplementedError("Email: falta documentación/credenciales del proveedor")


class TelegramNotificationProvider(NotificationProvider):
    """DOCUMENTACIÓN FALTANTE: bot token y chat_id oficiales."""

    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        raise NotImplementedError("Telegram: falta documentación del bot")


class WhatsAppNotificationProvider(NotificationProvider):
    """DOCUMENTACIÓN FALTANTE: API Business / proveedor."""

    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        raise NotImplementedError("WhatsApp: falta documentación del proveedor")


class SlackNotificationProvider(NotificationProvider):
    """DOCUMENTACIÓN FALTANTE: webhook o OAuth de Slack."""

    async def send(self, subject: str, message: str, severity: str = "info") -> None:
        raise NotImplementedError("Slack: falta documentación del workspace")

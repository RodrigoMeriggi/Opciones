"""Logging estructurado JSON sin secretos."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

_SECRET_KEYS = re.compile(
    r"(password|token|api[_-]?key|secret|authorization|cookie|refresh)",
    re.I,
)


def sanitize(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        if _SECRET_KEYS.search(str(k)):
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = sanitize(v)
        else:
            out[k] = v
    return out


class StructuredLogger:
    def __init__(self, service: str = "opciones", version: str = "0.2.0") -> None:
        self.service = service
        self.version = version
        self._logger = logging.getLogger("opciones.structured")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def log(
        self,
        severity: str,
        message: str,
        *,
        correlation_id: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        # Señales descartadas no son ERROR
        payload = sanitize(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": fields.pop("environment", "local"),
                "service": self.service,
                "version": self.version,
                "severity": severity.upper(),
                "message": message,
                "correlation_id": correlation_id,
                **fields,
            }
        )
        line = json.dumps(payload, default=str)
        level = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }.get(severity.upper(), logging.INFO)
        self._logger.log(level, line)
        return payload

"""Idempotencia de órdenes hacia brokers externos."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class IdempotentOrderKey:
    client_order_id: str
    correlation_id: str
    strategy_decision_id: str | None
    timestamp: datetime
    params_hash: str


@dataclass
class IdempotencyStore:
    """Registro en memoria de órdenes enviadas / conocidas."""

    _by_client_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_hash: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def hash_params(params: dict[str, Any]) -> str:
        payload = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def build_key(
        self,
        params: dict[str, Any],
        *,
        correlation_id: str | None = None,
        strategy_decision_id: str | None = None,
        client_order_id: str | None = None,
    ) -> IdempotentOrderKey:
        return IdempotentOrderKey(
            client_order_id=client_order_id or str(uuid4()),
            correlation_id=correlation_id or str(uuid4()),
            strategy_decision_id=strategy_decision_id,
            timestamp=datetime.utcnow(),
            params_hash=self.hash_params(params),
        )

    def remember(self, key: IdempotentOrderKey, status: str, external_id: str | None = None) -> None:
        self._by_client_id[key.client_order_id] = {
            "status": status,
            "external_id": external_id,
            "params_hash": key.params_hash,
            "correlation_id": key.correlation_id,
            "strategy_decision_id": key.strategy_decision_id,
            "timestamp": key.timestamp.isoformat(),
        }
        self._by_hash[key.params_hash] = key.client_order_id

    def get(self, client_order_id: str) -> dict[str, Any] | None:
        return self._by_client_id.get(client_order_id)

    def find_duplicate(self, params: dict[str, Any]) -> dict[str, Any] | None:
        h = self.hash_params(params)
        cid = self._by_hash.get(h)
        if not cid:
            return None
        return self._by_client_id.get(cid)

    def decide_before_resend(self, params: dict[str, Any], queried_status: str | None) -> dict[str, Any]:
        """
        Antes de reenviar tras error:
        1) buscar duplicado local
        2) considerar estado remoto si se consultó
        """
        existing = self.find_duplicate(params)
        if existing:
            return {
                "action": "DO_NOT_RESEND",
                "reason": "Orden con mismo hash ya registrada localmente",
                "existing": existing,
            }
        if queried_status in {"FILLED", "PARTIALLY_FILLED", "PENDING", "SUBMITTED"}:
            return {
                "action": "DO_NOT_RESEND",
                "reason": f"Estado remoto indica {queried_status}",
                "remote_status": queried_status,
            }
        if queried_status in {"REJECTED", "CANCELLED", "EXPIRED", None}:
            return {
                "action": "MAY_RESEND",
                "reason": "No hay evidencia de orden viva",
                "remote_status": queried_status,
            }
        return {
            "action": "QUERY_REQUIRED",
            "reason": "Estado incierto — consultar antes de reenviar",
            "remote_status": queried_status,
        }

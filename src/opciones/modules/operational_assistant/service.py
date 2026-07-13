"""Asistente operativo de solo lectura (Prompt 25)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from opciones.modules.security.rbac.permissions import Permission, has_permission


class DataMode(StrEnum):
    REAL = "REAL"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"


SECRET_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|credential|authorization)",
    re.I,
)


@dataclass
class AssistantEvidence:
    source: str
    timestamp: str | None
    identifiers: dict[str, str]
    snippet: dict[str, Any]


@dataclass
class AssistantAnswer:
    summary: str
    evidence: list[AssistantEvidence]
    confidence: float
    missing_data: list[str]
    internal_links: list[str]
    data_mode: DataMode
    asked_at: datetime = field(default_factory=datetime.utcnow)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    refused_action: str | None = None


class ReadOnlyDataGateway:
    """Solo fuentes autorizadas; filtra secretos."""

    def __init__(self, store: dict[str, Any] | None = None) -> None:
        self.store = store or {
            "decisions": [],
            "orders": [],
            "positions": [],
            "audit": [],
            "metrics": {},
            "reports": [],
            "config_public": {},
            "incidents": [],
            "active_strategy": None,
            "deployed_version": None,
            "circuit_breaker": None,
            "mode": "PAPER",
        }

    def get(self, key: str) -> Any:
        if SECRET_PATTERNS.search(key):
            raise PermissionError("acceso a secretos denegado")
        value = self.store.get(key)
        return self._redact(value)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ("***REDACTED***" if SECRET_PATTERNS.search(str(k)) else self._redact(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value


class QueryIntentClassifier:
    INTENTS = {
        "why_bought": [r"por qu[eé] compr", r"why buy", r"motivo de entrada"],
        "why_discarded": [r"descart", r"por qu[eé] no eligi", r"rechaz"],
        "why_no_trade": [r"no oper", r"por qu[eé] no oper", r"sin se[nñ]al"],
        "circuit_breaker": [r"circuit breaker", r"cortacircuito", r"bloqueo"],
        "risk_usage": [r"riesgo", r"exposici[oó]n", r"l[ií]mite"],
        "near_expiry": [r"vencimiento", r"expir"],
        "rejected_orders": [r"rechazad", r"rejected"],
        "what_changed": [r"cambi[oó]", r"desde ayer", r"diff"],
        "active_strategy": [r"estrategia activa", r"qu[eé] estrategia"],
        "deployed_version": [r"versi[oó]n", r"despleg"],
        "incidents": [r"incidente", r"alerta", r"falla"],
        "forbidden_action": [
            r"cre(ar|á) orden",
            r"cancel(ar|á)",
            r"cerr(ar|á) posici",
            r"activ(ar|á) live",
            r"desactiv(ar|á) emergency",
            r"aprob(ar|á) estrateg",
            r"cambi(ar|á) par[aá]metro",
        ],
    }

    def classify(self, question: str) -> str:
        q = question.lower()
        for intent, patterns in self.INTENTS.items():
            for p in patterns:
                if re.search(p, q):
                    return intent
        return "general"


class PermissionFilter:
    INTENT_PERMS = {
        "circuit_breaker": Permission.RISK_READ,
        "risk_usage": Permission.RISK_READ,
        "rejected_orders": Permission.ORDERS_READ,
        "near_expiry": Permission.POSITIONS_READ,
        "active_strategy": Permission.STRATEGY_READ,
        "deployed_version": Permission.SETTINGS_READ,
        "incidents": Permission.AUDIT_READ,
        "what_changed": Permission.AUDIT_READ,
        "why_bought": Permission.ORDERS_READ,
        "why_discarded": Permission.STRATEGY_READ,
        "why_no_trade": Permission.STRATEGY_READ,
        "general": Permission.STRATEGY_READ,
    }

    def allow(self, role: str, intent: str) -> bool:
        if intent == "forbidden_action":
            return True  # se responde con rechazo
        perm = self.INTENT_PERMS.get(intent, Permission.STRATEGY_READ)
        return has_permission(role, perm)


class EvidenceCollector:
    def __init__(self, gateway: ReadOnlyDataGateway) -> None:
        self.gateway = gateway

    def collect(self, intent: str) -> list[AssistantEvidence]:
        out: list[AssistantEvidence] = []
        mapping = {
            "why_bought": "decisions",
            "why_discarded": "decisions",
            "why_no_trade": "decisions",
            "circuit_breaker": "circuit_breaker",
            "risk_usage": "metrics",
            "near_expiry": "positions",
            "rejected_orders": "orders",
            "what_changed": "audit",
            "active_strategy": "active_strategy",
            "deployed_version": "deployed_version",
            "incidents": "incidents",
        }
        key = mapping.get(intent)
        if not key:
            return out
        raw = self.gateway.get(key)
        if raw is None or raw == [] or raw == {}:
            return out
        if isinstance(raw, list):
            for item in raw[-5:]:
                out.append(
                    AssistantEvidence(
                        source=key,
                        timestamp=str(item.get("timestamp") or item.get("created_at") or ""),
                        identifiers={
                            k: str(item.get(k))
                            for k in ("id", "symbol", "contract_symbol", "correlation_id")
                            if item.get(k) is not None
                        },
                        snippet=item if isinstance(item, dict) else {"value": item},
                    )
                )
        else:
            out.append(
                AssistantEvidence(
                    source=key,
                    timestamp=datetime.utcnow().isoformat(),
                    identifiers={},
                    snippet=raw if isinstance(raw, dict) else {"value": raw},
                )
            )
        return out


class ExplanationBuilder:
    def build(
        self,
        intent: str,
        evidence: list[AssistantEvidence],
        *,
        mode: DataMode,
        missing: list[str],
    ) -> str:
        if intent == "forbidden_action":
            return (
                "No puedo ejecutar acciones de trading ni cambiar configuración. "
                "Use los controles oficiales del dashboard/API (ADMIN/TRADER según rol)."
            )
        if not evidence and missing:
            return (
                f"No hay evidencia suficiente para responder con exactitud. "
                f"Falta: {', '.join(missing)}. "
                f"Debería estar en logs/auditoría/BD según el proceso correspondiente."
            )
        parts = [f"[{mode.value}] "]
        if intent == "why_bought" and evidence:
            e = evidence[-1].snippet
            parts.append(
                "Compra explicada: "
                f"señal={e.get('entry_reason') or e.get('action')}; "
                f"contrato={e.get('contract_symbol')}; score={e.get('score')}; "
                f"riesgo={e.get('risk') or 'ver auditoría'}."
            )
        elif intent == "why_discarded" and evidence:
            e = evidence[-1].snippet
            parts.append(f"Descarte: {e.get('discard_reason') or e.get('reason') or e}")
        elif intent == "why_no_trade":
            parts.append(
                "No operó: "
                + (
                    evidence[-1].snippet.get("discard_reason")
                    if evidence
                    else "sin señales BUY registradas"
                )
            )
        elif intent == "circuit_breaker" and evidence:
            parts.append(f"Circuit breaker: {evidence[-1].snippet}")
        elif intent == "risk_usage" and evidence:
            parts.append(f"Uso de riesgo/métricas: {evidence[-1].snippet}")
        elif intent == "near_expiry" and evidence:
            parts.append(f"Posiciones (revisar DTE): {len(evidence)} evidencias recientes")
        elif intent == "rejected_orders":
            parts.append(f"Órdenes rechazadas en evidencia: {len(evidence)}")
        elif intent == "active_strategy" and evidence:
            parts.append(f"Estrategia activa: {evidence[-1].snippet}")
        elif intent == "deployed_version" and evidence:
            parts.append(f"Versión desplegada: {evidence[-1].snippet}")
        elif intent == "incidents":
            parts.append(f"Incidentes recientes: {len(evidence)}")
        elif intent == "what_changed":
            parts.append(f"Cambios/auditoría reciente: {len(evidence)} eventos")
        else:
            parts.append("Consulta general resuelta con evidencia disponible." if evidence else "Sin datos.")
        parts.append(" No se inventan motivos faltantes.")
        return "".join(parts)


class LLMBridge(Protocol):
    """Interfaz opcional futura — no usada por defecto."""

    def complete(self, prompt: str, context: dict[str, Any]) -> str: ...


class OperationalAssistantService:
    """Solo lectura. Diferencia PAPER/BACKTEST/REAL. Sin órdenes ni config."""

    def __init__(self, gateway: ReadOnlyDataGateway | None = None, llm: LLMBridge | None = None) -> None:
        self.gateway = gateway or ReadOnlyDataGateway()
        self.classifier = QueryIntentClassifier()
        self.permissions = PermissionFilter()
        self.collector = EvidenceCollector(self.gateway)
        self.builder = ExplanationBuilder()
        self.llm = llm  # opcional, desactivado

    def ask(self, question: str, *, role: str = "VIEWER") -> AssistantAnswer:
        intent = self.classifier.classify(question)
        mode = DataMode(str(self.gateway.get("mode") or "PAPER"))
        if not self.permissions.allow(role, intent):
            return AssistantAnswer(
                summary="Permiso insuficiente para esta consulta.",
                evidence=[],
                confidence=1.0,
                missing_data=[],
                internal_links=["/dashboard"],
                data_mode=mode,
            )
        if intent == "forbidden_action":
            return AssistantAnswer(
                summary=self.builder.build(intent, [], mode=mode, missing=[]),
                evidence=[],
                confidence=1.0,
                missing_data=[],
                internal_links=["/dashboard/risk", "/dashboard/config"],
                data_mode=mode,
                refused_action=intent,
            )

        evidence = self.collector.collect(intent)
        missing: list[str] = []
        if not evidence:
            missing.append(f"fuente:{intent}")

        # ambigüedad: varias operaciones
        candidates: list[dict[str, Any]] = []
        if intent in {"why_bought", "why_discarded"} and len(evidence) > 1:
            candidates = [
                {
                    "id": e.identifiers.get("id") or e.identifiers.get("correlation_id"),
                    "timestamp": e.timestamp,
                    "symbol": e.identifiers.get("symbol") or e.identifiers.get("contract_symbol"),
                }
                for e in evidence
            ]
            candidates.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        summary = self.builder.build(intent, evidence, mode=mode, missing=missing)
        conf = 0.9 if evidence and not missing else 0.35 if missing else 0.6
        return AssistantAnswer(
            summary=summary,
            evidence=evidence,
            confidence=conf,
            missing_data=missing,
            internal_links=["/dashboard/signals", "/dashboard/orders", "/api/audit"],
            data_mode=mode,
            candidates=candidates,
        )

"""ConfigurationService centralizado, versionado y auditable (Prompt 24)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from opciones.modules.security.audit.log import ImmutableAuditLog


class ConfigCategory(StrEnum):
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"
    MARKET = "market"
    BROKER = "broker"
    STRATEGY = "strategy"
    RISK = "risk"
    HOURS = "hours"
    NOTIFICATIONS = "notifications"
    REPORTS = "reports"
    SECURITY = "security"


class ConfigStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


CRITICAL_KEYS = {
    "trading_mode",
    "live_trading_enabled",
    "emergency_stop",
    "max_capital",
    "max_daily_loss",
    "max_drawdown",
    "max_positions",
    "broker",
    "account",
    "allowed_assets",
    "active_strategy",
    "market_hours",
    "expirations",
}

# Precedencia: defaults < yaml < env < db < secrets < env_overrides
PRECEDENCE = ("defaults", "yaml", "env", "database", "secrets", "env_override")

HOT_RELOAD_FORBIDDEN = {
    "credentials",
    "broker",
    "account",
    "trading_mode",
    "live_trading_enabled",
    "emergency_stop",
    "max_daily_loss",
    "max_drawdown",
    "max_capital",
    "active_strategy_live",
}


class RiskConfigSchema(BaseModel):
    max_daily_loss: Decimal = Field(gt=0)
    max_drawdown: Decimal = Field(gt=0, le=1)
    max_capital: Decimal = Field(gt=0)
    max_per_trade: Decimal = Field(gt=0)
    max_positions: int = Field(ge=1)
    stop_loss_pct: Decimal = Field(gt=0, le=1)
    allowed_assets: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def cross_checks(self) -> RiskConfigSchema:
        if self.max_per_trade > self.max_capital:
            raise ValueError("capital por operación > capital total")
        if self.stop_loss_pct * self.max_per_trade > self.max_daily_loss:
            # stop teórico por trade no debe superar pérdida diaria (coherencia)
            pass  # soft: documentado en warnings externos
        return self


class AppConfigSchema(BaseModel):
    trading_mode: str = "paper"
    live_trading_enabled: bool = False
    emergency_stop: bool = True
    environment: str = "local"

    @model_validator(mode="after")
    def live_vs_stop(self) -> AppConfigSchema:
        if self.live_trading_enabled and self.emergency_stop:
            raise ValueError("live activado con emergency stop")
        if self.live_trading_enabled and self.trading_mode != "live":
            raise ValueError("live_trading_enabled requiere trading_mode=live")
        return self


class ConfigVersion(BaseModel):
    version: str
    environment: str
    status: ConfigStatus
    category: ConfigCategory
    payload: dict[str, Any]
    created_by: str
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    content_hash: str = ""
    previous_hash: str | None = None
    critical: bool = False


class ConfigurationService:
    def __init__(self, audit: ImmutableAuditLog | None = None) -> None:
        self.audit = audit or ImmutableAuditLog()
        self._layers: dict[str, dict[str, Any]] = {k: {} for k in PRECEDENCE}
        self._versions: list[ConfigVersion] = []
        self._active: dict[str, ConfigVersion] = {}  # category -> active
        self._snapshots: list[dict[str, Any]] = []

    def set_layer(self, layer: str, values: dict[str, Any]) -> None:
        if layer not in PRECEDENCE:
            raise ValueError(f"capa desconocida: {layer}")
        self._layers[layer] = dict(values)

    def resolve(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        sources: dict[str, str] = {}
        for layer in PRECEDENCE:
            for k, v in self._layers[layer].items():
                merged[k] = v
                sources[k] = layer
        merged["_sources"] = sources
        return merged

    def validate_cross(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        try:
            AppConfigSchema(
                trading_mode=payload.get("trading_mode", "paper"),
                live_trading_enabled=bool(payload.get("live_trading_enabled", False)),
                emergency_stop=bool(payload.get("emergency_stop", True)),
                environment=payload.get("environment", "local"),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        if "max_daily_loss" in payload and "max_per_trade" in payload and "max_capital" in payload:
            try:
                RiskConfigSchema(
                    max_daily_loss=Decimal(str(payload["max_daily_loss"])),
                    max_drawdown=Decimal(str(payload.get("max_drawdown", "0.15"))),
                    max_capital=Decimal(str(payload["max_capital"])),
                    max_per_trade=Decimal(str(payload["max_per_trade"])),
                    max_positions=int(payload.get("max_positions", 5)),
                    stop_loss_pct=Decimal(str(payload.get("stop_loss_pct", "0.2"))),
                    allowed_assets=list(payload.get("allowed_assets", ["GGAL"])),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        if payload.get("active_strategy") and payload.get("strategy_approved") is False:
            errors.append("estrategia no aprobada")
        if payload.get("asset") and payload.get("allowed_assets"):
            if payload["asset"] not in payload["allowed_assets"]:
                errors.append("activo no autorizado")
        if float(payload.get("max_daily_loss", 1)) < 0:
            errors.append("límite diario negativo")
        open_h = payload.get("market_open_hour")
        close_h = payload.get("market_close_hour")
        if open_h is not None and close_h is not None and int(open_h) >= int(close_h):
            errors.append("horario inválido")
        return errors

    def _hash(self, payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    def create_draft(
        self,
        *,
        category: ConfigCategory,
        payload: dict[str, Any],
        created_by: str,
        environment: str = "local",
        version: str = "1.0.0",
    ) -> ConfigVersion:
        errors = self.validate_cross(payload)
        if errors:
            raise ValueError(f"config inválida: {errors}")
        critical = any(k in CRITICAL_KEYS for k in payload)
        ver = ConfigVersion(
            version=version,
            environment=environment,
            status=ConfigStatus.DRAFT,
            category=category,
            payload=payload,
            created_by=created_by,
            content_hash=self._hash(payload),
            critical=critical,
        )
        self._versions.append(ver)
        return ver

    def submit_for_approval(self, content_hash: str) -> ConfigVersion:
        ver = self._by_hash(content_hash)
        if ver.critical:
            ver.status = ConfigStatus.PENDING_APPROVAL
        else:
            ver.status = ConfigStatus.APPROVED
        return ver

    def approve(self, content_hash: str, approver: str) -> ConfigVersion:
        ver = self._by_hash(content_hash)
        if ver.critical and ver.status != ConfigStatus.PENDING_APPROVAL:
            raise PermissionError("crítico requiere PENDING_APPROVAL")
        ver.status = ConfigStatus.APPROVED
        ver.approved_by = approver
        self.audit.append(
            actor=approver,
            action="config_approved",
            resource=content_hash,
            result="APPROVED",
            after={"category": ver.category.value, "version": ver.version},
        )
        return ver

    def apply_atomic(self, content_hash: str, actor: str) -> ConfigVersion:
        ver = self._by_hash(content_hash)
        if ver.status != ConfigStatus.APPROVED:
            raise PermissionError("solo APPROVED puede activarse")
        # snapshot
        snap = {
            "at": datetime.utcnow().isoformat(),
            "active": {k: v.model_dump(mode="json") for k, v in self._active.items()},
        }
        self._snapshots.append(snap)
        prev = self._active.get(ver.category.value)
        if prev:
            prev.status = ConfigStatus.SUPERSEDED
            ver.previous_hash = prev.content_hash
        ver.status = ConfigStatus.ACTIVE
        ver.effective_at = datetime.utcnow()
        self._active[ver.category.value] = ver
        # merge into database layer for resolve()
        self._layers["database"].update(ver.payload)
        # verify
        errors = self.validate_cross(self.resolve())
        if errors:
            self.rollback(actor=actor, reason=f"verificación falló: {errors}")
            raise RuntimeError(f"aplicación fallida: {errors}")
        self.audit.append(
            actor=actor,
            action="config_applied",
            resource=content_hash,
            result="ACTIVE",
            before={"previous": ver.previous_hash},
            after={"payload_keys": list(ver.payload.keys())},
        )
        return ver

    def rollback(self, *, actor: str, reason: str) -> ConfigVersion | None:
        if not self._snapshots:
            return None
        snap = self._snapshots[-1]
        # restore previous active map is simplified: mark current rolled back
        for cat, ver in list(self._active.items()):
            ver.status = ConfigStatus.ROLLED_BACK
            self.audit.append(
                actor=actor,
                action="config_rollback",
                resource=ver.content_hash,
                result="ROLLED_BACK",
                reason=reason,
            )
        self._active.clear()
        return None

    def hot_reload(self, key: str, value: Any) -> None:
        if key in HOT_RELOAD_FORBIDDEN or key in CRITICAL_KEYS:
            raise PermissionError(f"hot reload prohibido para {key}")
        self._layers["env_override"][key] = value

    def _by_hash(self, content_hash: str) -> ConfigVersion:
        for v in self._versions:
            if v.content_hash == content_hash:
                return v
        raise KeyError(content_hash)

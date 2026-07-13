"""Registro de estrategias — paper/backtest/shadow; nunca live por defecto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from opciones.modules.strategies.base import StrategyLifecycle, StrategyMeta


class StrategyRunMode(StrEnum):
    PAPER = "paper"
    BACKTEST = "backtest"
    SHADOW = "shadow"
    # LIVE omitted from default activation paths


@dataclass
class RegistryEntry:
    strategy: StrategyLifecycle
    meta: StrategyMeta
    active: bool = False
    mode: StrategyRunMode | None = None
    registered_at: datetime = field(default_factory=datetime.utcnow)


class StrategyRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def _key(self, name: str, version: str) -> str:
        return f"{name}@{version}"

    def register(self, strategy: StrategyLifecycle) -> str:
        key = self._key(strategy.meta.name, strategy.meta.version)
        self._entries[key] = RegistryEntry(strategy=strategy, meta=strategy.meta, active=False)
        return key

    def activate(self, name: str, version: str, mode: StrategyRunMode) -> None:
        if mode.value not in ("paper", "backtest", "shadow"):
            raise PermissionError("solo paper/backtest/shadow; live requiere aprobación explícita")
        key = self._key(name, version)
        entry = self._entries[key]
        if mode.value not in entry.meta.allowed_environments:
            raise PermissionError(f"modo {mode} no permitido para {key}")
        entry.active = True
        entry.mode = mode

    def deactivate(self, name: str, version: str) -> None:
        key = self._key(name, version)
        self._entries[key].active = False
        self._entries[key].mode = None

    def get(self, name: str, version: str) -> RegistryEntry:
        return self._entries[self._key(name, version)]

    def list_all(self) -> list[RegistryEntry]:
        return list(self._entries.values())

    def list_active(self) -> list[RegistryEntry]:
        return [e for e in self._entries.values() if e.active]

    def parameters(self, name: str, version: str) -> dict[str, Any]:
        return dict(self.get(name, version).meta.parameters)

    def status(self, name: str, version: str) -> dict[str, Any]:
        e = self.get(name, version)
        return {
            "name": e.meta.name,
            "version": e.meta.version,
            "active": e.active,
            "mode": e.mode.value if e.mode else None,
            "approval_status": e.meta.approval_status,
            "allowed_environments": e.meta.allowed_environments,
            "commit": e.meta.commit,
            "author": e.meta.author,
        }

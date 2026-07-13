"""Carga de configuración YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from opciones.domain.models import RiskLimits


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML inválido en {path}")
    return data


def load_strategy_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else Path(__file__).resolve().parents[3] / "config" / "strategy_basic.yaml"
    # parents: configuration -> modules -> opciones -> src -> root? 
    # __file__ = .../src/opciones/modules/configuration/loader.py
    # parents[0]=configuration, [1]=modules, [2]=opciones, [3]=src, [4]=root
    if path is None:
        p = Path(__file__).resolve().parents[4] / "config" / "strategy_basic.yaml"
    return load_yaml(p)


def load_risk_limits(path: str | Path | None = None) -> RiskLimits:
    if path is None:
        p = Path(__file__).resolve().parents[4] / "config" / "risk.yaml"
    else:
        p = Path(path)
    data = load_yaml(p)
    return RiskLimits(**data)

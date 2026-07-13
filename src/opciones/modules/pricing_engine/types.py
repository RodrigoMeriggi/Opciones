"""Tipos del motor de valuación."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExerciseStyle(StrEnum):
    EUROPEAN = "EUROPEAN"
    AMERICAN = "AMERICAN"


class PricingStatus(StrEnum):
    OK = "OK"
    INVALID_INPUT = "INVALID_INPUT"
    NO_CONVERGENCE = "NO_CONVERGENCE"
    ARBITRAGE_VIOLATION = "ARBITRAGE_VIOLATION"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"
    WARNING = "WARNING"


class PricingInputs(BaseModel):
    spot: float
    strike: float
    time_to_expiry_years: float
    rate: float
    dividend_yield: float = 0.0
    volatility: float | None = None
    option_type: str  # CALL / PUT
    exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN
    market_price: float | None = None
    contract_size: int = 1
    discrete_dividends: list[dict[str, float]] = Field(default_factory=list)
    # discrete: [{"t": years_from_now, "amount": cash}]
    assumptions: list[str] = Field(default_factory=list)


class Greeks(BaseModel):
    delta: float | None = None
    gamma: float | None = None
    theta_daily: float | None = None
    theta_annual: float | None = None
    vega_per_pct: float | None = None
    rho: float | None = None
    elasticity: float | None = None


class PricingResult(BaseModel):
    theoretical_price: float | None = None
    implied_volatility: float | None = None
    greeks: Greeks = Field(default_factory=Greeks)
    intrinsic_value: float | None = None
    extrinsic_value: float | None = None
    moneyness: str | None = None
    approx_itm_probability: float | None = None
    model: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data_source: str = "unspecified"
    interpolated: bool = False
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = 0.0  # 0-1
    warnings: list[str] = Field(default_factory=list)
    convergence_status: PricingStatus = PricingStatus.OK
    disclaimer: str = (
        "Métricas cuantitativas de referencia. No constituyen garantía de rentabilidad."
    )

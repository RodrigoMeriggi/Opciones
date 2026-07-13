"""Configuración y tipos del motor de backtesting."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BarFrequency(StrEnum):
    TICK = "tick"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"


class MarketEventType(StrEnum):
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSE = "MARKET_CLOSE"
    HOLIDAY = "HOLIDAY"
    EXPIRATION = "EXPIRATION"
    HALT = "HALT"
    PRICE_SHOCK = "PRICE_SHOCK"
    MISSING_DATA = "MISSING_DATA"
    STALE_QUOTE = "STALE_QUOTE"
    NO_TRADES = "NO_TRADES"
    CONTRACT_EXPIRED = "CONTRACT_EXPIRED"
    FORCE_EXIT = "FORCE_EXIT"


class BacktestConfig(BaseModel):
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("1000000")
    universe: list[str] = Field(default_factory=lambda: ["GGAL"])
    strategy_id: str = "basic_option_v1"
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    commission_rate: Decimal = Decimal("0.001")
    slippage_bps: Decimal = Decimal("5")
    latency_ms: int = 0
    min_volume: int = 10
    max_spread_pct: Decimal = Decimal("8")
    max_daily_loss: Decimal = Decimal("50000")
    frequency: BarFrequency = BarFrequency.D1
    force_exit_days_before_expiration: int = 3
    allow_partial: bool = True
    holidays: list[date] = Field(default_factory=list)
    market_open_hour: int = 11
    market_close_hour: int = 17
    timezone: str = "America/Argentina/Buenos_Aires"
    # Política: no mezclar frecuencias sin declarar
    mixed_frequency_policy: str = "reject"  # reject | upsample_ffill | downsample_last


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    exposure: Decimal
    drawdown: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class TradeRecord(BaseModel):
    symbol: str
    underlying: str
    option_type: str
    side: str
    quantity: int
    price: Decimal
    commission: Decimal
    slippage: Decimal
    timestamp: datetime
    pnl: Decimal | None = None
    entry_reason: str | None = None
    exit_reason: str | None = None
    expiration: date | None = None
    partial: bool = False
    rejected: bool = False
    rejection_reason: str | None = None


class PerformanceMetrics(BaseModel):
    total_return: Decimal
    annualized_return: Decimal
    net_profit: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    max_drawdown: Decimal
    max_drawdown_duration_days: int
    sharpe_ratio: float | None
    sortino_ratio: float | None
    profit_factor: float | None
    expectancy: Decimal
    win_rate: float
    avg_win: Decimal
    avg_loss: Decimal
    best_trade: Decimal
    worst_trade: Decimal
    max_consecutive_losses: int
    max_consecutive_wins: int
    avg_exposure: Decimal
    max_capital_used: Decimal
    total_commissions: Decimal
    total_slippage: Decimal
    rejected_orders: int
    partial_fills: int
    total_trades: int
    disclaimer: str = (
        "Resultados históricos simulados. No constituyen garantía de rentabilidad futura."
    )


class BacktestResult(BaseModel):
    config: BacktestConfig
    metrics: PerformanceMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    series: dict[str, Any] = Field(default_factory=dict)
    breakdowns: dict[str, Any] = Field(default_factory=dict)

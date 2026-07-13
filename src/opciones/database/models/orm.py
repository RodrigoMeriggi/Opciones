"""Modelos SQLAlchemy 2 para persistencia."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UnderlyingAssetRow(Base):
    __tablename__ = "underlying_assets"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(256), default="")
    currency: Mapped[str] = mapped_column(String(8), default="ARS")
    market: Mapped[str] = mapped_column(String(16), default="BYMA")
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OptionContractRow(Base):
    __tablename__ = "option_contracts"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    underlying_symbol: Mapped[str] = mapped_column(String(32), index=True)
    option_type: Mapped[str] = mapped_column(String(8))
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    expiration_date: Mapped[date] = mapped_column(Date, index=True)
    contract_size: Mapped[int] = mapped_column(Integer, default=1)
    currency: Mapped[str] = mapped_column(String(8), default="ARS")
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    intrinsic_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    extrinsic_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    days_to_expiration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    moneyness: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OrderRow(Base):
    __tablename__ = "orders"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    slippage: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    rejection_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_notes: Mapped[Any] = mapped_column(JSON, default=list)
    quote_used: Mapped[Any] = mapped_column(JSON, nullable=True)
    fills: Mapped[Any] = mapped_column(JSON, default=list)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PositionRow(Base):
    __tablename__ = "positions"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(32), index=True)
    option_type: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    average_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    expiration_date: Mapped[date] = mapped_column(Date)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioSnapshotRow(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    total_premium: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    weekly_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    trades_today: Mapped[int] = mapped_column(Integer, default=0)
    positions_by_underlying: Mapped[Any] = mapped_column(JSON, default=dict)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DecisionRecordRow(Base):
    __tablename__ = "decision_records"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    contract_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    underlying_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(16))
    indicators: Mapped[Any] = mapped_column(JSON, default=dict)
    score: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    score_components: Mapped[Any] = mapped_column(JSON, default=dict)
    rules_passed: Mapped[Any] = mapped_column(JSON, default=list)
    rules_failed: Mapped[Any] = mapped_column(JSON, default=list)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    discard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_risk: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    expected_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    executed_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RiskAuditRow(Base):
    __tablename__ = "risk_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean)
    codes: Mapped[Any] = mapped_column(JSON, default=list)
    payload: Mapped[Any] = mapped_column(JSON, default=dict)

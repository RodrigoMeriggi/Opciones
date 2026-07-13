"""Modelos de dominio: instrumentos y cotizaciones."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opciones.domain.enums import (
    Currency,
    Market,
    Moneyness,
    OptionStatus,
    OptionType,
    QuoteQuality,
)


class UnderlyingAsset(BaseModel):
    model_config = ConfigDict(frozen=False)

    symbol: str
    description: str = ""
    currency: Currency = Currency.ARS
    market: Market = Market.BYMA
    last_price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int | None = None
    timestamp: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class MarketQuote(BaseModel):
    instrument_symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    volume: int | None = None
    timestamp: datetime | None = None
    source: str = "unknown"
    is_delayed: bool = False

    @field_validator("instrument_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def mid(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def absolute_spread(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def percentage_spread(self) -> Decimal | None:
        abs_spread = self.absolute_spread
        if abs_spread is None or self.ask is None or self.ask <= 0:
            return None
        return (abs_spread / self.ask) * Decimal("100")

    def quality(self, max_age_seconds: int = 120) -> QuoteQuality:
        if self.bid is None or self.ask is None:
            return QuoteQuality.MISSING
        if self.ask <= 0:
            return QuoteQuality.INVALID
        if self.bid > self.ask:
            return QuoteQuality.INVALID
        if self.timestamp is None:
            return QuoteQuality.MISSING
        age = (datetime.utcnow() - self.timestamp.replace(tzinfo=None)).total_seconds()
        if age > max_age_seconds:
            return QuoteQuality.STALE
        return QuoteQuality.VALID


class OptionContract(BaseModel):
    symbol: str
    underlying_symbol: str
    option_type: OptionType
    strike: Decimal
    expiration_date: date
    contract_size: int = 1
    currency: Currency = Currency.ARS
    bid: Decimal | None = None
    ask: Decimal | None = None
    last_price: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    implied_volatility: Decimal | None = None
    intrinsic_value: Decimal | None = None
    extrinsic_value: Decimal | None = None
    days_to_expiration: int | None = None
    status: OptionStatus = OptionStatus.ACTIVE
    timestamp: datetime | None = None
    moneyness: Moneyness | None = None

    @field_validator("symbol", "underlying_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def absolute_spread(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def percentage_spread(self) -> Decimal | None:
        abs_spread = self.absolute_spread
        if abs_spread is None or self.ask is None or self.ask <= 0:
            return None
        return (abs_spread / self.ask) * Decimal("100")

    def to_quote(self, source: str = "option_contract") -> MarketQuote:
        return MarketQuote(
            instrument_symbol=self.symbol,
            bid=self.bid,
            ask=self.ask,
            last=self.last_price,
            volume=self.volume,
            timestamp=self.timestamp,
            source=source,
        )


class OptionChain(BaseModel):
    """Agrupa opciones de un subyacente por vencimiento, tipo y strike."""

    underlying_symbol: str
    underlying_price: Decimal | None = None
    as_of: datetime = Field(default_factory=datetime.utcnow)
    contracts: list[OptionContract] = Field(default_factory=list)

    @field_validator("underlying_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    def calls(self) -> list[OptionContract]:
        return [c for c in self.contracts if c.option_type == OptionType.CALL]

    def puts(self) -> list[OptionContract]:
        return [c for c in self.contracts if c.option_type == OptionType.PUT]

    def by_expiration(self) -> dict[date, list[OptionContract]]:
        grouped: dict[date, list[OptionContract]] = {}
        for contract in self.contracts:
            grouped.setdefault(contract.expiration_date, []).append(contract)
        for exp in grouped:
            grouped[exp] = sorted(grouped[exp], key=lambda c: (c.option_type, c.strike))
        return dict(sorted(grouped.items()))

    def by_type_and_strike(self) -> dict[OptionType, dict[Decimal, list[OptionContract]]]:
        result: dict[OptionType, dict[Decimal, list[OptionContract]]] = {
            OptionType.CALL: {},
            OptionType.PUT: {},
        }
        for contract in self.contracts:
            bucket = result[contract.option_type]
            bucket.setdefault(contract.strike, []).append(contract)
        for opt_type in result:
            result[opt_type] = dict(sorted(result[opt_type].items()))
        return result

    def expirations(self) -> list[date]:
        return sorted({c.expiration_date for c in self.contracts})


class RiskLimits(BaseModel):
    initial_capital: Decimal = Decimal("1000000")
    maximum_capital_at_risk: Decimal = Decimal("200000")
    maximum_position_percentage: Decimal = Decimal("0.35")
    maximum_loss_per_trade: Decimal = Decimal("25000")
    maximum_daily_loss: Decimal = Decimal("50000")
    maximum_weekly_loss: Decimal = Decimal("100000")
    maximum_drawdown: Decimal = Decimal("0.15")
    maximum_open_positions: int = 5
    maximum_positions_per_underlying: int = 2
    maximum_total_premium: Decimal = Decimal("300000")
    minimum_cash_reserve: Decimal = Decimal("100000")
    minimum_days_to_expiration: int = 5
    maximum_days_to_expiration: int = 60
    force_exit_days_before_expiration: int = 3
    maximum_bid_ask_spread_percentage: Decimal = Decimal("8")
    minimum_volume: int = 10
    maximum_consecutive_losses: int = 3
    daily_trade_limit: int = 20
    cooldown_after_loss_minutes: int = 30
    max_quote_age_seconds: int = 120
    abnormal_move_percentage: Decimal = Decimal("10")


class PortfolioSnapshot(BaseModel):
    cash: Decimal
    reserved_cash: Decimal = Decimal("0")
    equity: Decimal
    open_positions: int = 0
    total_premium: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    consecutive_losses: int = 0
    trades_today: int = 0
    positions_by_underlying: dict[str, int] = Field(default_factory=dict)
    last_loss_at: datetime | None = None
    as_of: datetime = Field(default_factory=datetime.utcnow)

    @property
    def available_cash(self) -> Decimal:
        return self.cash - self.reserved_cash

    @property
    def drawdown(self) -> Decimal:
        if self.peak_equity <= 0:
            return Decimal("0")
        return (self.peak_equity - self.equity) / self.peak_equity


class Position(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    underlying_symbol: str
    option_type: OptionType
    quantity: int
    average_price: Decimal
    current_price: Decimal | None = None
    expiration_date: date
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: str | None = None
    correlation_id: str | None = None

    @model_validator(mode="after")
    def quantity_must_be_positive(self) -> Position:
        if self.quantity <= 0:
            raise ValueError("Las posiciones largas deben tener cantidad positiva")
        return self

    @property
    def market_value(self) -> Decimal | None:
        if self.current_price is None:
            return None
        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> Decimal | None:
        if self.current_price is None:
            return None
        return (self.current_price - self.average_price) * self.quantity


class OrderRequest(BaseModel):
    symbol: str
    side: str  # BUY / SELL — validated against OrderSide in services
    order_type: str
    quantity: int
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "DAY"
    strategy_id: str | None = None
    correlation_id: str | None = None
    underlying_symbol: str | None = None
    expiration_date: date | None = None
    option_type: OptionType | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    request: OrderRequest
    status: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    filled_quantity: int = 0
    average_fill_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    rejection_code: str | None = None
    rejection_reason: str | None = None
    validation_notes: list[str] = Field(default_factory=list)
    quote_used: MarketQuote | None = None
    fills: list[dict[str, Any]] = Field(default_factory=list)


class Fill(BaseModel):
    order_id: UUID
    quantity: int
    price: Decimal
    commission: Decimal
    slippage: Decimal
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    quote_snapshot: MarketQuote | None = None


class RiskValidationResult(BaseModel):
    approved: bool
    codes: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    suggested_quantity: int | None = None
    estimated_premium: Decimal | None = None
    estimated_commission: Decimal | None = None
    exposure_metrics: dict[str, Any] = Field(default_factory=dict)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def primary_code(self) -> str | None:
        return self.codes[0] if self.codes else None


class DecisionRecord(BaseModel):
    """Registro explicable de una decisión de estrategia."""

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: str
    contract_symbol: str | None = None
    underlying_symbol: str | None = None
    action: str
    indicators: dict[str, Any] = Field(default_factory=dict)
    score: Decimal | None = None
    score_components: dict[str, Any] = Field(default_factory=dict)
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    entry_reason: str | None = None
    discard_reason: str | None = None
    exit_reason: str | None = None
    estimated_risk: Decimal | None = None
    expected_price: Decimal | None = None
    executed_price: Decimal | None = None
    correlation_id: str | None = None

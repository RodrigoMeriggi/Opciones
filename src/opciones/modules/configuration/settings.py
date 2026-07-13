"""Configuración centralizada con defaults seguros (paper + emergency stop)."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from opciones.domain.enums import TradingMode
from opciones.domain.models import RiskLimits


def _default_authorized_underlyings() -> list[str]:
    from opciones.modules.instruments.universe import load_byma_universe

    return load_byma_universe().symbols


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading_mode: TradingMode = TradingMode.PAPER
    live_trading_enabled: bool = False
    emergency_stop: bool = True
    manual_live_confirmation: str = ""

    max_daily_loss: Decimal = Decimal("50000")
    max_position_size: Decimal = Decimal("0.35")
    max_open_positions: int = 20
    min_days_to_expiration: int = 5
    force_exit_days_before_expiration: int = 3

    database_url: str = "postgresql+psycopg://opciones:opciones@localhost:5432/opciones"
    redis_url: str = "redis://localhost:6379/0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    paper_initial_cash: Decimal = Decimal("1000000")
    paper_commission_rate: Decimal = Decimal("0.001")
    paper_slippage_bps: Decimal = Decimal("5")
    paper_latency_ms: int = 50

    # Credenciales broker real — no usadas hasta documentación oficial
    broker_api_url: str = ""
    broker_api_key: str = ""
    broker_api_secret: str = ""
    broker_account_id: str = ""

    authorized_underlyings: list[str] = Field(default_factory=_default_authorized_underlyings)
    market_open_hour: int = 11
    market_close_hour: int = 17
    timezone: str = "America/Argentina/Buenos_Aires"
    # Orígenes CORS separados por coma (prod: URL de Vercel)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("trading_mode", mode="before")
    @classmethod
    def parse_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @model_validator(mode="after")
    def enforce_safe_defaults(self) -> Settings:
        # Ningún módulo puede cambiar a live automáticamente vía defaults.
        if self.trading_mode == TradingMode.LIVE and not self.live_trading_enabled:
            object.__setattr__(self, "trading_mode", TradingMode.PAPER)
        return self

    def is_live_trading_allowed(self) -> bool:
        """Requiere TODAS las condiciones simultáneas."""
        return (
            self.trading_mode == TradingMode.LIVE
            and self.live_trading_enabled is True
            and self.emergency_stop is False
            and bool(self.broker_api_key)
            and bool(self.broker_api_secret)
            and self.manual_live_confirmation.strip().upper() == "I_UNDERSTAND_LIVE_TRADING"
        )

    def to_risk_limits(self) -> RiskLimits:
        return RiskLimits(
            initial_capital=self.paper_initial_cash,
            maximum_position_percentage=self.max_position_size,
            maximum_daily_loss=self.max_daily_loss,
            maximum_open_positions=self.max_open_positions,
            minimum_days_to_expiration=self.min_days_to_expiration,
            force_exit_days_before_expiration=self.force_exit_days_before_expiration,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()

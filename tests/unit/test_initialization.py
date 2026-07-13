"""Pruebas de inicialización y seguridad."""

from opciones import __version__
from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.modules.configuration import get_settings
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.ports import Broker, MarketDataProvider, RiskManager, Strategy


def test_package_version():
    assert __version__ == "0.3.0"


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("EMERGENCY_STOP", raising=False)
    from opciones.modules.configuration.settings import Settings, reset_settings_cache

    reset_settings_cache()
    s = Settings(_env_file=None)
    assert s.trading_mode.value == "paper"
    assert s.live_trading_enabled is False
    assert s.emergency_stop is True
    assert s.is_live_trading_allowed() is False


def test_live_requires_all_conditions():
    from opciones.modules.configuration.settings import Settings

    s = Settings(
        trading_mode="live",
        live_trading_enabled=True,
        emergency_stop=False,
        broker_api_key="key",
        broker_api_secret="secret",
        manual_live_confirmation="I_UNDERSTAND_LIVE_TRADING",
        _env_file=None,
    )
    assert s.is_live_trading_allowed() is True

    s2 = Settings(
        trading_mode="live",
        live_trading_enabled=True,
        emergency_stop=False,
        broker_api_key="key",
        broker_api_secret="secret",
        manual_live_confirmation="",
        _env_file=None,
    )
    assert s2.is_live_trading_allowed() is False


def test_interfaces_and_implementations():
    assert issubclass(MockMarketDataProvider, MarketDataProvider)
    assert issubclass(PaperBroker, Broker)
    assert issubclass(DefaultRiskManager, RiskManager)
    assert issubclass(BasicOptionStrategy, Strategy)


def test_fastapi_app_imports():
    from opciones.api.app import app

    assert app.title.startswith("Opciones")

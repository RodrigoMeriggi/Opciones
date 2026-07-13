"""API pública del módulo de backtesting."""

from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.backtesting.data.provider import (
    HistoricalDataProvider,
    generate_historical_dataset,
)
from opciones.modules.backtesting.engine.core import BacktestEngine, StrategyRunner
from opciones.modules.backtesting.execution.broker import HistoricalBroker
from opciones.modules.backtesting.execution.simulator import ExecutionSimulator
from opciones.modules.backtesting.reporting.analyzer import PerformanceAnalyzer, PortfolioTracker
from opciones.modules.backtesting.reporting.generator import BacktestReportGenerator
from opciones.modules.backtesting.types import BacktestConfig, BacktestResult, BarFrequency

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "BarFrequency",
    "HistoricalMarketClock",
    "HistoricalDataProvider",
    "HistoricalBroker",
    "StrategyRunner",
    "ExecutionSimulator",
    "PortfolioTracker",
    "PerformanceAnalyzer",
    "BacktestReportGenerator",
    "generate_historical_dataset",
]

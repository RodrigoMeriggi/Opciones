"""StrategyRunner y BacktestEngine — la estrategia no sabe que está en backtest."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from opciones.domain.enums import OrderSide, SignalAction
from opciones.domain.models import DecisionRecord, OrderRequest, RiskLimits
from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.backtesting.data.provider import HistoricalDataProvider
from opciones.modules.backtesting.execution.broker import HistoricalBroker
from opciones.modules.backtesting.execution.simulator import ExecutionSimulator
from opciones.modules.backtesting.reporting.analyzer import PerformanceAnalyzer, PortfolioTracker
from opciones.modules.backtesting.types import BacktestConfig, BacktestResult, MarketEventType
from opciones.modules.configuration.settings import Settings
from opciones.modules.paper_broker.expiration import ExpirationCloser, ExpirationCloserConfig
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.ports import RiskManager, Strategy


class StrategyRunner:
    """Ejecuta Strategy + RiskManager igual que paper/live."""

    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        broker: HistoricalBroker,
        market_data: HistoricalDataProvider,
        force_exit_days: int = 3,
    ) -> None:
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.broker = broker
        self.market_data = market_data
        self.closer = ExpirationCloser(
            broker,  # compatible API submit_order/get_positions/add_alert
            market_data,
            ExpirationCloserConfig(force_exit_days=force_exit_days),
        )
        # ExpirationCloser espera PaperBroker.add_alert — adaptar
        if not hasattr(broker, "add_alert"):
            broker.add_alert = lambda msg: None  # type: ignore[method-assign]
        self.decisions: list[DecisionRecord] = []

    async def step(self, underlying: str) -> list[DecisionRecord]:
        out: list[DecisionRecord] = []
        # Cierres obligatorios
        await self.closer.close_near_expiration(today=self.market_data.clock.today)

        u = await self.market_data.get_underlying(underlying)
        if u is None:
            return out
        chain = await self.market_data.get_option_chain(underlying)
        end = self.market_data.clock.now
        start = end.replace(year=max(2000, end.year - 1)) if False else datetime(
            end.year, 1, 1
        )
        # Solo historia hasta ahora
        historical = await self.market_data.get_historical_prices(
            underlying, end.replace(day=1) if end.day > 1 else end, end
        )
        # Pedir más historia disponible
        historical = self.market_data.available_history(underlying)[-90:]

        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        quotes = {}
        for p in positions:
            q = await self.market_data.get_quote(p.symbol)
            if q:
                quotes[p.symbol] = q

        for dec in await self.strategy.evaluate_exits(
            positions, quotes, u, historical, portfolio
        ):
            self.decisions.append(dec)
            out.append(dec)
            if dec.action == SignalAction.SELL:
                await self._exec(dec)

        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        for dec in await self.strategy.evaluate(chain, u, historical, portfolio, positions):
            self.decisions.append(dec)
            out.append(dec)
            if dec.action == SignalAction.BUY:
                await self._exec(dec)
        return out

    async def _exec(self, decision: DecisionRecord) -> None:
        side = str(decision.indicators.get("order_side", OrderSide.BUY))
        qty = int(decision.indicators.get("suggested_quantity") or 1)
        symbol = decision.contract_symbol
        if not symbol:
            return
        positions = await self.broker.get_positions()
        und = decision.underlying_symbol
        exp = None
        opt = None
        for p in positions:
            if p.symbol == symbol:
                exp, opt, und = p.expiration_date, p.option_type, p.underlying_symbol
        if side in {OrderSide.BUY, "BUY"} and und:
            chain = await self.market_data.get_option_chain(und)
            for c in chain.contracts:
                if c.symbol == symbol:
                    exp, opt = c.expiration_date, c.option_type
                    # Registrar quotes en provider para ejecución
                    self.market_data.load_quote(c.to_quote())
                    # Fix timestamp to clock
                    q = c.to_quote()
                    q.timestamp = self.market_data.clock.now
                    self.market_data.load_quote(q)
                    break

        req = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=str(decision.indicators.get("order_type", "MARKET")),
            quantity=qty,
            underlying_symbol=und,
            expiration_date=exp,
            option_type=opt,
            strategy_id=decision.strategy_id,
            correlation_id=decision.correlation_id or str(uuid4()),
            reason=decision.entry_reason or decision.exit_reason,
        )
        quote = await self.market_data.get_quote(symbol)
        portfolio = await self.broker.get_portfolio()
        positions = await self.broker.get_positions()
        contract = None
        if und:
            chain = await self.market_data.get_option_chain(und)
            contract = next((c for c in chain.contracts if c.symbol == symbol), None)
        risk = await self.risk_manager.validate_order(
            req, quote, portfolio, positions, contract=contract
        )
        if not risk.approved:
            decision.action = SignalAction.DISCARD
            decision.discard_reason = "; ".join(risk.messages)
            return
        if risk.suggested_quantity and side in {OrderSide.BUY, "BUY"}:
            req.quantity = max(1, risk.suggested_quantity)
        order = await self.broker.submit_order(req)
        if order.average_fill_price:
            decision.executed_price = order.average_fill_price


class BacktestEngine:
    def __init__(
        self,
        config: BacktestConfig,
        strategy: Strategy,
        risk_manager: RiskManager | None = None,
        data_provider: HistoricalDataProvider | None = None,
        clock: HistoricalMarketClock | None = None,
    ) -> None:
        self.config = config
        start_dt = datetime.combine(config.start_date, datetime.min.time()).replace(
            hour=config.market_close_hour
        )
        end_dt = datetime.combine(config.end_date, datetime.min.time()).replace(
            hour=config.market_close_hour
        )
        self.clock = clock or HistoricalMarketClock(
            start_dt,
            end_dt,
            config.frequency,
            holidays=config.holidays,
            market_open_hour=config.market_open_hour,
            market_close_hour=config.market_close_hour,
        )
        self.data = data_provider or HistoricalDataProvider(self.clock)
        if data_provider is None:
            # rebind clock if provider created with different clock — already same
            pass
        else:
            self.data.clock = self.clock

        sim = ExecutionSimulator(
            commission_rate=config.commission_rate,
            slippage_bps=config.slippage_bps,
            allow_partial=config.allow_partial,
        )
        self.broker = HistoricalBroker(self.data, config.initial_capital, sim)
        settings = Settings(
            emergency_stop=False,
            trading_mode="paper",
            live_trading_enabled=False,
            _env_file=None,
        )
        limits = RiskLimits(
            initial_capital=config.initial_capital,
            maximum_daily_loss=config.max_daily_loss,
            minimum_volume=config.min_volume,
            maximum_bid_ask_spread_percentage=config.max_spread_pct,
            force_exit_days_before_expiration=config.force_exit_days_before_expiration,
            cooldown_after_loss_minutes=0,
            minimum_cash_reserve=Decimal("10000"),
            maximum_position_percentage=Decimal("0.15"),
            maximum_capital_at_risk=config.initial_capital,
            maximum_total_premium=config.initial_capital,
            daily_trade_limit=50,
            maximum_open_positions=10,
        )
        self.risk = risk_manager or DefaultRiskManager(
            limits=limits,
            settings=settings,
            authorized_underlyings=config.universe,
            ignore_market_hours=True,
        )
        if self.risk.is_buying_blocked():
            self.risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
        self.strategy = strategy
        self.runner = StrategyRunner(
            strategy,
            self.risk,
            self.broker,
            self.data,
            force_exit_days=config.force_exit_days_before_expiration,
        )
        self.tracker = PortfolioTracker()
        self.events: list[dict[str, Any]] = []

    async def run(self) -> BacktestResult:
        self.clock.reset()
        last_day = None
        while True:
            ts = self.clock.advance()
            if ts is None:
                break

            if self.clock.is_holiday():
                self.events.append(
                    {"type": MarketEventType.HOLIDAY, "ts": ts.isoformat()}
                )
                continue

            if last_day != ts.date():
                if last_day is not None:
                    self.events.append(
                        {"type": MarketEventType.MARKET_CLOSE, "ts": str(last_day)}
                    )
                self.events.append(
                    {"type": MarketEventType.MARKET_OPEN, "ts": ts.isoformat()}
                )
                self.broker.reset_daily_counters()
                last_day = ts.date()

            # Sync option quotes for current chain snapshot into quote book
            for und in self.config.universe:
                chain = await self.data.get_option_chain(und)
                for c in chain.contracts:
                    q = c.to_quote()
                    q.timestamp = ts
                    # Only load if not looking ahead — chain already asof
                    self.data.load_quote(q)

            await self.broker.process_pending()
            portfolio = await self.broker.get_portfolio()
            positions = await self.broker.get_positions()

            for und in self.config.universe:
                await self.runner.step(und)

            portfolio = await self.broker.get_portfolio()
            exposure = portfolio.total_premium
            self.tracker.record(
                ts,
                portfolio.equity,
                portfolio.cash,
                exposure,
                portfolio.peak_equity,
                portfolio.realized_pnl,
                portfolio.unrealized_pnl,
            )

        # Cierre final de posiciones abiertas al bid (fin de backtest)
        for p in list(await self.broker.get_positions()):
            await self.broker.submit_order(
                OrderRequest(
                    symbol=p.symbol,
                    side=OrderSide.SELL,
                    order_type="MARKET",
                    quantity=p.quantity,
                    underlying_symbol=p.underlying_symbol,
                    expiration_date=p.expiration_date,
                    option_type=p.option_type,
                    reason="BACKTEST_END",
                )
            )

        analyzer = PerformanceAnalyzer()
        metrics, extra = analyzer.analyze(
            self.tracker.equity_curve,
            self.broker.trades,
            self.config.initial_capital,
            self.broker.rejected_count,
            self.broker.partial_count,
            self.broker.total_commission,
            self.broker.total_slippage,
        )
        return BacktestResult(
            config=self.config,
            metrics=metrics,
            equity_curve=self.tracker.equity_curve,
            trades=self.broker.trades,
            decisions=[d.model_dump(mode="json") for d in self.runner.decisions],
            events=self.events + self.data.events,
            series=extra.get("series", {}),
            breakdowns=extra.get("breakdowns", {}),
        )

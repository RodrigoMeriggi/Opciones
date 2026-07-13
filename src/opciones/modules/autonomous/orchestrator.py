"""Servicio autónomo de paper trading en tiempo real (simulable)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from opciones.adapters.market_data.mock_provider import MockMarketDataProvider
from opciones.adapters.notifications.logging_provider import LoggingNotificationProvider
from opciones.domain.models import RiskLimits
from opciones.modules.configuration.settings import Settings, get_settings
from opciones.modules.paper_broker.broker import PaperBroker
from opciones.modules.paper_broker.expiration import ExpirationCloser
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.modules.strategy_engine.executor import StrategyExecutor
from opciones.ports import NotificationProvider

logger = logging.getLogger(__name__)


class OperationalState(StrEnum):
    STARTING = "STARTING"
    WAITING_FOR_MARKET = "WAITING_FOR_MARKET"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    RISK_BLOCKED = "RISK_BLOCKED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"
    CLOSING = "CLOSING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class ApplicationState(BaseModel):
    state: OperationalState = OperationalState.STARTING
    trading_mode: str = "paper"
    emergency_stop: bool = False
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    last_cycle_at: datetime | None = None
    cycle_count: int = 0
    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lock_holder: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    alerts: list[str] = Field(default_factory=list)
    idempotency_keys: list[str] = Field(default_factory=list)


class DistributedLock:
    """Lock en memoria (Redis en producción). Evita procesos duplicados."""

    def __init__(self) -> None:
        self._holder: str | None = None

    def acquire(self, owner: str) -> bool:
        if self._holder is None or self._holder == owner:
            self._holder = owner
            return True
        return False

    def release(self, owner: str) -> None:
        if self._holder == owner:
            self._holder = None


class MarketSessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tz = ZoneInfo(settings.timezone)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def is_open(self) -> bool:
        n = self.now()
        if n.weekday() >= 5:
            return False
        return time(self.settings.market_open_hour, 0) <= n.time() <= time(
            self.settings.market_close_hour, 0
        )

    def near_close(self, minutes: int = 15) -> bool:
        n = self.now()
        close = time(self.settings.market_close_hour, 0)
        close_dt = n.replace(hour=close.hour, minute=0, second=0, microsecond=0)
        return 0 <= (close_dt - n).total_seconds() <= minutes * 60


class HealthMonitor:
    def __init__(self) -> None:
        self.api_errors = 0
        self.last_ok = datetime.utcnow()

    def record_success(self) -> None:
        self.api_errors = 0
        self.last_ok = datetime.utcnow()

    def record_error(self) -> None:
        self.api_errors += 1

    def is_degraded(self) -> bool:
        return self.api_errors >= 3


class ReconciliationService:
    def __init__(self, broker: PaperBroker) -> None:
        self.broker = broker
        self.last_report: dict[str, Any] = {}

    async def reconcile(
        self,
        local_cash: Decimal,
        local_positions: dict[str, int],
        *,
        adopt_broker: bool = True,
    ) -> dict[str, Any]:
        broker_cash = await self.broker.get_cash()
        positions = await self.broker.get_positions()
        broker_pos = {p.symbol: p.quantity for p in positions}
        diffs = []
        if broker_cash != local_cash:
            diffs.append({"field": "cash", "local": str(local_cash), "broker": str(broker_cash)})
        for sym in set(local_positions) | set(broker_pos):
            if local_positions.get(sym, 0) != broker_pos.get(sym, 0):
                diffs.append(
                    {
                        "field": "position",
                        "symbol": sym,
                        "local": local_positions.get(sym, 0),
                        "broker": broker_pos.get(sym, 0),
                    }
                )
        adopted = False
        if diffs and adopt_broker:
            # Paper: broker es fuente de verdad; auto-sanar en lugar de cortar compras
            adopted = True
            diffs = []
        report = {
            "ok": len(diffs) == 0,
            "diffs": diffs,
            "adopted_broker": adopted,
            "broker_cash": str(broker_cash),
            "broker_positions": broker_pos,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.last_report = report
        return report


class EmergencyStopService:
    def __init__(
        self,
        risk: DefaultRiskManager,
        notifications: NotificationProvider,
        app_state: ApplicationStateManager | None = None,
    ) -> None:
        self.risk = risk
        self.notifications = notifications
        self.app_state = app_state
        self.active = risk.is_buying_blocked()

    async def activate(self, reason: str) -> None:
        self.active = True
        self.risk.activate_circuit_breaker("EMERGENCY_STOP", reason)
        if self.app_state:
            self.app_state.state.emergency_stop = True
            self.app_state.set_state(OperationalState.EMERGENCY_STOPPED)
        await self.notifications.send("EMERGENCY_STOP", reason, "critical")

    async def deactivate(self, confirmation: str) -> None:
        if confirmation != "MANUAL_UNLOCK_CONFIRMED":
            raise PermissionError("Confirmación inválida")
        self.risk.reset_circuit_breaker(confirmation)
        self.active = False
        if self.app_state:
            self.app_state.state.emergency_stop = False
            self.app_state.set_state(OperationalState.WAITING_FOR_MARKET)
        await self.notifications.send("EMERGENCY_STOP_OFF", "Desactivado manualmente", "warning")


class ApplicationStateManager:
    def __init__(self) -> None:
        self.state = ApplicationState()
        self.events: list[dict[str, Any]] = []

    def set_state(self, state: OperationalState) -> None:
        self.state.state = state
        self.state.last_heartbeat = datetime.utcnow()
        self.events.append({"state": state.value, "ts": datetime.utcnow().isoformat()})

    def heartbeat(self) -> None:
        self.state.last_heartbeat = datetime.utcnow()

    def persist(self) -> dict[str, Any]:
        return self.state.model_dump(mode="json")

    def restore(self, payload: dict[str, Any]) -> None:
        self.state = ApplicationState.model_validate(payload)


class TradingOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        notifications: NotificationProvider | None = None,
        simulate_market_open: bool = True,
        cycle_sleep_s: float = 1.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.notifications = notifications or LoggingNotificationProvider()
        self.session = MarketSessionManager(self.settings)
        self.health = HealthMonitor()
        self.lock = DistributedLock()
        self.app_state = ApplicationStateManager()
        self.simulate_market_open = simulate_market_open
        self.cycle_sleep_s = cycle_sleep_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._pause = asyncio.Event()
        self._pause.set()  # not paused
        self.block_new_entries = False

        # Wiring paper stack
        self.market_data = MockMarketDataProvider(scenario="sideways", liquidity="high")
        self.broker = PaperBroker(
            self.market_data,
            initial_cash=self.settings.paper_initial_cash,
            commission_rate=self.settings.paper_commission_rate,
            slippage_bps=self.settings.paper_slippage_bps,
            latency_ms=0,
        )
        limits = self.settings.to_risk_limits()
        limits.cooldown_after_loss_minutes = 0
        limits.minimum_volume = 1
        self.risk = DefaultRiskManager(
            limits=limits,
            settings=self.settings,
            ignore_market_hours=simulate_market_open,
        )
        self.emergency = EmergencyStopService(self.risk, self.notifications, self.app_state)
        self.strategy = BasicOptionStrategy(
            self.risk,
            config={
                "signal_confirm_cycles": 1,
                "min_seconds_between_trades": 0,
                "min_volume": 1,
                "max_spread_pct": 20,
                "rsi_min": 0,
                "rsi_max": 100,
                "min_momentum_pct": 0.05,
                "authorized_underlyings": list(self.settings.authorized_underlyings),
            },
        )
        self.executor = StrategyExecutor(self.strategy, self.risk, self.broker, self.market_data)
        self.reconciliation = ReconciliationService(self.broker)
        self._local_cash = self.settings.paper_initial_cash
        self._local_positions: dict[str, int] = {}
        self._processed_order_ids: set[str] = set()
        self._universe_idx = 0

    async def startup(self) -> None:
        self.app_state.set_state(OperationalState.STARTING)
        await self.notifications.send("START", "Orquestador iniciando", "info")
        if self.settings.trading_mode.value != "paper" or self.settings.live_trading_enabled:
            # Forzar paper
            self.app_state.set_state(OperationalState.ERROR)
            raise RuntimeError("Servicio autónomo solo opera en paper en esta etapa")
        if not self.lock.acquire(self.app_state.state.instance_id):
            raise RuntimeError("Otra instancia sostiene el lock")
        self.app_state.state.lock_holder = self.app_state.state.instance_id
        # Verificar modo paper, cargar estado
        self.app_state.state.emergency_stop = bool(self.settings.emergency_stop)
        self.emergency.active = bool(self.settings.emergency_stop)
        if self.settings.emergency_stop:
            self.app_state.set_state(OperationalState.EMERGENCY_STOPPED)
        else:
            # Asegurar compras habilitadas en paper si emergency está off
            if self.risk.is_buying_blocked():
                self.risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
            self.emergency.active = False
            self.app_state.state.emergency_stop = False
            self.app_state.set_state(OperationalState.WAITING_FOR_MARKET)
        report = await self.reconciliation.reconcile(self._local_cash, self._local_positions)
        if report.get("adopted_broker"):
            self._local_cash = Decimal(str(report["broker_cash"]))
            self._local_positions = dict(report.get("broker_positions") or {})
        if not report["ok"]:
            self.app_state.set_state(OperationalState.DEGRADED)
            await self.notifications.send("RECONCILE_FAIL", str(report), "error")

    async def start(self) -> None:
        await self.startup()
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        self._pause.set()
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            self._task = None
        try:
            self.lock.release(self.app_state.state.instance_id)
        except Exception:
            pass
        self.app_state.set_state(OperationalState.STOPPED)
        await self.notifications.send("STOP", "Orquestador detenido", "info")

    async def pause(self) -> None:
        self._pause.clear()
        self.app_state.set_state(OperationalState.PAUSED)

    async def resume(self) -> None:
        if self.app_state.state.state == OperationalState.EMERGENCY_STOPPED:
            return
        self._pause.set()
        self.app_state.set_state(OperationalState.RUNNING)

    async def _run_loop(self) -> None:
        backoff = 0.05
        while not self._stop.is_set():
            await self._pause.wait()
            try:
                # Paper: si emergency está off en settings, no mantener bloqueos residuales
                if not self.settings.emergency_stop and not self.emergency.active:
                    self.app_state.state.emergency_stop = False
                    if self.risk.is_buying_blocked():
                        self.risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")

                open_ok = self.simulate_market_open or self.session.is_open()
                if not open_ok:
                    self.app_state.set_state(OperationalState.WAITING_FOR_MARKET)
                    await asyncio.sleep(self.cycle_sleep_s)
                    continue

                if self.emergency.active or self.settings.emergency_stop:
                    self.app_state.state.emergency_stop = True
                    self.app_state.set_state(OperationalState.EMERGENCY_STOPPED)
                elif self.risk.is_buying_blocked():
                    self.app_state.state.emergency_stop = False
                    self.app_state.set_state(OperationalState.RISK_BLOCKED)
                elif self.health.is_degraded():
                    self.app_state.state.emergency_stop = False
                    self.app_state.set_state(OperationalState.DEGRADED)
                else:
                    self.app_state.state.emergency_stop = False
                    self.app_state.set_state(OperationalState.RUNNING)

                if self.session.near_close() and not self.simulate_market_open:
                    self.block_new_entries = True
                    await self._close_session()
                    continue

                await self._cycle()
                self.health.record_success()
                backoff = 0.05
            except Exception as exc:
                self.health.record_error()
                self.app_state.set_state(OperationalState.ERROR)
                await self.notifications.send("ERROR", str(exc), "error")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
            await asyncio.sleep(self.cycle_sleep_s)

    async def _cycle(self) -> None:
        self.app_state.heartbeat()
        if self.emergency.active or self.settings.emergency_stop:
            self.app_state.state.emergency_stop = True
            self.app_state.set_state(OperationalState.EMERGENCY_STOPPED)
        elif self.risk.is_buying_blocked():
            self.app_state.state.emergency_stop = False
            self.app_state.set_state(OperationalState.RISK_BLOCKED)
        elif self.health.is_degraded():
            self.app_state.state.emergency_stop = False
            self.app_state.set_state(OperationalState.DEGRADED)
        else:
            self.app_state.state.emergency_stop = False
            self.app_state.set_state(OperationalState.RUNNING)

        # Idempotencia: clave por ciclo
        key = f"cycle-{self.app_state.state.cycle_count}"
        if key in self.app_state.state.idempotency_keys:
            return
        report = await self.reconciliation.reconcile(self._local_cash, self._local_positions)
        if report.get("adopted_broker"):
            self._local_cash = Decimal(str(report["broker_cash"]))
            self._local_positions = dict(report.get("broker_positions") or {})
        if not report["ok"]:
            self.app_state.set_state(OperationalState.DEGRADED)
            await self.notifications.send("PORTFOLIO_MISMATCH", str(report["diffs"]), "critical")
            # No activar CB por mismatch en paper si se puede reintentar; solo alertar
            return

        if self.block_new_entries or self.emergency.active:
            # Solo exits / expiration
            await self.broker.process_pending()
            await self.executor.expiration_closer.close_near_expiration()
        else:
            await self.broker.process_pending()
            universe = list(self.settings.authorized_underlyings) or ["GGAL"]
            # Un subyacente por ciclo para no saturar BYMADATA; rota el universo completo
            und = universe[self._universe_idx % len(universe)]
            self._universe_idx += 1
            await self.executor.run_cycle(und)
            # Sync local mirrors from broker (source of truth after success)
            self._local_cash = await self.broker.get_cash()
            self._local_positions = {
                p.symbol: p.quantity for p in await self.broker.get_positions()
            }
            for order in self.executor.orders:
                oid = str(order.id)
                if oid in self._processed_order_ids:
                    continue
                self._processed_order_ids.add(oid)
                await self.notifications.send(
                    "ORDER",
                    f"{order.status} {order.request.symbol}",
                    "info",
                )

        self.app_state.state.idempotency_keys.append(key)
        self.app_state.state.idempotency_keys = self.app_state.state.idempotency_keys[-500:]
        self.app_state.state.cycle_count += 1
        self.app_state.state.last_cycle_at = datetime.utcnow()
        pf = await self.broker.get_portfolio()
        self.app_state.state.metrics = {
            "equity": str(pf.equity),
            "cash": str(pf.cash),
            "positions": pf.open_positions,
            "daily_pnl": str(pf.daily_pnl),
            "unrealized_pnl": str(pf.unrealized_pnl),
            "realized_pnl": str(pf.realized_pnl),
            "total_pnl": str(pf.realized_pnl + pf.unrealized_pnl),
        }

    async def _close_session(self) -> None:
        self.app_state.set_state(OperationalState.CLOSING)
        # Cancel pending
        # Paper broker pending cancel
        for oid in list(self.broker._pending):
            await self.broker.cancel_order(oid)
        await self.executor.expiration_closer.close_near_expiration()
        await self.notifications.send("DAILY_CLOSE", "Sesión cerrada", "info")
        self.app_state.set_state(OperationalState.STOPPED)
        self._stop.set()

    async def close_all_positions(self) -> list[Any]:
        from opciones.domain.enums import OrderSide, OrderType
        from opciones.domain.models import OrderRequest

        results = []
        for p in await self.broker.get_positions():
            order = await self.broker.submit_order(
                OrderRequest(
                    symbol=p.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=p.quantity,
                    underlying_symbol=p.underlying_symbol,
                    expiration_date=p.expiration_date,
                    option_type=p.option_type,
                    reason="MANUAL_CLOSE_ALL",
                )
            )
            results.append(order)
        self._local_positions = {}
        self._local_cash = await self.broker.get_cash()
        return results

    async def close_position(self, symbol: str, quantity: int | None = None) -> Any:
        """Cierra (vende) una posición paper a mercado contra bid BYMADATA."""
        from opciones.domain.enums import OrderSide, OrderType
        from opciones.domain.models import OrderRequest

        sym = symbol.upper()
        positions = {p.symbol: p for p in await self.broker.get_positions()}
        pos = positions.get(sym)
        if pos is None:
            raise KeyError(f"Sin posición abierta en {sym}")
        qty = int(quantity) if quantity is not None else pos.quantity
        if qty <= 0 or qty > pos.quantity:
            raise ValueError(f"Cantidad inválida para cerrar {sym}: {qty}")
        order = await self.broker.submit_order(
            OrderRequest(
                symbol=pos.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=qty,
                underlying_symbol=pos.underlying_symbol,
                expiration_date=pos.expiration_date,
                option_type=pos.option_type,
                reason="MANUAL_CLOSE",
            )
        )
        self._local_positions = {
            p.symbol: p.quantity for p in await self.broker.get_positions()
        }
        self._local_cash = await self.broker.get_cash()
        return order

    def status(self) -> dict[str, Any]:
        return {
            **self.app_state.persist(),
            "paper_mode_visible": True,
            "trading_mode": "paper",
            "universe": list(self.settings.authorized_underlyings),
            "universe_size": len(self.settings.authorized_underlyings),
            "emergency_stop": bool(
                self.emergency.active or self.settings.emergency_stop or self.app_state.state.emergency_stop
            ),
            "buying_blocked": self.risk.is_buying_blocked(),
            "circuit_breaker_reason": getattr(self.risk, "_circuit_breaker_reason", None),
            "reconciliation": self.reconciliation.last_report,
            "health_errors": self.health.api_errors,
        }


# Singleton de proceso para API
_orchestrator: TradingOrchestrator | None = None


def get_orchestrator() -> TradingOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        # Paper API: nunca arrancar con emergency on (el default de Settings es true)
        settings = get_settings()
        object.__setattr__(settings, "emergency_stop", False)
        _orchestrator = TradingOrchestrator(settings=settings, simulate_market_open=True)
    return _orchestrator


def reset_orchestrator() -> None:
    global _orchestrator
    _orchestrator = None

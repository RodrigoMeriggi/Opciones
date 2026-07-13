"""Rutas de control del orquestador, ingesta, backtest y SSE."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from opciones.api.deps.auth import (
    TokenPayload,
    authenticate,
    create_token,
    current_user,
    require_roles,
)
from opciones.modules.autonomous.orchestrator import (
    OperationalState,
    get_orchestrator,
    reset_orchestrator,
)
from opciones.modules.backtesting import (
    BacktestConfig,
    BacktestEngine,
    BacktestReportGenerator,
    BarFrequency,
    generate_historical_dataset,
)
from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.backtesting.data.provider import HistoricalDataProvider
from opciones.modules.configuration.settings import Settings, get_settings
from opciones.modules.data_ingestion.pipeline.core import IngestionPipeline
from opciones.modules.data_ingestion.readers.formats import read_file
from opciones.modules.data_ingestion.store import HistoricalStore
from opciones.modules.risk_manager.default import DefaultRiskManager
from opciones.modules.strategy_engine.basic import BasicOptionStrategy
from opciones.domain.models import RiskLimits

router = APIRouter()

# Estado compartido de proceso (paper)
_store = HistoricalStore()
_imports: dict[str, Any] = {}
_audit: list[dict[str, Any]] = []
_config_overrides: dict[str, Any] = {}
_sse_subscribers: list[asyncio.Queue] = []


class LoginRequest(BaseModel):
    username: str
    password: str


class ConfirmAction(BaseModel):
    confirmation: str
    second_confirmation: str | None = None


class ClosePositionRequest(BaseModel):
    symbol: str
    quantity: int | None = None


class ConfigUpdate(BaseModel):
    key: str
    value: Any
    confirmation: str


@router.post("/auth/login")
async def login(body: LoginRequest) -> dict:
    user = authenticate(body.username, body.password)
    token = create_token(user.sub, user.role)  # type: ignore[arg-type]
    return {"access_token": token, "token_type": "bearer", "role": user.role, "username": user.sub}


@router.get("/auth/me")
async def me(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    return {"username": user.sub, "role": user.role, "exp": user.exp}


# ---- Orchestrator control ----
@router.get("/bot/status")
async def bot_status(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    orch = get_orchestrator()
    st = orch.status()
    pf = await orch.broker.get_portfolio()
    positions = await orch.broker.get_positions()
    from opciones.modules.portfolio.position_view import enrich_position

    enriched = []
    for p in positions:
        und = await orch.market_data.get_underlying(p.underlying_symbol)
        quote = await orch.market_data.get_quote(p.symbol)
        enriched.append(enrich_position(p, underlying=und, quote=quote))
    return {
        **st,
        "mode_banner": "PAPER",
        "live_trading_enabled": False,
        "portfolio": pf.model_dump(mode="json"),
        "positions": enriched,
        "pending_orders": len(orch.broker._pending),
        "alerts": orch.app_state.state.alerts[-20:],
    }


@router.post("/bot/start")
async def bot_start(user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))]) -> dict:
    orch = get_orchestrator()
    if orch.app_state.state.state in {OperationalState.RUNNING, OperationalState.WAITING_FOR_MARKET}:
        return {"ok": True, "state": orch.app_state.state.state}
    await orch.start()
    await _broadcast({"type": "bot_started"})
    return {"ok": True, "state": orch.app_state.state.state}


@router.post("/bot/pause")
async def bot_pause(user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))]) -> dict:
    await get_orchestrator().pause()
    return {"ok": True}


@router.post("/bot/resume")
async def bot_resume(user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))]) -> dict:
    await get_orchestrator().resume()
    return {"ok": True}


@router.post("/bot/stop")
async def bot_stop(user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))]) -> dict:
    await get_orchestrator().stop()
    reset_orchestrator()
    return {"ok": True}


@router.post("/bot/emergency-stop")
async def emergency_on(
    body: ConfirmAction,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))],
) -> dict:
    if body.confirmation != "EMERGENCY_STOP":
        raise HTTPException(400, "Confirmación requerida: EMERGENCY_STOP")
    await get_orchestrator().emergency.activate(f"by {user.sub}")
    _audit.append({"action": "emergency_on", "user": user.sub, "ts": datetime.utcnow().isoformat()})
    return {"ok": True}


@router.post("/bot/emergency-stop/off")
async def emergency_off(
    body: ConfirmAction,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    if body.confirmation != "MANUAL_UNLOCK_CONFIRMED" or body.second_confirmation != "I_CONFIRM":
        raise HTTPException(400, "Doble confirmación requerida")
    await get_orchestrator().emergency.deactivate("MANUAL_UNLOCK_CONFIRMED")
    _audit.append({"action": "emergency_off", "user": user.sub, "ts": datetime.utcnow().isoformat()})
    return {"ok": True}


@router.post("/bot/close-all")
async def close_all(
    body: ConfirmAction,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))],
) -> dict:
    if body.confirmation != "CLOSE_ALL" or body.second_confirmation != "I_CONFIRM":
        raise HTTPException(400, "Doble confirmación requerida")
    orders = await get_orchestrator().close_all_positions()
    return {"ok": True, "closed": len(orders)}


@router.post("/bot/close")
async def close_position(
    body: ClosePositionRequest,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))],
) -> dict:
    """Venta paper a mercado (bid BYMADATA). No envía orden real."""
    orch = get_orchestrator()
    try:
        order = await orch.close_position(body.symbol, body.quantity)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "order_id": str(order.id),
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "symbol": order.request.symbol,
        "filled_quantity": order.filled_quantity,
        "average_fill_price": str(order.average_fill_price) if order.average_fill_price else None,
        "rejection_reason": order.rejection_reason,
    }


@router.post("/bot/reconcile")
async def reconcile(user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))]) -> dict:
    orch = get_orchestrator()
    return await orch.reconciliation.reconcile(orch._local_cash, orch._local_positions)


# ---- Ingestion ----
@router.post("/data/upload")
async def upload_data(
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))],
    file: UploadFile = File(...),
    kind: str = "underlying",
    allow_duplicate: bool = False,
) -> dict:
    raw = await file.read()
    tmp = Path("/tmp") / (file.filename or "upload.csv")
    tmp.write_bytes(raw)
    try:
        records = read_file(tmp)
    except Exception:
        # try decode as csv/json from bytes
        text = raw.decode("utf-8")
        if (file.filename or "").endswith(".json"):
            import json as _json

            records = _json.loads(text)
            if isinstance(records, dict):
                records = records.get("records", [])
        else:
            import csv
            import io

            records = list(csv.DictReader(io.StringIO(text)))
    pipeline = IngestionPipeline(kind=kind, known_symbols=set(get_settings().authorized_underlyings))
    result = pipeline.run(
        records,
        source="upload",
        filename=file.filename or "unknown",
        raw_bytes=raw,
        initiated_by=user.sub,
        allow_duplicate_import=allow_duplicate,
    )
    persisted = _store.persist(result, kind=kind)
    result.persisted = persisted
    _imports[str(result.version.id)] = result.model_dump(mode="json")
    return {
        "import_id": str(result.version.id),
        "persisted": persisted,
        "quality": result.quality.model_dump(mode="json"),
        "errors": [
            {"reason": r.reason, "original": r.original}
            for r in result.records
            if r.classification.value == "REJECTED"
        ][:50],
    }


@router.get("/data/imports/{import_id}")
async def import_status(import_id: str, user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    if import_id not in _imports:
        raise HTTPException(404)
    return _imports[import_id]


@router.get("/data/coverage/{symbol}")
async def coverage(symbol: str, user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    return _store.coverage(symbol)


@router.get("/data/instruments")
async def instruments(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    return {"instruments": _store.list_instruments()}


@router.get("/data/expirations")
async def expirations(
    user: Annotated[TokenPayload, Depends(current_user)], underlying: str | None = None
) -> dict:
    return {"expirations": _store.list_expirations(underlying)}


@router.get("/data/range/{symbol}")
async def data_range(
    symbol: str,
    start: datetime,
    end: datetime,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict:
    rows = _store.range_query(symbol, start, end)
    return {"count": len(rows), "records": rows[:500]}


# ---- Backtest ----
class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("1000000")
    universe: list[str] = Field(default_factory=lambda: ["GGAL"])
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    commission_rate: Decimal = Decimal("0.001")
    slippage_bps: Decimal = Decimal("5")


@router.post("/backtest/run")
async def run_backtest(
    body: BacktestRequest,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN", "TRADER"))],
) -> dict:
    cfg = BacktestConfig(
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        universe=body.universe,
        strategy_params={
            "signal_confirm_cycles": 1,
            "min_seconds_between_trades": 0,
            "min_volume": 1,
            "max_spread_pct": 20,
            "rsi_min": 0,
            "rsi_max": 100,
            **body.strategy_params,
        },
        commission_rate=body.commission_rate,
        slippage_bps=body.slippage_bps,
        frequency=BarFrequency.D1,
    )
    start_dt = datetime.combine(cfg.start_date, datetime.min.time()).replace(hour=17)
    bars, chains = generate_historical_dataset(
        cfg.universe[0], start=start_dt, days=(cfg.end_date - cfg.start_date).days + 2
    )
    clock = HistoricalMarketClock(
        start_dt,
        datetime.combine(cfg.end_date, datetime.min.time()).replace(hour=17),
        BarFrequency.D1,
    )
    provider = HistoricalDataProvider(clock)
    provider.load_bars(cfg.universe[0], bars)
    provider.load_chain_snapshots(cfg.universe[0], chains)
    settings = Settings(emergency_stop=False, trading_mode="paper", _env_file=None)
    risk = DefaultRiskManager(
        limits=RiskLimits(
            minimum_cash_reserve=Decimal("10000"),
            cooldown_after_loss_minutes=0,
            minimum_volume=1,
            maximum_bid_ask_spread_percentage=Decimal("25"),
        ),
        settings=settings,
        ignore_market_hours=True,
    )
    if risk.is_buying_blocked():
        risk.reset_circuit_breaker("MANUAL_UNLOCK_CONFIRMED")
    strategy = BasicOptionStrategy(risk, config=cfg.strategy_params)
    engine = BacktestEngine(cfg, strategy, risk, provider, clock)
    result = await engine.run()
    out = Path("reports/backtests")
    paths = BacktestReportGenerator(out).write_all(result, name=f"api_{user.sub}")
    return {
        "metrics": result.metrics.model_dump(mode="json"),
        "reports": paths,
        "disclaimer": result.metrics.disclaimer,
    }


# ---- Config audit ----
@router.post("/config/update")
async def config_update(
    body: ConfigUpdate,
    user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))],
) -> dict:
    if body.confirmation != "UPDATE_CONFIG":
        raise HTTPException(400, "Confirmación requerida")
    allowed = {
        "max_daily_loss",
        "stop_loss_pct",
        "take_profit_pct",
        "max_spread_pct",
        "min_volume",
        "authorized_underlyings",
        "paper_initial_cash",
    }
    if body.key not in allowed:
        raise HTTPException(400, "Parámetro no autorizado")
    old = _config_overrides.get(body.key)
    _config_overrides[body.key] = body.value
    _audit.append(
        {
            "user": user.sub,
            "key": body.key,
            "old": old,
            "new": body.value,
            "ts": datetime.utcnow().isoformat(),
        }
    )
    return {"ok": True, "old": old, "new": body.value}


@router.get("/config/audit")
async def config_audit(user: Annotated[TokenPayload, Depends(require_roles("ADMIN"))]) -> dict:
    return {"entries": _audit[-100:]}


@router.get("/signals")
async def signals(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    orch = get_orchestrator()
    return {"decisions": [d.model_dump(mode="json") for d in orch.executor.decisions[-100:]]}


@router.get("/orders")
async def orders(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    orch = get_orchestrator()
    return {
        "orders": [o.model_dump(mode="json") for o in orch.broker._orders.values()],
        "trades": orch.broker.trade_history[-100:],
    }


@router.get("/risk")
async def risk_view(user: Annotated[TokenPayload, Depends(current_user)]) -> dict:
    orch = get_orchestrator()
    pf = await orch.broker.get_portfolio()
    return {
        "limits": orch.risk.get_limits().model_dump(mode="json"),
        "buying_blocked": orch.risk.is_buying_blocked(),
        "exposure": pf.model_dump(mode="json"),
        "audit": orch.risk.audit_log[-50:],
    }


async def _broadcast(event: dict) -> None:
    for q in list(_sse_subscribers):
        await q.put(event)


@router.get("/events/stream")
async def sse_stream(user: Annotated[TokenPayload, Depends(current_user)]) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    _sse_subscribers.append(queue)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'mode': 'PAPER'})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    orch = get_orchestrator()
                    heartbeat = {
                        "type": "heartbeat",
                        "state": orch.app_state.state.state.value,
                        "ts": datetime.utcnow().isoformat(),
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
        finally:
            if queue in _sse_subscribers:
                _sse_subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")

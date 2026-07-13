"""FastAPI application — paper trading platform API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opciones.api.routes.platform import router as platform_router
from opciones.api.routes.ops import router as ops_router
from opciones.api.routes.governance import router as governance_router
from opciones.modules.configuration import get_settings

app = FastAPI(
    title="Opciones BYMA — Paper Trading",
    description=(
        "Plataforma de trading algorítmico autónomo de opciones (modo paper). "
        "Trading real deshabilitado por defecto."
    ),
    version="0.4.0",
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.include_router(platform_router, prefix="/api")
app.include_router(ops_router, prefix="/api")
app.include_router(governance_router, prefix="/api")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "trading_mode": settings.trading_mode.value,
        "live_trading_enabled": settings.live_trading_enabled,
        "emergency_stop": settings.emergency_stop,
        "live_allowed": settings.is_live_trading_allowed(),
        "mode_banner": "PAPER",
    }


@app.get("/config/safety")
async def safety_config() -> dict:
    settings = get_settings()
    return {
        "TRADING_MODE": settings.trading_mode.value,
        "LIVE_TRADING_ENABLED": settings.live_trading_enabled,
        "EMERGENCY_STOP": settings.emergency_stop,
        "MAX_DAILY_LOSS": str(settings.max_daily_loss),
        "MAX_POSITION_SIZE": str(settings.max_position_size),
        "MAX_OPEN_POSITIONS": settings.max_open_positions,
        "MIN_DAYS_TO_EXPIRATION": settings.min_days_to_expiration,
        "FORCE_EXIT_DAYS_BEFORE_EXPIRATION": settings.force_exit_days_before_expiration,
        "note": "Ningún módulo puede habilitar live automáticamente.",
    }

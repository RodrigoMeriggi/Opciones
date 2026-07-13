"""Escenarios de stress testing (Prompt 19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class ScenarioCategory(StrEnum):
    MARKET = "MARKET"
    OPERATIONAL = "OPERATIONAL"
    PORTFOLIO = "PORTFOLIO"


@dataclass
class Scenario:
    id: str
    name: str
    category: ScenarioCategory
    description: str
    critical: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    apply: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _shock_spot(state: dict[str, Any], pct: float) -> dict[str, Any]:
    out = dict(state)
    spot = float(out.get("spot", 100))
    out["spot"] = spot * (1 + pct)
    out["events"] = list(out.get("events", [])) + [f"spot_shock_{pct}"]
    return out


def _vol_shock(state: dict[str, Any], mult: float) -> dict[str, Any]:
    out = dict(state)
    out["iv"] = float(out.get("iv", 0.3)) * mult
    out["events"] = list(out.get("events", [])) + [f"vol_mult_{mult}"]
    return out


def _spread_mult(state: dict[str, Any], mult: float) -> dict[str, Any]:
    out = dict(state)
    out["spread"] = float(out.get("spread", 0.01)) * mult
    out["events"] = list(out.get("events", [])) + [f"spread_mult_{mult}"]
    return out


def catalog() -> list[Scenario]:
    return [
        # Market
        Scenario("mkt_crash", "Caída brusca", ScenarioCategory.MARKET, "spot -15%", True, {"pct": -0.15}, lambda s: _shock_spot(s, -0.15)),
        Scenario("mkt_rally", "Suba brusca", ScenarioCategory.MARKET, "spot +15%", False, {"pct": 0.15}, lambda s: _shock_spot(s, 0.15)),
        Scenario("mkt_gap", "Gap apertura", ScenarioCategory.MARKET, "gap -8%", True, {"pct": -0.08}, lambda s: _shock_spot(s, -0.08)),
        Scenario("mkt_vol_spike", "Vol explosiva", ScenarioCategory.MARKET, "IV x3", True, {"mult": 3.0}, lambda s: _vol_shock(s, 3.0)),
        Scenario("mkt_vol_crush", "Colapso vol", ScenarioCategory.MARKET, "IV x0.3", False, {"mult": 0.3}, lambda s: _vol_shock(s, 0.3)),
        Scenario("mkt_spread_x", "Spread multiplicado", ScenarioCategory.MARKET, "spread x5", True, {"mult": 5.0}, lambda s: _spread_mult(s, 5.0)),
        Scenario("mkt_no_bid", "Sin bid", ScenarioCategory.MARKET, "bid desaparece", True, {}, lambda s: {**s, "bid": None, "events": s.get("events", []) + ["no_bid"]}),
        Scenario("mkt_no_ask", "Sin ask", ScenarioCategory.MARKET, "ask desaparece", True, {}, lambda s: {**s, "ask": None, "events": s.get("events", []) + ["no_ask"]}),
        Scenario("mkt_no_volume", "Volumen nulo", ScenarioCategory.MARKET, "volume~0", False, {}, lambda s: {**s, "volume": 0, "events": s.get("events", []) + ["no_volume"]}),
        Scenario("mkt_halt", "Suspensión", ScenarioCategory.MARKET, "activo suspendido", True, {}, lambda s: {**s, "halted": True, "events": s.get("events", []) + ["halt"]}),
        Scenario("mkt_sideways", "Lateral prolongado", ScenarioCategory.MARKET, "spot flat", False, {}, lambda s: {**s, "regime": "sideways"}),
        Scenario("mkt_trend", "Tendencia prolongada", ScenarioCategory.MARKET, "trend", False, {}, lambda s: {**s, "regime": "trend"}),
        Scenario("mkt_reversal", "Reversión violenta", ScenarioCategory.MARKET, "reversal", True, {}, lambda s: _shock_spot({**s, "regime": "reversal"}, -0.12)),
        Scenario("mkt_near_expiry", "Vencimiento próximo", ScenarioCategory.MARKET, "DTE=1", True, {}, lambda s: {**s, "dte": 1}),
        Scenario("mkt_div_surprise", "Dividendo inesperado", ScenarioCategory.MARKET, "div", False, {}, lambda s: {**s, "unexpected_dividend": 5.0}),
        Scenario("mkt_rate_jump", "Cambio abrupto tasa", ScenarioCategory.MARKET, "rate +500bps", False, {}, lambda s: {**s, "rate": float(s.get("rate", 0.4)) + 0.05}),
        # Operational
        Scenario("ops_disconnect", "Caída conexión", ScenarioCategory.OPERATIONAL, "disconnect", True, {}, lambda s: {**s, "connected": False}),
        Scenario("ops_slow", "Respuestas lentas", ScenarioCategory.OPERATIONAL, "latency", False, {}, lambda s: {**s, "latency_ms": 5000}),
        Scenario("ops_timeout", "Timeout broker", ScenarioCategory.OPERATIONAL, "timeout", True, {}, lambda s: {**s, "broker_timeout": True}),
        Scenario("ops_unconfirmed", "Orden sin confirmación", ScenarioCategory.OPERATIONAL, "uncertain order", True, {}, lambda s: {**s, "uncertain_orders": int(s.get("uncertain_orders", 0)) + 1}),
        Scenario("ops_dup_response", "Doble respuesta", ScenarioCategory.OPERATIONAL, "dup", True, {}, lambda s: {**s, "duplicate_messages": True}),
        Scenario("ops_dup_msg", "Mensajes duplicados", ScenarioCategory.OPERATIONAL, "dup msg", True, {}, lambda s: {**s, "duplicate_messages": True}),
        Scenario("ops_ooo", "Fuera de orden", ScenarioCategory.OPERATIONAL, "ooo", True, {}, lambda s: {**s, "out_of_order": True}),
        Scenario("ops_db_down", "Caída DB", ScenarioCategory.OPERATIONAL, "db", True, {}, lambda s: {**s, "db_up": False}),
        Scenario("ops_redis_down", "Caída Redis", ScenarioCategory.OPERATIONAL, "redis", True, {}, lambda s: {**s, "redis_up": False}),
        Scenario("ops_worker_restart", "Reinicio worker", ScenarioCategory.OPERATIONAL, "restart", True, {}, lambda s: {**s, "worker_restart": True}),
        Scenario("ops_two_workers", "Dos workers", ScenarioCategory.OPERATIONAL, "split brain", True, {}, lambda s: {**s, "duplicate_workers": True}),
        Scenario("ops_token_expired", "Token vencido", ScenarioCategory.OPERATIONAL, "auth", True, {}, lambda s: {**s, "token_valid": False}),
        Scenario("ops_clock_skew", "Error de reloj", ScenarioCategory.OPERATIONAL, "clock", True, {}, lambda s: {**s, "clock_skew_seconds": 120}),
        Scenario("ops_frozen_data", "Datos congelados", ScenarioCategory.OPERATIONAL, "stale", True, {}, lambda s: {**s, "data_frozen": True}),
        Scenario("ops_corrupt", "Datos corruptos", ScenarioCategory.OPERATIONAL, "corrupt", True, {}, lambda s: {**s, "data_corrupt": True}),
        Scenario("ops_recon_bad", "Reconciliación inconsistente", ScenarioCategory.OPERATIONAL, "recon", True, {}, lambda s: {**s, "reconcile_ok": False}),
        # Portfolio
        Scenario("pf_multi_loss", "Pérdidas simultáneas", ScenarioCategory.PORTFOLIO, "multi loss", True, {}, lambda s: {**s, "simultaneous_losses": True, "pnl": float(s.get("pnl", 0)) - abs(float(s.get("capital", 100000)) * 0.08)}),
        Scenario("pf_conc_und", "Concentración subyacente", ScenarioCategory.PORTFOLIO, "conc", False, {}, lambda s: {**s, "concentration_underlying": 0.9}),
        Scenario("pf_conc_exp", "Concentración vencimiento", ScenarioCategory.PORTFOLIO, "conc exp", False, {}, lambda s: {**s, "concentration_expiry": 0.9}),
        Scenario("pf_delta", "Delta excesivo", ScenarioCategory.PORTFOLIO, "delta", True, {}, lambda s: {**s, "portfolio_delta": 5000}),
        Scenario("pf_theta", "Theta excesivo", ScenarioCategory.PORTFOLIO, "theta", False, {}, lambda s: {**s, "portfolio_theta": -2000}),
        Scenario("pf_loss_streak", "Pérdidas consecutivas", ScenarioCategory.PORTFOLIO, "streak", True, {}, lambda s: {**s, "consecutive_losses": 8}),
        Scenario("pf_no_capital", "Capital insuficiente", ScenarioCategory.PORTFOLIO, "capital", True, {}, lambda s: {**s, "available_capital": 0}),
        Scenario("pf_cant_close", "Imposible cerrar", ScenarioCategory.PORTFOLIO, "illiquid exit", True, {}, lambda s: {**s, "can_close": False, "open_positions": int(s.get("open_positions", 1))}),
        Scenario("pf_partial_exit", "Salida parcial", ScenarioCategory.PORTFOLIO, "partial", False, {}, lambda s: {**s, "partial_exit": True}),
        Scenario("pf_high_commission", "Comisión mayor", ScenarioCategory.PORTFOLIO, "fees", False, {}, lambda s: {**s, "commission_mult": 3.0}),
    ]

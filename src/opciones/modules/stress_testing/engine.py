"""ScenarioEngine, Monte Carlo y criterios de aprobación."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opciones.modules.stress_testing.scenarios.catalog import Scenario, catalog


@dataclass
class StressMetrics:
    max_loss: float = 0.0
    drawdown: float = 0.0
    recovery_time_steps: int | None = None
    min_capital: float = 0.0
    unclosed_ops: int = 0
    uncertain_orders: int = 0
    degraded_time_steps: int = 0
    circuit_breaker_activations: int = 0
    limit_violations: int = 0
    slippage_loss: float = 0.0
    liquidity_loss: float = 0.0
    estimated_ruin_risk: float | None = None
    ruin_assumptions: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    scenario_id: str
    name: str
    critical: bool
    passed: bool
    metrics: StressMetrics
    failures: list[str] = field(default_factory=list)
    residual_risks: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class StressReport:
    as_of: datetime
    results: list[ScenarioResult]
    executive_summary: str
    failed_critical: list[str]
    recommended_actions: list[str]
    blocks_live: bool
    disclaimer: str = (
        "Stress testing mide supervivencia y control, no rentabilidad futura. "
        "Monte Carlo no es prueba de ganancias."
    )


@dataclass
class AcceptanceCriteria:
    max_loss_pct: float = 0.20
    max_drawdown: float = 0.25
    zero_duplicate_orders: bool = True
    zero_unknown_positions: bool = True
    safe_recovery_required: bool = True
    allow_close_during_failure: bool = True
    reconcile_must_pass: bool = True
    never_exceed_authorized_capital: bool = True
    never_trade_invalid_data: bool = True


class ScenarioEngine:
    def __init__(self, criteria: AcceptanceCriteria | None = None) -> None:
        self.criteria = criteria or AcceptanceCriteria()
        self.scenarios = {s.id: s for s in catalog()}

    def run_all(self, initial_state: dict[str, Any] | None = None) -> StressReport:
        state0 = {
            "spot": 100.0,
            "iv": 0.35,
            "spread": 0.02,
            "bid": 1.0,
            "ask": 1.05,
            "volume": 100,
            "capital": 100_000.0,
            "available_capital": 100_000.0,
            "pnl": 0.0,
            "connected": True,
            "db_up": True,
            "redis_up": True,
            "token_valid": True,
            "reconcile_ok": True,
            "can_close": True,
            "halted": False,
            "data_corrupt": False,
            "data_frozen": False,
            "duplicate_messages": False,
            "duplicate_workers": False,
            "uncertain_orders": 0,
            "open_positions": 0,
            "circuit_breaker": False,
            "authorized_capital": 100_000.0,
            "events": [],
            **(initial_state or {}),
        }
        results = [self.run_one(sid, dict(state0)) for sid in self.scenarios]
        failed_crit = [r.scenario_id for r in results if r.critical and not r.passed]
        actions = []
        if failed_crit:
            actions.append("No avanzar a trading real: fallaron escenarios críticos")
            actions.append(f"Revisar: {', '.join(failed_crit)}")
        actions.append("Verificar circuit breakers y reconciliación tras fallas operativas")
        summary = (
            f"{sum(1 for r in results if r.passed)}/{len(results)} escenarios OK; "
            f"críticos fallidos={len(failed_crit)}"
        )
        return StressReport(
            as_of=datetime.utcnow(),
            results=results,
            executive_summary=summary,
            failed_critical=failed_crit,
            recommended_actions=actions,
            blocks_live=bool(failed_crit),
        )

    def run_one(self, scenario_id: str, state: dict[str, Any]) -> ScenarioResult:
        sc = self.scenarios[scenario_id]
        if sc.apply:
            state = sc.apply(state)
        state = self._apply_platform_defenses(state)
        metrics, failures, evidence = self._evaluate(state)
        passed = len(failures) == 0
        residual = []
        if state.get("spread", 0) > 0.1:
            residual.append("spreads elevados residuales")
        if metrics.estimated_ruin_risk and metrics.estimated_ruin_risk > 0.05:
            residual.append("riesgo de ruina estimado >5% bajo supuestos explícitos")
        return ScenarioResult(
            scenario_id=sc.id,
            name=sc.name,
            critical=sc.critical,
            passed=passed,
            metrics=metrics,
            failures=failures,
            residual_risks=residual,
            evidence=evidence,
            final_state={k: v for k, v in state.items() if k != "events"},
        )

    def _apply_platform_defenses(self, state: dict[str, Any]) -> dict[str, Any]:
        """Simula controles esperados de la plataforma ante el hazard."""
        out = dict(state)
        events = list(out.get("events", []))

        # No operar con datos inválidos / desconexión / halt / token
        if (
            out.get("data_corrupt")
            or out.get("data_frozen")
            or not out.get("connected", True)
            or out.get("halted")
            or not out.get("token_valid", True)
            or out.get("broker_timeout")
            or out.get("clock_skew_seconds", 0) > 60
        ):
            out["circuit_breaker"] = True
            out["trading_allowed_with_bad_data"] = False
            out["traded_with_expired_token"] = False
            out["new_orders_placed"] = False
            events.append("defense:circuit_breaker")

        # Duplicados / dos workers → idempotencia + no nuevas órdenes
        if out.get("duplicate_messages") or out.get("duplicate_workers") or out.get("out_of_order"):
            out["idempotency_guard"] = True
            out["duplicate_orders_created"] = False
            out["new_orders_placed"] = False
            out["circuit_breaker"] = True
            events.append("defense:idempotency")

        # Sin bid/ask → no operar, permitir intento de cierre marcado
        if out.get("bid") is None or out.get("ask") is None:
            out["new_orders_placed"] = False
            out["circuit_breaker"] = True
            events.append("defense:no_quote_block")

        # Capital insuficiente → no comprar
        if float(out.get("available_capital", 1)) <= 0:
            out["new_orders_placed"] = False
            events.append("defense:no_capital_block")

        # DB/Redis down → modo degradado, solo cierre
        if not out.get("db_up", True) or not out.get("redis_up", True):
            out["degraded_mode"] = True
            out["new_orders_placed"] = False
            out["closes_allowed"] = True
            events.append("defense:degraded_closes_only")

        # Reconciliación inconsistente → freeze + alert
        if not out.get("reconcile_ok", True):
            out["trading_frozen"] = True
            out["new_orders_placed"] = False
            # la falla de recon sigue siendo crítica hasta resolver
            events.append("defense:freeze_on_bad_recon")

        # Órdenes inciertas → no duplicar envío
        if int(out.get("uncertain_orders", 0)) > 0:
            out["suppress_resubmit"] = True
            events.append("defense:suppress_resubmit")

        # Imposible cerrar: residual risk, intentar marcar
        if not out.get("can_close", True):
            out["escalated"] = True
            events.append("defense:escalate_illiquid_exit")

        # Racha / pérdidas simultáneas / delta excesivo → circuit breaker
        if (
            out.get("simultaneous_losses")
            or int(out.get("consecutive_losses", 0)) >= 5
            or float(out.get("portfolio_delta", 0)) > 1000
        ):
            out["circuit_breaker"] = True
            out["new_orders_placed"] = False
            events.append("defense:risk_circuit_breaker")

        out["events"] = events
        return out

    def _evaluate(self, state: dict[str, Any]) -> tuple[StressMetrics, list[str], list[str]]:
        capital0 = float(state.get("authorized_capital", 100000))
        capital = float(state.get("capital", capital0)) + float(state.get("pnl", 0))
        max_loss = max(0.0, capital0 - capital)
        dd = max_loss / capital0 if capital0 else 0.0
        metrics = StressMetrics(
            max_loss=max_loss,
            drawdown=dd,
            min_capital=capital,
            unclosed_ops=0 if state.get("can_close", True) else int(state.get("open_positions", 0)),
            uncertain_orders=int(state.get("uncertain_orders", 0)),
            degraded_time_steps=1
            if (
                not state.get("connected", True)
                or state.get("latency_ms", 0) > 1000
                or state.get("degraded_mode")
            )
            else 0,
            circuit_breaker_activations=1 if state.get("circuit_breaker") else 0,
            limit_violations=0,
            slippage_loss=float(state.get("spread", 0)) * 100,
            liquidity_loss=50.0 if state.get("bid") is None or state.get("ask") is None else 0.0,
            estimated_ruin_risk=min(1.0, dd * 1.5) if dd > 0 else 0.0,
            ruin_assumptions=["proxy lineal dd*1.5; no es probabilidad real de ruina"],
        )
        failures: list[str] = []
        evidence: list[str] = list(state.get("events", []))

        if metrics.drawdown > self.criteria.max_drawdown:
            failures.append(f"drawdown {metrics.drawdown:.2%} > {self.criteria.max_drawdown:.2%}")
        if capital0 and max_loss / capital0 > self.criteria.max_loss_pct:
            failures.append("pérdida máxima supera criterio")

        if self.criteria.zero_duplicate_orders and state.get("duplicate_orders_created"):
            failures.append("se crearon órdenes duplicadas")
            evidence.append("duplicate_orders_created=true")

        if state.get("duplicate_workers") and not state.get("idempotency_guard"):
            failures.append("dos workers sin guarda de idempotencia")

        if not state.get("reconcile_ok", True) and self.criteria.reconcile_must_pass:
            failures.append("reconciliación inconsistente no resuelta")

        if state.get("available_capital", 0) is not None and float(state.get("available_capital", 0)) < 0:
            failures.append("capital negativo")

        if (
            self.criteria.never_exceed_authorized_capital
            and float(state.get("exposure", 0)) > float(state.get("authorized_capital", capital0))
        ):
            failures.append("exposición supera capital autorizado")
            metrics.limit_violations += 1

        if state.get("data_corrupt") or state.get("data_frozen"):
            if self.criteria.never_trade_invalid_data and state.get("trading_allowed_with_bad_data"):
                failures.append("operó con datos inválidos")
            elif state.get("circuit_breaker"):
                evidence.append("trading bloqueado ante datos inválidos (OK)")

        if state.get("halted") and state.get("new_orders_placed"):
            failures.append("operó con activo suspendido")

        if not state.get("can_close", True):
            # posición imposible de cerrar: falla crítica de liquidez residual
            failures.append("posición imposible de cerrar (riesgo residual)")
            metrics.unclosed_ops = max(metrics.unclosed_ops, 1)

        if int(state.get("uncertain_orders", 0)) > 0 and not state.get("suppress_resubmit"):
            failures.append("órdenes inciertas sin supresión de reenvío")

        if not state.get("token_valid", True) and state.get("traded_with_expired_token"):
            failures.append("operó con token vencido")
        elif not state.get("token_valid", True):
            evidence.append("rechazo por token vencido (OK)")

        # pérdidas simultáneas / streak: activar CB si dd alto
        if state.get("simultaneous_losses") or int(state.get("consecutive_losses", 0)) >= 5:
            if not state.get("circuit_breaker"):
                failures.append("pérdidas en serie sin circuit breaker")
            else:
                evidence.append("circuit breaker ante racha/pérdidas (OK)")

        if float(state.get("portfolio_delta", 0)) > 1000 and not state.get("circuit_breaker"):
            # forzar detección: en defenses no lo pusimos; marcar violación de límite
            failures.append("delta excesivo sin corte")
            metrics.limit_violations += 1

        return metrics, failures, evidence


class MonteCarloRunner:
    """Variación de fricciones operativas — no prueba de rentabilidad futura."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def run(
        self,
        base_pnls: list[float],
        *,
        n_paths: int = 200,
        slip_std: float = 0.02,
        spread_std: float = 0.01,
        latency_impact: float = 0.005,
    ) -> dict[str, Any]:
        path_stats = []
        for _ in range(n_paths):
            order = list(base_pnls)
            self.rng.shuffle(order)
            equity = 0.0
            peak = 0.0
            max_dd = 0.0
            streak = 0
            max_streak = 0
            for pnl in order:
                slip = self.rng.gauss(0, slip_std)
                spr = abs(self.rng.gauss(0, spread_std))
                lat = abs(self.rng.gauss(0, latency_impact))
                liq = abs(self.rng.gauss(0, 0.01))
                realized = pnl - slip - spr - lat - liq
                equity += realized
                peak = max(peak, equity)
                max_dd = max(max_dd, peak - equity)
                if realized < 0:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0
            path_stats.append(
                {
                    "final": equity,
                    "max_dd": max_dd,
                    "max_loss_streak": max_streak,
                }
            )
        finals = sorted(p["final"] for p in path_stats)
        return {
            "n_paths": n_paths,
            "median_final": finals[len(finals) // 2],
            "p05_final": finals[max(0, int(0.05 * len(finals)) - 1)],
            "p95_final": finals[min(len(finals) - 1, int(0.95 * len(finals)))],
            "median_dd": sorted(p["max_dd"] for p in path_stats)[len(path_stats) // 2],
            "disclaimer": "Monte Carlo de fricciones/orden — no es proyección de rentabilidad",
            "hash": hashlib.sha256(str(finals[:10]).encode()).hexdigest()[:16],
        }

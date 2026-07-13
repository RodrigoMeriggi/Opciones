"""Motor de selección de contratos (Prompt 17)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from opciones.domain.enums import OptionType
from opciones.domain.models import (
    MarketQuote,
    OptionChain,
    OptionContract,
    OrderRequest,
    PortfolioSnapshot,
    Position,
    RiskValidationResult,
)
from opciones.modules.pricing_engine.types import Greeks
from opciones.modules.pricing_engine.validation import moneyness_label
from opciones.ports import RiskManager


class ContractCategory(StrEnum):
    DEEP_ITM = "DEEP_ITM"
    ITM = "ITM"
    ATM = "ATM"
    OTM = "OTM"
    DEEP_OTM = "DEEP_OTM"


@dataclass
class ScoreComponent:
    name: str
    weight: float
    raw_score: float  # 0-100
    enabled: bool
    explanation: str

    @property
    def weighted(self) -> float:
        return self.raw_score * self.weight if self.enabled else 0.0


@dataclass
class CandidateEvaluation:
    contract: OptionContract
    category: ContractCategory
    discarded: bool
    discard_reasons: list[str] = field(default_factory=list)
    components: list[ScoreComponent] = field(default_factory=list)
    total_score: float = 0.0
    penalties: list[str] = field(default_factory=list)
    greeks: Greeks | None = None
    assumptions: list[str] = field(default_factory=list)
    data_quality: float = 0.0
    risk_result: RiskValidationResult | None = None


@dataclass
class SelectionResult:
    signal_direction: str  # BULLISH / BEARISH
    underlying_symbol: str
    winner: CandidateEvaluation | None
    runners_up: list[CandidateEvaluation]
    all_candidates: list[CandidateEvaluation]
    no_trade: bool
    no_trade_reason: str | None
    assumptions: list[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    disclaimer: str = (
        "La selección no garantiza rentabilidad; prima baja no implica mejor contrato."
    )


DEFAULT_WEIGHTS: dict[str, float] = {
    "liquidity": 0.12,
    "spread": 0.14,
    "data_quality": 0.10,
    "expiry_fit": 0.10,
    "strike_fit": 0.10,
    "delta": 0.10,
    "theta": 0.08,
    "vega": 0.05,
    "iv_hv": 0.08,
    "premium": 0.05,
    "risk": 0.04,
    "execution": 0.04,
}


class ContractSelector:
    """
    Separado de la señal del subyacente.
    Nunca elige solo por prima baja.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.config = {
            "min_dte": 7,
            "max_dte": 45,
            "max_spread_pct": 8.0,
            "min_volume": 10,
            "max_quote_age_seconds": 120,
            "max_premium_capital": 50000.0,
            "prefer_atm": True,
            "delta_min": 0.40,
            "delta_max": 0.65,
            "avoid_deep_otm": True,
            "max_theta_daily_abs": 50.0,
            "prefer_mid_expiry": True,
            "require_greeks": False,
            "weights": dict(DEFAULT_WEIGHTS),
            "disabled_components": [],
            "max_per_underlying": 2,
            "max_per_expiry": 2,
            **(config or {}),
        }
        self.risk_manager = risk_manager
        self._exposure_counts: dict[str, int] = {}
        self._expiry_counts: dict[str, int] = {}

    def classify(self, contract: OptionContract, spot: float) -> ContractCategory:
        label = moneyness_label(spot, float(contract.strike), contract.option_type.value)
        return ContractCategory(label)

    def select(
        self,
        chain: OptionChain,
        signal_direction: str,
        *,
        historical_vol: float | None = None,
        greeks_by_symbol: dict[str, Greeks] | None = None,
        portfolio: PortfolioSnapshot | None = None,
        positions: list[Position] | None = None,
        order_side: str = "BUY",
    ) -> SelectionResult:
        spot = float(chain.underlying_price or 0)
        assumptions = [
            "score multicriterio; prima no es criterio único",
            f"señal={signal_direction}",
        ]
        want_calls = signal_direction.upper() == "BULLISH"
        candidates: list[CandidateEvaluation] = []

        for c in chain.contracts:
            if want_calls and c.option_type != OptionType.CALL:
                continue
            if not want_calls and c.option_type != OptionType.PUT:
                continue
            ev = self._evaluate(
                c,
                spot,
                historical_vol=historical_vol,
                greeks=(greeks_by_symbol or {}).get(c.symbol),
            )
            candidates.append(ev)

        # filtros + risk
        for ev in candidates:
            if ev.discarded:
                continue
            if self.risk_manager and portfolio is not None:
                req = OrderRequest(
                    symbol=ev.contract.symbol,
                    side=order_side,  # type: ignore[arg-type]
                    quantity=1,
                    order_type="LIMIT",  # type: ignore[arg-type]
                    limit_price=ev.contract.ask,
                    underlying_symbol=chain.underlying_symbol,
                    option_type=ev.contract.option_type,
                    strategy_id="contract_selector",
                )
                # Risk validation sync wrapper expectation — DefaultRiskManager is async
                # defer: mark pending; actual validate done by caller async path
                ev.assumptions.append("RiskManager debe validar antes de ejecutar")

        viable = [c for c in candidates if not c.discarded]
        viable.sort(key=lambda x: x.total_score, reverse=True)

        # diversificación
        filtered: list[CandidateEvaluation] = []
        for c in viable:
            und = c.contract.underlying_symbol
            exp = str(c.contract.expiration_date)
            if self._exposure_counts.get(und, 0) >= int(self.config["max_per_underlying"]):
                c.discarded = True
                c.discard_reasons.append("límite exposición por subyacente")
                continue
            if self._expiry_counts.get(f"{und}:{exp}", 0) >= int(self.config["max_per_expiry"]):
                c.discarded = True
                c.discard_reasons.append("límite exposición por vencimiento")
                continue
            # evitar casi equivalentes: mismo strike±1% y mismo expiry
            if any(
                abs(float(x.contract.strike) - float(c.contract.strike))
                / max(float(c.contract.strike), 1)
                < 0.01
                and x.contract.expiration_date == c.contract.expiration_date
                for x in filtered
            ):
                c.discarded = True
                c.discard_reasons.append("contrato casi equivalente ya priorizado")
                continue
            filtered.append(c)

        if not filtered:
            return SelectionResult(
                signal_direction=signal_direction,
                underlying_symbol=chain.underlying_symbol,
                winner=None,
                runners_up=[],
                all_candidates=candidates,
                no_trade=True,
                no_trade_reason="ningún contrato aceptable tras filtros/score",
                assumptions=assumptions,
            )

        winner = filtered[0]
        runners = filtered[1:3]
        return SelectionResult(
            signal_direction=signal_direction,
            underlying_symbol=chain.underlying_symbol,
            winner=winner,
            runners_up=runners,
            all_candidates=candidates,
            no_trade=False,
            no_trade_reason=None,
            assumptions=assumptions,
        )

    async def select_with_risk(
        self,
        chain: OptionChain,
        signal_direction: str,
        portfolio: PortfolioSnapshot,
        positions: list[Position],
        *,
        historical_vol: float | None = None,
        greeks_by_symbol: dict[str, Greeks] | None = None,
    ) -> SelectionResult:
        result = self.select(
            chain,
            signal_direction,
            historical_vol=historical_vol,
            greeks_by_symbol=greeks_by_symbol,
            portfolio=portfolio,
            positions=positions,
        )
        if result.no_trade or result.winner is None or self.risk_manager is None:
            return result

        # re-rank viable with risk approval
        approved: list[CandidateEvaluation] = []
        for ev in sorted(
            [c for c in result.all_candidates if not c.discarded],
            key=lambda x: x.total_score,
            reverse=True,
        ):
            quote = ev.contract.to_quote()
            req = OrderRequest(
                symbol=ev.contract.symbol,
                side="BUY",  # type: ignore[arg-type]
                quantity=1,
                order_type="LIMIT",  # type: ignore[arg-type]
                limit_price=ev.contract.ask,
                underlying_symbol=chain.underlying_symbol,
                option_type=ev.contract.option_type,
                strategy_id="contract_selector",
            )
            risk = await self.risk_manager.validate_order(
                req, quote, portfolio, positions, ev.contract
            )
            ev.risk_result = risk
            if not risk.approved:
                ev.discarded = True
                ev.discard_reasons.append(
                    f"RiskManager rechazó: {risk.primary_code or risk.messages}"
                )
                continue
            approved.append(ev)

        if not approved:
            result.winner = None
            result.runners_up = []
            result.no_trade = True
            result.no_trade_reason = "RiskManager rechazó todos los candidatos"
            return result

        result.winner = approved[0]
        result.runners_up = approved[1:3]
        result.no_trade = False
        result.no_trade_reason = None
        return result

    def _evaluate(
        self,
        contract: OptionContract,
        spot: float,
        *,
        historical_vol: float | None,
        greeks: Greeks | None,
    ) -> CandidateEvaluation:
        reasons: list[str] = []
        category = self.classify(contract, spot) if spot > 0 else ContractCategory.ATM

        if contract.bid is None or contract.ask is None:
            reasons.append("sin bid/ask")
        elif contract.bid > contract.ask:
            reasons.append("bid/ask inconsistente")
        spread = float(contract.percentage_spread or 999)
        if spread > float(self.config["max_spread_pct"]):
            reasons.append(f"spread excesivo ({spread:.2f}%)")
        if contract.timestamp is None:
            reasons.append("cotización sin timestamp")
        else:
            age = (datetime.utcnow() - contract.timestamp.replace(tzinfo=None)).total_seconds()
            if age > float(self.config["max_quote_age_seconds"]):
                reasons.append("cotización desactualizada")
        dte = contract.days_to_expiration
        if dte is None:
            reasons.append("DTE desconocido")
        else:
            if dte < int(self.config["min_dte"]):
                reasons.append("vencimiento demasiado cerca")
            if dte > int(self.config["max_dte"]):
                reasons.append("vencimiento demasiado lejos")
        if (contract.volume or 0) < int(self.config["min_volume"]):
            reasons.append("volumen insuficiente")
        if contract.contract_size <= 0:
            reasons.append("tamaño de contrato inválido")
        premium = float(contract.ask or 0)
        notional = premium * contract.contract_size
        if notional > float(self.config["max_premium_capital"]):
            reasons.append("prima excede capital permitido")
        if self.config["avoid_deep_otm"] and category == ContractCategory.DEEP_OTM:
            reasons.append("política: evitar deep OTM")
        if self.config["require_greeks"] and greeks is None:
            reasons.append("griegas requeridas no disponibles")
        if greeks and greeks.theta_daily is not None:
            if abs(greeks.theta_daily) > float(self.config["max_theta_daily_abs"]):
                reasons.append("theta excesivo")

        components = self._score_components(contract, spot, category, historical_vol, greeks)
        disabled = set(self.config.get("disabled_components") or [])
        for comp in components:
            if comp.name in disabled:
                comp.enabled = False
        total = sum(c.weighted for c in components)
        # normalizar a 0-100 según pesos activos
        wsum = sum(c.weight for c in components if c.enabled) or 1.0
        total_norm = total / wsum

        penalties: list[str] = []
        if spread > float(self.config["max_spread_pct"]) * 0.7:
            total_norm *= 0.9
            penalties.append("penalización spread amplio")
        if (contract.volume or 0) < int(self.config["min_volume"]) * 2:
            total_norm *= 0.95
            penalties.append("penalización volumen bajo")
        if contract.open_interest == 0:
            total_norm *= 0.9
            penalties.append("penalización OI nulo")
        if premium < 1.0 and (contract.volume or 0) < 20:
            total_norm *= 0.85
            penalties.append("penalización prima baja + poca liquidez")
        iv = float(contract.implied_volatility) if contract.implied_volatility is not None else None
        if iv is not None and (iv > 2.0 or iv < 0.05):
            total_norm *= 0.85
            penalties.append("penalización IV extrema")

        data_q = next((c.raw_score for c in components if c.name == "data_quality"), 0.0)

        return CandidateEvaluation(
            contract=contract,
            category=category,
            discarded=bool(reasons),
            discard_reasons=reasons,
            components=components,
            total_score=max(0.0, min(100.0, total_norm)),
            penalties=penalties,
            greeks=greeks,
            data_quality=data_q,
        )

    def _score_components(
        self,
        contract: OptionContract,
        spot: float,
        category: ContractCategory,
        historical_vol: float | None,
        greeks: Greeks | None,
    ) -> list[ScoreComponent]:
        weights: dict[str, float] = dict(self.config["weights"])
        out: list[ScoreComponent] = []

        vol = contract.volume or 0
        liq = min(100.0, (vol / 100.0) * 100)
        out.append(
            ScoreComponent(
                "liquidity",
                weights.get("liquidity", 0.12),
                liq,
                True,
                f"volumen={vol}",
            )
        )

        spread = float(contract.percentage_spread or 100)
        max_sp = float(self.config["max_spread_pct"])
        sp_score = max(0.0, 100.0 * (1 - spread / max(max_sp, 0.01)))
        out.append(
            ScoreComponent(
                "spread",
                weights.get("spread", 0.14),
                sp_score,
                True,
                f"spread={spread:.2f}% (máx {max_sp})",
            )
        )

        dq = 100.0 if contract.bid and contract.ask and contract.timestamp else 20.0
        out.append(
            ScoreComponent(
                "data_quality",
                weights.get("data_quality", 0.10),
                dq,
                True,
                "bid/ask/timestamp presentes" if dq > 50 else "datos incompletos",
            )
        )

        dte = contract.days_to_expiration or 0
        mid = (int(self.config["min_dte"]) + int(self.config["max_dte"])) / 2
        exp_score = max(0.0, 100.0 * (1 - abs(dte - mid) / max(mid, 1)))
        out.append(
            ScoreComponent(
                "expiry_fit",
                weights.get("expiry_fit", 0.10),
                exp_score,
                True,
                f"DTE={dte}, preferido~{mid:.0f}",
            )
        )

        if spot > 0:
            dist = abs(float(contract.strike) - spot) / spot * 100
            strike_score = max(0.0, 100.0 * (1 - dist / 15.0))
            if self.config["prefer_atm"] and category == ContractCategory.ATM:
                strike_score = min(100.0, strike_score + 10)
            expl = f"distancia strike={dist:.2f}%, categoría={category}"
        else:
            strike_score = 0.0
            expl = "spot desconocido"
        out.append(
            ScoreComponent(
                "strike_fit",
                weights.get("strike_fit", 0.10),
                strike_score,
                True,
                expl,
            )
        )

        if greeks and greeks.delta is not None:
            d = abs(greeks.delta)
            dmin, dmax = float(self.config["delta_min"]), float(self.config["delta_max"])
            if dmin <= d <= dmax:
                delta_score = 100.0
                de = f"delta={d:.3f} en rango [{dmin},{dmax}]"
            else:
                delta_score = max(0.0, 100.0 - abs(d - (dmin + dmax) / 2) * 200)
                de = f"delta={d:.3f} fuera de rango preferido"
        else:
            delta_score = 40.0
            de = "delta no disponible; score neutro"
        out.append(
            ScoreComponent("delta", weights.get("delta", 0.10), delta_score, True, de)
        )

        if greeks and greeks.theta_daily is not None:
            th = abs(greeks.theta_daily)
            tmax = float(self.config["max_theta_daily_abs"])
            theta_score = max(0.0, 100.0 * (1 - th / max(tmax, 1e-6)))
            te = f"|theta_daily|={th:.4f}"
        else:
            theta_score = 40.0
            te = "theta no disponible"
        out.append(
            ScoreComponent("theta", weights.get("theta", 0.08), theta_score, True, te)
        )

        if greeks and greeks.vega_per_pct is not None:
            # vega moderada preferible para compra direccional
            v = abs(greeks.vega_per_pct)
            vega_score = max(0.0, 100.0 - min(v, 100))
            ve = f"vega/pct={v:.4f}"
        else:
            vega_score = 40.0
            ve = "vega no disponible"
        out.append(
            ScoreComponent("vega", weights.get("vega", 0.05), vega_score, True, ve)
        )

        iv = float(contract.implied_volatility) if contract.implied_volatility is not None else None
        if iv is not None and historical_vol and historical_vol > 0:
            ratio = iv / historical_vol
            iv_score = max(0.0, 100.0 * (1 - abs(ratio - 1.0)))
            ie = f"IV/HV={ratio:.2f}"
        else:
            iv_score = 35.0
            ie = "IV/HV incompleto"
        out.append(
            ScoreComponent("iv_hv", weights.get("iv_hv", 0.08), iv_score, True, ie)
        )

        # prima: asequible pero NO recompensar ser la más barata
        premium = float(contract.ask or 0)
        max_cap = float(self.config["max_premium_capital"])
        afford = max(0.0, 100.0 * (1 - premium * contract.contract_size / max(max_cap, 1)))
        # techo: no dar más de 70 solo por barata
        premium_score = min(70.0, afford)
        out.append(
            ScoreComponent(
                "premium",
                weights.get("premium", 0.05),
                premium_score,
                True,
                f"prima={premium} (tope score 70 para no privilegiar baratas)",
            )
        )

        risk_score = 80.0 if contract.open_interest and contract.open_interest > 0 else 40.0
        out.append(
            ScoreComponent(
                "risk",
                weights.get("risk", 0.04),
                risk_score,
                True,
                f"OI={contract.open_interest}",
            )
        )

        # ejecución esperada: mid disponible + spread
        exec_score = sp_score * 0.7 + (30.0 if contract.bid and contract.ask else 0)
        out.append(
            ScoreComponent(
                "execution",
                weights.get("execution", 0.04),
                min(100.0, exec_score),
                True,
                "proxy ejecución por spread/libro",
            )
        )
        return out

    def register_selection(self, evaluation: CandidateEvaluation) -> None:
        und = evaluation.contract.underlying_symbol
        exp = f"{und}:{evaluation.contract.expiration_date}"
        self._exposure_counts[und] = self._exposure_counts.get(und, 0) + 1
        self._expiry_counts[exp] = self._expiry_counts.get(exp, 0) + 1

"""API interna del motor de valuación."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from opciones.modules.pricing_engine.iv.solver import IVResult, IVSolverConfig, solve_implied_volatility
from opciones.modules.pricing_engine.models.base import OptionPricingModel
from opciones.modules.pricing_engine.models.binomial import BinomialAmericanModel
from opciones.modules.pricing_engine.models.black_scholes import (
    BlackScholesMertonModel,
    BlackScholesModel,
)
from opciones.modules.pricing_engine.providers.base import (
    DividendProvider,
    ExplicitMissingDividendProvider,
    ManualRiskFreeRateProvider,
    RiskFreeRateProvider,
)
from opciones.modules.pricing_engine.types import (
    ExerciseStyle,
    PricingInputs,
    PricingResult,
    PricingStatus,
)


class PricingEngine:
    """Fachada: selecciona modelo, resuelve IV, adjunta metadatos de fuentes."""

    def __init__(
        self,
        rate_provider: RiskFreeRateProvider | None = None,
        dividend_provider: DividendProvider | None = None,
        *,
        default_european: OptionPricingModel | None = None,
        default_american: OptionPricingModel | None = None,
        iv_config: IVSolverConfig | None = None,
    ) -> None:
        self.rate_provider = rate_provider  # puede ser None → exigir rate en inputs
        self.dividend_provider = dividend_provider or ExplicitMissingDividendProvider(
            assume_zero_with_warning=True
        )
        self.european = default_european or BlackScholesMertonModel()
        self.american = default_american or BinomialAmericanModel(steps=100)
        self.bs = BlackScholesModel()
        self.iv_config = iv_config or IVSolverConfig()

    def select_model(self, style: ExerciseStyle) -> OptionPricingModel:
        if style == ExerciseStyle.AMERICAN:
            return self.american
        return self.european

    def enrich_inputs(
        self,
        inputs: PricingInputs,
        *,
        underlying_symbol: str | None = None,
    ) -> PricingInputs:
        assumptions = list(inputs.assumptions)
        data: dict[str, Any] = {}
        rate = inputs.rate
        if self.rate_provider is not None:
            rq = self.rate_provider.get_rate(inputs.time_to_expiry_years)
            rate = rq.rate
            assumptions.extend(rq.assumptions)
            data["rate_source"] = rq.source
            data["rate_version"] = rq.source_version
        elif rate is None:  # type: ignore[unreachable]
            pass

        q = inputs.dividend_yield
        discrete = list(inputs.discrete_dividends)
        if underlying_symbol:
            div = self.dividend_provider.get_dividends(underlying_symbol)
            assumptions.extend(div.assumptions)
            data["div_source"] = div.source
            data["div_version"] = div.source_version
            if not div.data_available and div.continuous_yield is None:
                raise ValueError(
                    "sin datos de dividendos y sin supuesto explícito; "
                    "use ExplicitMissingDividendProvider(assume_zero_with_warning=True)"
                )
            if div.continuous_yield is not None:
                q = div.continuous_yield
            if div.discrete:
                discrete = div.discrete

        return inputs.model_copy(
            update={
                "rate": rate,
                "dividend_yield": q,
                "discrete_dividends": discrete,
                "assumptions": assumptions,
            }
        )

    def value(self, inputs: PricingInputs, *, underlying_symbol: str | None = None) -> PricingResult:
        enriched = self.enrich_inputs(inputs, underlying_symbol=underlying_symbol)
        model = self.select_model(enriched.exercise_style)
        result = model.price(enriched)
        result.data_source = "pricing_engine"
        result.parameters = {
            **result.parameters,
            "rate_provider": getattr(self.rate_provider, "version", None),
        }
        return result

    def implied_vol(self, inputs: PricingInputs, *, underlying_symbol: str | None = None) -> IVResult:
        enriched = self.enrich_inputs(inputs, underlying_symbol=underlying_symbol)
        if enriched.market_price is None:
            return IVResult(
                None,
                None,
                0,
                False,
                PricingStatus.INCOMPLETE_DATA,
                ["falta market_price"],
            )
        return solve_implied_volatility(
            enriched.market_price,
            enriched.spot,
            enriched.strike,
            enriched.time_to_expiry_years,
            enriched.rate,
            enriched.dividend_yield,
            enriched.option_type,
            self.iv_config,
        )

    def full_metrics(
        self,
        inputs: PricingInputs,
        *,
        underlying_symbol: str | None = None,
        resolve_iv: bool = True,
    ) -> PricingResult:
        enriched = self.enrich_inputs(inputs, underlying_symbol=underlying_symbol)
        iv_res: IVResult | None = None
        if resolve_iv and enriched.market_price is not None:
            iv_res = self.implied_vol(enriched)
            if iv_res.converged and iv_res.implied_volatility is not None:
                enriched = enriched.model_copy(update={"volatility": iv_res.implied_volatility})
            elif enriched.volatility is None:
                # sin vol ni IV: incompleto
                return PricingResult(
                    model="n/a",
                    warnings=(iv_res.warnings if iv_res else [])
                    + ["sin volatilidad ni IV convergente"],
                    assumptions=enriched.assumptions,
                    confidence=0.0,
                    convergence_status=PricingStatus.NO_CONVERGENCE
                    if iv_res and not iv_res.converged
                    else PricingStatus.INCOMPLETE_DATA,
                    timestamp=datetime.utcnow(),
                )

        result = self.value(enriched)
        if iv_res is not None:
            result.implied_volatility = iv_res.implied_volatility
            result.warnings = list(result.warnings) + list(iv_res.warnings)
            if not iv_res.converged:
                result.convergence_status = iv_res.status
                result.confidence = min(result.confidence, 0.3)
            else:
                result.parameters["iv_method"] = iv_res.method
                result.parameters["iv_iterations"] = iv_res.iterations
        return result


def default_engine(manual_rate: float = 0.40) -> PricingEngine:
    """Factory de demo: tasa manual explícita (ARS suele ser alta; configurable)."""
    return PricingEngine(
        rate_provider=ManualRiskFreeRateProvider(manual_rate, source_version="demo-manual"),
        dividend_provider=ExplicitMissingDividendProvider(assume_zero_with_warning=True),
    )

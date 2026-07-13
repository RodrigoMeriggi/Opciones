"""Pricing engine — valuación, IV, griegas y superficie."""

from opciones.modules.pricing_engine.engine import PricingEngine, default_engine
from opciones.modules.pricing_engine.models.base import OptionPricingModel
from opciones.modules.pricing_engine.models.binomial import BinomialAmericanModel
from opciones.modules.pricing_engine.models.black_scholes import (
    BlackScholesMertonModel,
    BlackScholesModel,
    bsm_price,
)
from opciones.modules.pricing_engine.providers.base import (
    ContinuousDividendProvider,
    CurveRiskFreeRateProvider,
    DiscreteDividendProvider,
    DividendProvider,
    ExplicitMissingDividendProvider,
    ExternalRateAdapter,
    ManualRiskFreeRateProvider,
    RiskFreeRateProvider,
)
from opciones.modules.pricing_engine.surface.vol_surface import VolatilitySurface
from opciones.modules.pricing_engine.types import (
    ExerciseStyle,
    Greeks,
    PricingInputs,
    PricingResult,
    PricingStatus,
)
from opciones.modules.pricing_engine.validation import intrinsic

# compatibilidad con API previa
from opciones.domain.enums import OptionType
from decimal import Decimal


def intrinsic_only(
    option_type: OptionType,
    strike: Decimal,
    spot: Decimal,
) -> Decimal:
    if option_type == OptionType.CALL:
        return max(spot - strike, Decimal("0"))
    return max(strike - spot, Decimal("0"))


__all__ = [
    "PricingEngine",
    "default_engine",
    "OptionPricingModel",
    "BlackScholesModel",
    "BlackScholesMertonModel",
    "BinomialAmericanModel",
    "bsm_price",
    "RiskFreeRateProvider",
    "DividendProvider",
    "ManualRiskFreeRateProvider",
    "CurveRiskFreeRateProvider",
    "ExternalRateAdapter",
    "ContinuousDividendProvider",
    "DiscreteDividendProvider",
    "ExplicitMissingDividendProvider",
    "VolatilitySurface",
    "ExerciseStyle",
    "Greeks",
    "PricingInputs",
    "PricingResult",
    "PricingStatus",
    "intrinsic",
    "intrinsic_only",
]

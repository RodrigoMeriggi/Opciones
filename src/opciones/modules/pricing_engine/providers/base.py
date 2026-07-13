"""Proveedores de tasa libre de riesgo y dividendos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RateQuote:
    rate: float
    tenor_years: float
    source: str
    source_version: str
    as_of: datetime
    assumptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DividendInfo:
    continuous_yield: float | None
    discrete: list[dict[str, float]]  # {"t": years, "amount": cash}
    ex_dates: list[str]
    source: str
    source_version: str
    as_of: datetime
    data_available: bool
    assumptions: list[str] = field(default_factory=list)


class RiskFreeRateProvider(ABC):
    """No fijar una tasa arbitraria en el motor; inyectar vía proveedor."""

    @abstractmethod
    def get_rate(self, tenor_years: float, as_of: datetime | None = None) -> RateQuote:
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        ...


class ManualRiskFreeRateProvider(RiskFreeRateProvider):
    def __init__(self, rate: float, source_version: str = "manual-v1") -> None:
        if rate < -0.5 or rate > 2.0:
            raise ValueError("tasa fuera de rango razonable; revisar configuración")
        self._rate = rate
        self._version = source_version

    @property
    def version(self) -> str:
        return self._version

    def get_rate(self, tenor_years: float, as_of: datetime | None = None) -> RateQuote:
        return RateQuote(
            rate=self._rate,
            tenor_years=tenor_years,
            source="manual",
            source_version=self._version,
            as_of=as_of or datetime.utcnow(),
            assumptions=[f"tasa plana manual={self._rate}"],
        )


class CurveRiskFreeRateProvider(RiskFreeRateProvider):
    """Curva por plazos: interpolación lineal en tenor; sin extrapolación silenciosa."""

    def __init__(
        self,
        points: list[tuple[float, float]],
        source_version: str = "curve-v1",
        *,
        allow_extrapolation: bool = False,
    ) -> None:
        if len(points) < 1:
            raise ValueError("curva vacía")
        self._points = sorted(points, key=lambda p: p[0])
        self._version = source_version
        self._allow_extrapolation = allow_extrapolation

    @property
    def version(self) -> str:
        return self._version

    def get_rate(self, tenor_years: float, as_of: datetime | None = None) -> RateQuote:
        assumptions: list[str] = []
        tenors = [p[0] for p in self._points]
        rates = [p[1] for p in self._points]
        if tenor_years < tenors[0] or tenor_years > tenors[-1]:
            if not self._allow_extrapolation:
                raise ValueError(
                    f"tenor {tenor_years} fuera de curva [{tenors[0]}, {tenors[-1]}]; "
                    "no se extrapola silenciosamente"
                )
            assumptions.append("extrapolación explícitamente permitida")
            rate = rates[0] if tenor_years < tenors[0] else rates[-1]
        else:
            rate = _linear_interp(tenors, rates, tenor_years)
            assumptions.append("interpolación lineal en curva")
        return RateQuote(
            rate=rate,
            tenor_years=tenor_years,
            source="curve",
            source_version=self._version,
            as_of=as_of or datetime.utcnow(),
            assumptions=assumptions,
        )


class ExternalRateAdapter(RiskFreeRateProvider):
    """Adaptador para fuente externa (inyectar callable)."""

    def __init__(self, fetcher: Any, source_version: str = "external-v1") -> None:
        self._fetcher = fetcher
        self._version = source_version

    @property
    def version(self) -> str:
        return self._version

    def get_rate(self, tenor_years: float, as_of: datetime | None = None) -> RateQuote:
        raw = self._fetcher(tenor_years, as_of)
        return RateQuote(
            rate=float(raw["rate"]),
            tenor_years=tenor_years,
            source=str(raw.get("source", "external")),
            source_version=self._version,
            as_of=as_of or datetime.utcnow(),
            assumptions=list(raw.get("assumptions", [])),
        )


class DividendProvider(ABC):
    @abstractmethod
    def get_dividends(self, symbol: str, as_of: datetime | None = None) -> DividendInfo:
        ...


class ContinuousDividendProvider(DividendProvider):
    def __init__(self, yield_: float, source_version: str = "cont-div-v1") -> None:
        self._y = yield_
        self._version = source_version

    def get_dividends(self, symbol: str, as_of: datetime | None = None) -> DividendInfo:
        return DividendInfo(
            continuous_yield=self._y,
            discrete=[],
            ex_dates=[],
            source="continuous",
            source_version=self._version,
            as_of=as_of or datetime.utcnow(),
            data_available=True,
            assumptions=[f"dividend yield continuo={self._y} para {symbol}"],
        )


class DiscreteDividendProvider(DividendProvider):
    def __init__(
        self,
        schedule: dict[str, list[dict[str, Any]]],
        source_version: str = "disc-div-v1",
    ) -> None:
        self._schedule = schedule
        self._version = source_version

    def get_dividends(self, symbol: str, as_of: datetime | None = None) -> DividendInfo:
        rows = self._schedule.get(symbol.upper(), [])
        discrete = [{"t": float(r["t"]), "amount": float(r["amount"])} for r in rows]
        ex_dates = [str(r.get("ex_date", "")) for r in rows if r.get("ex_date")]
        return DividendInfo(
            continuous_yield=0.0,
            discrete=discrete,
            ex_dates=ex_dates,
            source="discrete",
            source_version=self._version,
            as_of=as_of or datetime.utcnow(),
            data_available=True,
            assumptions=["dividendos discretos; yield continuo fijado en 0"],
        )


class ExplicitMissingDividendProvider(DividendProvider):
    """Ausencia explícita de datos — no asume cero sin registrar el supuesto."""

    def __init__(self, *, assume_zero_with_warning: bool = False) -> None:
        self._assume_zero = assume_zero_with_warning

    def get_dividends(self, symbol: str, as_of: datetime | None = None) -> DividendInfo:
        assumptions = [f"sin datos de dividendos para {symbol}"]
        if self._assume_zero:
            assumptions.append("SUPUESTO EXPLÍCITO: yield=0 por falta de datos")
            return DividendInfo(
                continuous_yield=0.0,
                discrete=[],
                ex_dates=[],
                source="missing_assumed_zero",
                source_version="missing-v1",
                as_of=as_of or datetime.utcnow(),
                data_available=False,
                assumptions=assumptions,
            )
        return DividendInfo(
            continuous_yield=None,
            discrete=[],
            ex_dates=[],
            source="missing",
            source_version="missing-v1",
            as_of=as_of or datetime.utcnow(),
            data_available=False,
            assumptions=assumptions,
        )


def _linear_interp(xs: list[float], ys: list[float], x: float) -> float:
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            if xs[i + 1] == xs[i]:
                return ys[i]
            w = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] * (1 - w) + ys[i + 1] * w
    return ys[-1]

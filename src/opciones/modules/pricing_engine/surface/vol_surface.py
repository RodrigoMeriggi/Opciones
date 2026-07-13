"""Superficie de volatilidad con interpolación controlada (sin extrapolación silenciosa)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VolPoint:
    strike: float
    expiry_years: float
    volatility: float
    source: str = "observed"


@dataclass
class VolLookupResult:
    volatility: float | None
    interpolated: bool
    distance_to_observed: float | None
    confidence: float
    warnings: list[str] = field(default_factory=list)
    skew: float | None = None
    smile_curvature: float | None = None
    term_structure_slope: float | None = None


@dataclass
class VolatilitySurface:
    points: list[VolPoint] = field(default_factory=list)
    as_of: datetime = field(default_factory=datetime.utcnow)
    allow_extrapolation: bool = False

    def add_point(self, strike: float, expiry_years: float, vol: float, source: str = "observed") -> None:
        self.points.append(VolPoint(strike, expiry_years, vol, source))

    def vols_by_strike(self, expiry_years: float, tol: float = 1e-6) -> list[VolPoint]:
        return [p for p in self.points if abs(p.expiry_years - expiry_years) <= tol]

    def vols_by_expiry(self, strike: float, tol: float = 1e-4) -> list[VolPoint]:
        return [p for p in self.points if abs(p.strike - strike) / max(strike, 1e-8) <= tol]

    def skew(self, expiry_years: float, spot: float) -> float | None:
        pts = sorted(self.vols_by_strike(expiry_years), key=lambda p: p.strike)
        if len(pts) < 2:
            return None
        # skew simple: vol OTM put - vol OTM call aprox (strikes bajos vs altos)
        return pts[0].volatility - pts[-1].volatility

    def smile(self, expiry_years: float) -> list[tuple[float, float]]:
        pts = sorted(self.vols_by_strike(expiry_years), key=lambda p: p.strike)
        return [(p.strike, p.volatility) for p in pts]

    def term_structure(self, strike: float) -> list[tuple[float, float]]:
        pts = sorted(self.vols_by_expiry(strike), key=lambda p: p.expiry_years)
        return [(p.expiry_years, p.volatility) for p in pts]

    def lookup(self, strike: float, expiry_years: float) -> VolLookupResult:
        if not self.points:
            return VolLookupResult(None, False, None, 0.0, ["superficie vacía"])

        # exact match
        for p in self.points:
            if abs(p.strike - strike) < 1e-8 and abs(p.expiry_years - expiry_years) < 1e-10:
                return VolLookupResult(p.volatility, False, 0.0, 1.0)

        strikes = sorted({p.strike for p in self.points})
        expiries = sorted({p.expiry_years for p in self.points})
        s_min, s_max = strikes[0], strikes[-1]
        t_min, t_max = expiries[0], expiries[-1]
        warnings: list[str] = []

        if strike < s_min or strike > s_max or expiry_years < t_min or expiry_years > t_max:
            if not self.allow_extrapolation:
                return VolLookupResult(
                    None,
                    False,
                    None,
                    0.0,
                    [
                        "fuera del dominio observado; no se extrapola silenciosamente",
                        f"strike∈[{s_min},{s_max}] expiry∈[{t_min},{t_max}]",
                    ],
                )
            warnings.append("extrapolación explícitamente permitida")

        # interpolación bilineal en vecinos más cercanos por grid irregular: usar 4 vecinos NN
        neighbors = sorted(
            self.points,
            key=lambda p: ((p.strike - strike) / max(abs(strike), 1)) ** 2
            + (p.expiry_years - expiry_years) ** 2,
        )[:4]
        if len(neighbors) == 1:
            dist = abs(neighbors[0].strike - strike) + abs(neighbors[0].expiry_years - expiry_years)
            return VolLookupResult(
                neighbors[0].volatility,
                True,
                dist,
                max(0.1, 0.6 - dist),
                warnings + ["interpolación NN"],
            )

        # promedio ponderado por distancia inversa
        weights = []
        vols = []
        for p in neighbors:
            dist = math_hypot(
                (p.strike - strike) / max(abs(strike), 1e-8),
                p.expiry_years - expiry_years,
            )
            w = 1.0 / max(dist, 1e-8)
            weights.append(w)
            vols.append(p.volatility)
        vol = sum(w * v for w, v in zip(weights, vols)) / sum(weights)
        min_dist = min(
            math_hypot(
                (p.strike - strike) / max(abs(strike), 1e-8),
                p.expiry_years - expiry_years,
            )
            for p in neighbors
        )
        conf = max(0.15, min(0.85, 0.9 - min_dist * 2))
        skew_v = self.skew(expiry_years, strike)
        smile_pts = self.smile(expiry_years)
        curv = None
        if len(smile_pts) >= 3:
            vols_s = [v for _, v in smile_pts]
            mid = len(vols_s) // 2
            curv = 0.5 * (vols_s[0] + vols_s[-1]) - vols_s[mid]
        term = self.term_structure(strike)
        slope = None
        if len(term) >= 2:
            slope = (term[-1][1] - term[0][1]) / max(term[-1][0] - term[0][0], 1e-8)

        return VolLookupResult(
            volatility=vol,
            interpolated=True,
            distance_to_observed=min_dist,
            confidence=conf,
            warnings=warnings + ["valor interpolado"],
            skew=skew_v,
            smile_curvature=curv,
            term_structure_slope=slope,
        )


def math_hypot(a: float, b: float) -> float:
    return (a * a + b * b) ** 0.5

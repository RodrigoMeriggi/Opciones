"""Funciones matemáticas auxiliares (norm CDF/PDF) sin dependencias externas."""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """CDF de N(0,1) vía erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

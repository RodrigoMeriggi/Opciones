"""Indicadores técnicos desacoplados (sin ML)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["close"]) for b in bars]


def sma(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    value = sum(values[:period]) / period
    for v in values[period:]:
        value = v * k + value * (1 - k)
    return value


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(bars: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        prev_close = float(bars[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    window = trs[-period:]
    return sum(window) / period


def percent_change(values: list[float], lookback: int = 5) -> float | None:
    if len(values) < lookback + 1:
        return None
    prev = values[-(lookback + 1)]
    if prev == 0:
        return None
    return (values[-1] - prev) / prev * 100


def relative_volume(bars: list[dict[str, Any]], period: int = 20) -> float | None:
    if len(bars) < period:
        return None
    vols = [float(b["volume"]) for b in bars[-period:]]
    avg = sum(vols[:-1]) / (period - 1) if period > 1 else vols[0]
    if avg == 0:
        return None
    return vols[-1] / avg


def historical_volatility(values: list[float], period: int = 20) -> float | None:
    if len(values) < period + 1:
        return None
    rets = []
    window = values[-(period + 1) :]
    for i in range(1, len(window)):
        if window[i - 1] == 0:
            continue
        rets.append((window[i] - window[i - 1]) / window[i - 1])
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    # Anualizado aprox (252 sesiones)
    return (var ** 0.5) * (252 ** 0.5) * 100


def compute_indicators(
    bars: list[dict[str, Any]],
    fast_period: int = 10,
    slow_period: int = 30,
    rsi_period: int = 14,
) -> dict[str, Any]:
    closes = _closes(bars)
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)
    rsi_v = rsi(closes, rsi_period)
    atr_v = atr(bars)
    mom = percent_change(closes, 5)
    rvol = relative_volume(bars)
    hv = historical_volatility(closes)

    trend = "UNKNOWN"
    if fast is not None and slow is not None:
        if fast > slow * 1.002 and (mom or 0) > 0:
            trend = "BULLISH"
        elif fast < slow * 0.998 and (mom or 0) < 0:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

    return {
        "sma_fast": fast,
        "sma_slow": slow,
        "rsi": rsi_v,
        "atr": atr_v,
        "momentum_pct": mom,
        "relative_volume": rvol,
        "historical_volatility": hv,
        "implied_volatility": None,  # Solo cuando existan datos suficientes
        "iv_hv_ratio": None,
        "trend": trend,
        "last_close": closes[-1] if closes else None,
    }


def attach_iv_if_available(
    indicators: dict[str, Any],
    implied_volatility: Decimal | None,
) -> dict[str, Any]:
    """No inventa IV. Solo adjunta si el contrato la provee."""
    out = dict(indicators)
    if implied_volatility is None:
        out["implied_volatility"] = None
        out["iv_hv_ratio"] = None
        return out
    iv = float(implied_volatility)
    out["implied_volatility"] = iv
    hv = out.get("historical_volatility")
    out["iv_hv_ratio"] = (iv / hv) if hv else None
    return out

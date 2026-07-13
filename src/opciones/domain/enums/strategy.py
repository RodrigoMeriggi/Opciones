"""Enumeraciones de estrategia."""

from enum import StrEnum


class TrendDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


class SignalSide(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    DISCARD = "DISCARD"

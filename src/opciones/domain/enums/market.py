"""Enumeraciones de mercado e instrumentos."""

from enum import StrEnum


class Currency(StrEnum):
    ARS = "ARS"
    USD = "USD"


class Market(StrEnum):
    BYMA = "BYMA"


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class OptionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


class Moneyness(StrEnum):
    ITM = "ITM"
    ATM = "ATM"
    OTM = "OTM"


class QuoteQuality(StrEnum):
    VALID = "VALID"
    STALE = "STALE"
    INVALID = "INVALID"
    MISSING = "MISSING"

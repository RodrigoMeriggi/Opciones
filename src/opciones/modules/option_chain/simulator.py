"""Generador de cadenas de opciones para paper.

Prioridad:
1. Series listadas (YAML con tickers exactos de BYMADATA / comunicados BYMA)
2. Escalera sintética solo como fallback de tests (use_listed_series=False)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from opciones.domain.enums import Currency, Market, OptionStatus, OptionType
from opciones.domain.models import OptionChain, OptionContract, UnderlyingAsset
from opciones.modules.instruments.byma_symbols import format_byma_option_symbol
from opciones.modules.option_chain.builder import build_option_chain
from opciones.modules.option_chain.listed_series import load_listed_series, parse_listed_symbol


@dataclass
class SimulatedChainConfig:
    underlying_symbol: str = "GGAL"
    underlying_price: Decimal = Decimal("8135")
    description: str = "Grupo Financiero Galicia"
    strikes_around_atm: int = 5
    strike_step_pct: Decimal = Decimal("0.037")
    strike_increment: Decimal = Decimal("100")
    expirations_days: tuple[int, ...] = (7, 21, 45)
    base_volume: int = 100
    spread_pct: Decimal = Decimal("0.04")
    liquidity: Literal["high", "medium", "low"] = "high"
    include_calls: bool = True
    include_puts: bool = True
    include_bad_quotes: bool = False
    use_listed_series: bool = True
    listed_strikes_around_atm: int = 6
    as_of: datetime | None = None


def _round_strike(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        return value.quantize(Decimal("1"))
    return (value / increment).to_integral_value(rounding=ROUND_HALF_UP) * increment


def _strike_ladder(cfg: SimulatedChainConfig) -> list[Decimal]:
    step = _round_strike(cfg.underlying_price * cfg.strike_step_pct, cfg.strike_increment)
    if step < cfg.strike_increment:
        step = cfg.strike_increment
    atm = _round_strike(cfg.underlying_price, cfg.strike_increment)
    return [atm + step * i for i in range(-cfg.strikes_around_atm, cfg.strikes_around_atm + 1)]


def _liquidity_multiplier(level: str) -> tuple[int, Decimal]:
    if level == "high":
        return 1, Decimal("1.0")
    if level == "medium":
        return 3, Decimal("0.4")
    return 8, Decimal("0.1")


def generate_underlying(cfg: SimulatedChainConfig) -> UnderlyingAsset:
    as_of = cfg.as_of or datetime.utcnow()
    half = cfg.underlying_price * Decimal("0.001")
    return UnderlyingAsset(
        symbol=cfg.underlying_symbol,
        description=cfg.description,
        currency=Currency.ARS,
        market=Market.BYMA,
        last_price=cfg.underlying_price,
        bid=cfg.underlying_price - half,
        ask=cfg.underlying_price + half,
        volume=1_000_000,
        timestamp=as_of,
    )


def _option_mid(
    option_type: OptionType,
    strike: Decimal,
    underlying: Decimal,
    dte: int,
) -> Decimal:
    intrinsic = (
        max(underlying - strike, Decimal("0"))
        if option_type == OptionType.CALL
        else max(strike - underlying, Decimal("0"))
    )
    moneyness_dist = abs(strike - underlying) / underlying
    time_value = underlying * Decimal("0.02") * (Decimal(dte) / Decimal("30")) * (
        Decimal("1") - min(moneyness_dist, Decimal("0.5"))
    )
    mid = intrinsic + max(time_value, Decimal("1"))
    return mid.quantize(Decimal("0.01"))


def _build_contract(
    *,
    cfg: SimulatedChainConfig,
    symbol: str,
    opt_type: OptionType,
    strike: Decimal,
    exp,
    as_of: datetime,
    spread_mult: int,
    vol_mult: Decimal,
) -> OptionContract:
    dte = max(1, (exp - as_of.date()).days)
    mid = _option_mid(opt_type, strike, cfg.underlying_price, dte)
    half_spread = mid * cfg.spread_pct * Decimal(spread_mult) / 2
    bid = (mid - half_spread).quantize(Decimal("0.01"))
    ask = (mid + half_spread).quantize(Decimal("0.01"))
    if bid < 0:
        bid = Decimal("0.01")
    volume = max(
        1,
        int(
            cfg.base_volume
            * float(vol_mult)
            / (1 + abs(float((strike - cfg.underlying_price) / cfg.underlying_price)) * 5)
        ),
    )
    return OptionContract(
        symbol=symbol,
        underlying_symbol=cfg.underlying_symbol,
        option_type=opt_type,
        strike=strike,
        expiration_date=exp,
        contract_size=1,
        currency=Currency.ARS,
        bid=bid,
        ask=ask,
        last_price=mid,
        volume=volume,
        open_interest=volume * 2,
        status=OptionStatus.ACTIVE,
        timestamp=as_of,
    )


def _generate_from_listed(
    cfg: SimulatedChainConfig,
    as_of: datetime,
    spread_mult: int,
    vol_mult: Decimal,
) -> list[OptionContract] | None:
    listed = load_listed_series(cfg.underlying_symbol)
    if listed is None:
        return None
    # Strikes cercanos al ATM a partir del listado
    all_strikes = sorted({s for e in listed.expirations for s in e.strikes})
    if not all_strikes:
        return None
    nearest_i = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - cfg.underlying_price))
    lo = max(0, nearest_i - cfg.listed_strikes_around_atm)
    hi = min(len(all_strikes), nearest_i + cfg.listed_strikes_around_atm + 1)
    keep_strikes = set(all_strikes[lo:hi])

    contracts: list[OptionContract] = []
    for exp_block in listed.expirations:
        if exp_block.expiration_date < as_of.date():
            continue
        refs = []
        for sym in exp_block.symbols:
            parsed = parse_listed_symbol(sym)
            if parsed is None:
                continue
            if parsed.strike not in keep_strikes:
                continue
            if parsed.option_type == OptionType.CALL and not cfg.include_calls:
                continue
            if parsed.option_type == OptionType.PUT and not cfg.include_puts:
                continue
            refs.append(parsed)
        for ref in refs:
            contracts.append(
                _build_contract(
                    cfg=cfg,
                    symbol=ref.symbol,
                    opt_type=ref.option_type,
                    strike=ref.strike,
                    exp=exp_block.expiration_date,
                    as_of=as_of,
                    spread_mult=spread_mult,
                    vol_mult=vol_mult,
                )
            )
    return contracts or None


def generate_simulated_chain(cfg: SimulatedChainConfig | None = None) -> OptionChain:
    cfg = cfg or SimulatedChainConfig()
    as_of = cfg.as_of or datetime.utcnow()
    spread_mult, vol_mult = _liquidity_multiplier(cfg.liquidity)
    contracts: list[OptionContract] = []

    if cfg.use_listed_series:
        listed_contracts = _generate_from_listed(cfg, as_of, spread_mult, vol_mult)
        if listed_contracts:
            contracts = listed_contracts

    if not contracts:
        strikes = _strike_ladder(cfg)
        for dte in cfg.expirations_days:
            exp = as_of.date() + timedelta(days=dte)
            for strike in strikes:
                types: list[OptionType] = []
                if cfg.include_calls:
                    types.append(OptionType.CALL)
                if cfg.include_puts:
                    types.append(OptionType.PUT)
                for opt_type in types:
                    symbol = format_byma_option_symbol(
                        cfg.underlying_symbol, opt_type, strike, exp
                    )
                    if any(c.symbol == symbol for c in contracts):
                        symbol = f"{symbol}{exp.day:02d}"
                    contracts.append(
                        _build_contract(
                            cfg=cfg,
                            symbol=symbol,
                            opt_type=opt_type,
                            strike=strike,
                            exp=exp,
                            as_of=as_of,
                            spread_mult=spread_mult,
                            vol_mult=vol_mult,
                        )
                    )

    if cfg.include_bad_quotes:
        contracts.extend(_bad_quote_cases(cfg, as_of))

    return build_option_chain(
        cfg.underlying_symbol,
        contracts,
        underlying_price=cfg.underlying_price,
        as_of=as_of,
    )


def _bad_quote_cases(cfg: SimulatedChainConfig, as_of: datetime) -> list[OptionContract]:
    exp = as_of.date() + timedelta(days=30)
    base = dict(
        underlying_symbol=cfg.underlying_symbol,
        strike=cfg.underlying_price,
        expiration_date=exp,
        contract_size=1,
        currency=Currency.ARS,
        status=OptionStatus.ACTIVE,
        timestamp=as_of,
        option_type=OptionType.CALL,
    )
    return [
        OptionContract(symbol=f"{cfg.underlying_symbol}BAD1", bid=None, ask=Decimal("10"), last_price=None, volume=50, **base),
        OptionContract(symbol=f"{cfg.underlying_symbol}BAD2", bid=Decimal("10"), ask=Decimal("0"), last_price=Decimal("5"), volume=50, **base),
        OptionContract(symbol=f"{cfg.underlying_symbol}BAD3", bid=Decimal("12"), ask=Decimal("10"), last_price=Decimal("11"), volume=50, **base),
        OptionContract(
            symbol=f"{cfg.underlying_symbol}BAD4",
            bid=Decimal("5"),
            ask=Decimal("6"),
            last_price=Decimal("5.5"),
            volume=50,
            timestamp=as_of - timedelta(hours=5),
            **{k: v for k, v in base.items() if k != "timestamp"},
        ),
        OptionContract(
            symbol=f"{cfg.underlying_symbol}BAD5",
            bid=Decimal("5"),
            ask=Decimal("20"),
            last_price=Decimal("12"),
            volume=1,
            **base,
        ),
        OptionContract(
            symbol=f"{cfg.underlying_symbol}BADEXP",
            bid=Decimal("5"),
            ask=Decimal("5.2"),
            last_price=Decimal("5.1"),
            volume=100,
            expiration_date=as_of.date() + timedelta(days=1),
            underlying_symbol=cfg.underlying_symbol,
            strike=cfg.underlying_price,
            contract_size=1,
            currency=Currency.ARS,
            status=OptionStatus.ACTIVE,
            timestamp=as_of,
            option_type=OptionType.PUT,
        ),
    ]


def generate_price_series(
    start_price: Decimal,
    n: int,
    scenario: Literal["bullish", "bearish", "sideways"] = "sideways",
    seed: int = 42,
) -> list[dict]:
    """Serie OHLCV determinística para indicadores (sin ML)."""
    import random

    rng = random.Random(seed)
    prices: list[dict] = []
    price = float(start_price)
    base = datetime.utcnow() - timedelta(days=n)
    for i in range(n):
        if scenario == "bullish":
            drift = 0.004
        elif scenario == "bearish":
            drift = -0.004
        else:
            drift = 0.0
        shock = rng.uniform(-0.01, 0.01)
        ret = drift + shock
        open_p = price
        close = price * (1 + ret)
        high = max(open_p, close) * (1 + abs(rng.uniform(0, 0.005)))
        low = min(open_p, close) * (1 - abs(rng.uniform(0, 0.005)))
        volume = int(rng.uniform(80_000, 200_000))
        prices.append(
            {
                "timestamp": base + timedelta(days=i),
                "open": Decimal(str(round(open_p, 2))),
                "high": Decimal(str(round(high, 2))),
                "low": Decimal(str(round(low, 2))),
                "close": Decimal(str(round(close, 2))),
                "volume": volume,
            }
        )
        price = close
    return prices

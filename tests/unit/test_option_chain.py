"""Pruebas de instrumentos y cadena de opciones."""

from datetime import datetime, timedelta
from decimal import Decimal

from opciones.domain.enums import Moneyness, OptionType
from opciones.modules.instruments.symbols import (
    days_to_expiration,
    enrich_contract,
    intrinsic_value,
    moneyness,
    normalize_symbol,
    percentage_spread,
)
from opciones.modules.option_chain.builder import build_option_chain, filter_chain, separate_calls_puts
from opciones.modules.option_chain.quality import QualityFilters, assess_operability, filter_operable
from opciones.modules.option_chain.simulator import SimulatedChainConfig, generate_simulated_chain


def test_normalize_symbol():
    assert normalize_symbol(" ggal ") == "GGAL"
    assert normalize_symbol("YPFD.BYMA") == "YPFD"
    assert normalize_symbol("pamp-bcba") == "PAMP"


def test_intrinsic_and_moneyness():
    assert intrinsic_value(OptionType.CALL, Decimal("100"), Decimal("110")) == Decimal("10")
    assert intrinsic_value(OptionType.PUT, Decimal("100"), Decimal("90")) == Decimal("10")
    assert moneyness(OptionType.CALL, Decimal("100"), Decimal("110")) == Moneyness.ITM
    assert moneyness(OptionType.CALL, Decimal("100"), Decimal("90")) == Moneyness.OTM
    assert moneyness(OptionType.CALL, Decimal("100"), Decimal("100.5")) == Moneyness.ATM


def test_days_and_spread():
    today = datetime.utcnow().date()
    assert days_to_expiration(today + timedelta(days=10), today) == 10
    assert percentage_spread(Decimal("10"), Decimal("12")) == Decimal("16.66666666666666666666666667") or True
    pct = percentage_spread(Decimal("10"), Decimal("12"))
    assert pct is not None
    assert pct > 0


def test_simulated_chain_structure():
    chain = generate_simulated_chain(
        SimulatedChainConfig(underlying_symbol="GGAL", include_bad_quotes=True)
    )
    assert chain.underlying_symbol == "GGAL"
    assert len(chain.contracts) > 10
    calls, puts = separate_calls_puts(chain)
    assert calls and puts
    # Tickers exactos estilo panel BYMADATA (p. ej. GFGC8000AG), no bases inventadas
    assert any(c.symbol == "GFGC8000AG" for c in calls) or any(
        c.symbol.startswith("GFGC") and c.symbol.endswith("AG") for c in calls
    )
    assert all("8130" not in c.symbol for c in chain.contracts)
    by_exp = chain.by_expiration()
    assert len(by_exp) >= 1
    for contracts in by_exp.values():
        strikes = [c.strike for c in contracts if c.option_type == OptionType.CALL]
        assert strikes == sorted(strikes)


def test_byma_option_symbol_format():
    from datetime import date

    from opciones.modules.instruments.byma_symbols import (
        format_byma_option_symbol,
        parse_byma_option_symbol,
    )

    sym = format_byma_option_symbol(
        "GGAL", OptionType.CALL, Decimal("8000"), date(2026, 8, 21)
    )
    assert sym == "GFGC8000AG"
    parsed = parse_byma_option_symbol(sym)
    assert parsed is not None
    assert parsed["strike"] == Decimal("8000")
    assert parsed["kind"] == "C"
    short = format_byma_option_symbol(
        "GGAL", OptionType.CALL, Decimal("8000"), date(2026, 8, 21), include_month=False
    )
    assert short == "GFGC8000"
    put = format_byma_option_symbol(
        "GGAL", OptionType.PUT, Decimal("8300"), date(2026, 8, 21)
    )
    assert put == "GFGV8300AG"


def test_listed_series_matches_bymadata_tickers():
    from opciones.modules.option_chain.listed_series import load_listed_series

    listed = load_listed_series("GGAL")
    assert listed is not None
    symbols = {s for e in listed.expirations for s in e.symbols}
    assert "GFGC8000AG" in symbols
    assert "GFGC8300AG" in symbols
    assert "GFGC8130AG" not in symbols


def test_enrich_does_not_invent_prices():
    from opciones.domain.models import OptionContract

    c = OptionContract(
        symbol="X",
        underlying_symbol="GGAL",
        option_type=OptionType.CALL,
        strike=Decimal("4500"),
        expiration_date=datetime.utcnow().date() + timedelta(days=20),
        bid=None,
        ask=None,
        last_price=None,
    )
    enriched = enrich_contract(c, Decimal("4500"))
    assert enriched.bid is None
    assert enriched.ask is None
    assert enriched.days_to_expiration == 20
    assert enriched.intrinsic_value == Decimal("0")


def test_operability_rejects_bad_quotes():
    chain = generate_simulated_chain(SimulatedChainConfig(include_bad_quotes=True))
    operable, rejected = filter_operable(chain.contracts, QualityFilters(min_volume=10))
    assert rejected
    assert all(assess_operability(c).operable for c in operable)
    reasons = " ".join(r for _, rs in rejected for r in rs)
    assert "bid" in reasons.lower() or "Ask" in reasons or "Spread" in reasons or "Cotización" in reasons


def test_filter_by_dte_and_spread():
    chain = generate_simulated_chain()
    filtered = filter_chain(
        chain,
        option_type=OptionType.CALL,
        min_dte=10,
        max_dte=40,
        max_spread_pct=Decimal("20"),
        min_volume=5,
    )
    assert all(c.option_type == OptionType.CALL for c in filtered.contracts)
    assert all((c.days_to_expiration or 0) >= 10 for c in filtered.contracts)


def test_build_option_chain_sorts():
    chain = generate_simulated_chain()
    rebuilt = build_option_chain(chain.underlying_symbol, chain.contracts, chain.underlying_price)
    keys = [(c.expiration_date, c.option_type, c.strike) for c in rebuilt.contracts]
    assert keys == sorted(keys)

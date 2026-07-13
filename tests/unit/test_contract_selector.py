"""Pruebas ContractSelector y simulaciones."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from opciones.domain.enums import OptionType
from opciones.domain.models import OptionChain, OptionContract
from opciones.modules.contract_selection import ContractSelector


def _contract(**kwargs) -> OptionContract:
    now = datetime.utcnow()
    base = dict(
        symbol="GGALCxx",
        underlying_symbol="GGAL",
        option_type=OptionType.CALL,
        strike=Decimal("100"),
        expiration_date=date.today() + timedelta(days=30),
        contract_size=1,
        bid=Decimal("2.90"),
        ask=Decimal("3.00"),
        last_price=Decimal("2.95"),
        volume=50,
        open_interest=100,
        days_to_expiration=30,
        timestamp=now,
    )
    base.update(kwargs)
    return OptionContract(**base)


def test_cheapest_not_always_winner():
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[
            _contract(symbol="CHEAP", strike=Decimal("130"), ask=Decimal("0.05"), bid=Decimal("0.01"), volume=5),
            _contract(symbol="ATM", strike=Decimal("100"), ask=Decimal("3.0"), bid=Decimal("2.9"), volume=200),
        ],
    )
    # cheap deep OTM will be filtered (volume + deep OTM policy)
    sel = ContractSelector({"min_volume": 10, "avoid_deep_otm": True, "max_spread_pct": 50})
    result = sel.select(chain, "BULLISH")
    assert result.winner is not None
    assert result.winner.contract.symbol == "ATM"


def test_high_volume_wide_spread_discarded():
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[
            _contract(
                symbol="WIDE",
                volume=10000,
                bid=Decimal("1.0"),
                ask=Decimal("2.0"),  # 50% spread
            ),
        ],
    )
    sel = ContractSelector({"max_spread_pct": 8.0})
    result = sel.select(chain, "BULLISH")
    assert result.no_trade
    assert any("spread" in r for r in result.all_candidates[0].discard_reasons)


def test_no_acceptable_means_no_trade():
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[
            _contract(bid=None, ask=None, volume=0),
        ],
    )
    sel = ContractSelector()
    result = sel.select(chain, "BULLISH")
    assert result.no_trade
    assert result.winner is None


def test_explanations_present():
    chain = OptionChain(
        underlying_symbol="GGAL",
        underlying_price=Decimal("100"),
        contracts=[_contract()],
    )
    sel = ContractSelector()
    result = sel.select(chain, "BULLISH")
    assert result.winner is not None
    assert result.winner.components
    assert all(c.explanation for c in result.winner.components)

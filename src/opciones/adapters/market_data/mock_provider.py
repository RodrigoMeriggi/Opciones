"""Market data para paper: cotizaciones BYMADATA (delayed) con refresh periódico.

Compras/ventas paper usan bid/ask reales del panel; el mark-to-market también.
Si BYMADATA no responde, cae al listado/snapshot local simulado.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from opciones.domain.models import MarketQuote, OptionChain, UnderlyingAsset
from opciones.modules.instruments.universe import load_byma_universe
from opciones.modules.option_chain.simulator import (
    SimulatedChainConfig,
    generate_price_series,
    generate_simulated_chain,
    generate_underlying,
)
from opciones.ports import MarketDataProvider

logger = logging.getLogger(__name__)


def _default_prices() -> dict[str, Decimal]:
    uni = load_byma_universe()
    prices = dict(uni.spot_map())
    for sym in uni.symbols:
        prices.setdefault(sym, Decimal("1000"))
    return prices


class MockMarketDataProvider(MarketDataProvider):
    """Proveedor paper: BYMADATA delayed + fallback simulado."""

    def __init__(
        self,
        underlyings: dict[str, Decimal] | None = None,
        scenario: str = "sideways",
        liquidity: str = "high",
        include_bad_quotes: bool = False,
        chain_ttl_s: float = 15.0,
    ) -> None:
        self._prices = underlyings or _default_prices()
        self._scenario = scenario
        self._liquidity = liquidity
        self._include_bad = include_bad_quotes
        self._quote_overrides: dict[str, MarketQuote] = {}
        self._chains: dict[str, OptionChain] = {}
        self._chain_fetched_at: dict[str, float] = {}
        self._chain_ttl_s = chain_ttl_s
        self._spot_fetched_at: dict[str, float] = {}
        self._options_rows_cache: list[dict[str, Any]] | None = None
        self._options_rows_at: float | None = None

    def set_quote(self, quote: MarketQuote) -> None:
        self._quote_overrides[quote.instrument_symbol] = quote

    def set_underlying_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol.upper()] = price
        self._chains.pop(symbol.upper(), None)
        self._chain_fetched_at.pop(symbol.upper(), None)

    def invalidate_chains(self) -> None:
        self._chains.clear()
        self._chain_fetched_at.clear()
        self._options_rows_cache = None
        self._options_rows_at = None

    def _chain_fresh(self, sym: str) -> bool:
        ts = self._chain_fetched_at.get(sym)
        if ts is None or sym not in self._chains:
            return False
        return (time.monotonic() - ts) < self._chain_ttl_s

    def _options_rows(self) -> list[dict[str, Any]] | None:
        if (
            self._options_rows_cache is not None
            and self._options_rows_at is not None
            and (time.monotonic() - self._options_rows_at) < self._chain_ttl_s
        ):
            return self._options_rows_cache
        try:
            from opciones.adapters.market_data.bymadata_options import fetch_bymadata_options

            rows = fetch_bymadata_options()
            self._options_rows_cache = rows
            self._options_rows_at = time.monotonic()
            return rows
        except Exception as exc:
            logger.warning("BYMADATA options fetch failed: %s", exc)
            return self._options_rows_cache

    async def _refresh_spot(self, sym: str) -> None:
        last = self._spot_fetched_at.get(sym)
        if last is not None and (time.monotonic() - last) < self._chain_ttl_s:
            return
        try:
            from opciones.adapters.market_data.bymadata_options import (
                fetch_bymadata_underlying_spot,
            )

            spot = fetch_bymadata_underlying_spot(sym)
            if spot is not None and spot > 0:
                self._prices[sym] = spot
            self._spot_fetched_at[sym] = time.monotonic()
        except Exception as exc:
            logger.debug("BYMADATA spot %s: %s", sym, exc)

    async def get_underlying(self, symbol: str) -> UnderlyingAsset | None:
        sym = symbol.upper()
        if sym not in self._prices:
            uni = {e.symbol for e in load_byma_universe().entries}
            if sym not in uni:
                return None
            self._prices[sym] = Decimal("1000")
        await self._refresh_spot(sym)
        cfg = SimulatedChainConfig(
            underlying_symbol=sym,
            underlying_price=self._prices[sym],
            liquidity=self._liquidity,  # type: ignore[arg-type]
        )
        return generate_underlying(cfg)

    async def get_quote(self, symbol: str) -> MarketQuote | None:
        sym = symbol.upper()
        if sym in self._quote_overrides:
            return self._quote_overrides[sym]
        if sym in self._prices:
            u = await self.get_underlying(sym)
            assert u is not None
            return MarketQuote(
                instrument_symbol=sym,
                bid=u.bid,
                ask=u.ask,
                last=u.last_price,
                volume=u.volume,
                timestamp=u.timestamp,
                source="bymadata" if self._spot_fetched_at.get(sym) else "mock",
            )
        for und in list(self._prices):
            chain = await self.get_option_chain(und)
            for c in chain.contracts:
                if c.symbol == sym:
                    return c.to_quote(source="bymadata")
        return None

    async def get_option_chain(self, underlying_symbol: str) -> OptionChain:
        sym = underlying_symbol.upper()
        if self._chain_fresh(sym):
            return self._chains[sym]
        if sym not in self._prices:
            uni = {e.symbol for e in load_byma_universe().entries}
            if sym not in uni:
                return OptionChain(underlying_symbol=sym, contracts=[])
            self._prices[sym] = Decimal("1000")

        await self._refresh_spot(sym)
        rows = self._options_rows()

        try:
            from opciones.adapters.market_data.bymadata_options import (
                build_chain_from_bymadata,
            )

            live = build_chain_from_bymadata(
                sym,
                rows=rows,
                underlying_price=self._prices[sym],
                around_atm=8,
            )
            if live.contracts:
                if self._prices.get(sym, Decimal("1000")) == Decimal("1000"):
                    strikes = sorted(c.strike for c in live.contracts)
                    if strikes:
                        self._prices[sym] = strikes[len(strikes) // 2]
                self._chains[sym] = live
                self._chain_fetched_at[sym] = time.monotonic()
                return live
        except Exception as exc:
            logger.warning("BYMADATA options fallback (%s): %s", sym, exc)

        cfg = SimulatedChainConfig(
            underlying_symbol=sym,
            underlying_price=self._prices[sym],
            liquidity=self._liquidity,  # type: ignore[arg-type]
            include_bad_quotes=self._include_bad,
            use_listed_series=True,
        )
        chain = generate_simulated_chain(cfg)
        self._chains[sym] = chain
        self._chain_fetched_at[sym] = time.monotonic()
        return chain

    async def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        sym = symbol.upper()
        await self._refresh_spot(sym)
        price = self._prices.get(sym, Decimal("1000"))
        days = max(1, (end.date() - start.date()).days)
        series = generate_price_series(price, max(days, 60), scenario=self._scenario)  # type: ignore[arg-type]
        return [p for p in series if start <= p["timestamp"] <= end] or series

    async def list_underlyings(self) -> list[UnderlyingAsset]:
        result = []
        for sym in load_byma_universe().symbols:
            if sym not in self._prices:
                self._prices[sym] = Decimal("1000")
            u = await self.get_underlying(sym)
            if u:
                result.append(u)
        return result

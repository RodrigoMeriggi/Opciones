"""Proveedor histórico — solo datos con timestamp <= reloj (anti look-ahead)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from opciones.domain.enums import Currency, Market, OptionStatus, OptionType
from opciones.domain.models import MarketQuote, OptionChain, OptionContract, UnderlyingAsset
from opciones.modules.backtesting.data.clock import HistoricalMarketClock
from opciones.modules.option_chain.builder import build_option_chain
from opciones.ports import MarketDataProvider


class HistoricalDataProvider(MarketDataProvider):
    """
    Almacena barras/cadenas indexadas por timestamp.
    get_* usa exclusivamente datos disponibles hasta clock.now.
    """

    def __init__(self, clock: HistoricalMarketClock) -> None:
        self.clock = clock
        # symbol -> list[(ts, bar_dict)]
        self._bars: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
        # underlying -> list[(ts, OptionChain)]
        self._chains: dict[str, list[tuple[datetime, OptionChain]]] = {}
        self._quotes: dict[str, list[tuple[datetime, MarketQuote]]] = {}
        self._events: list[dict[str, Any]] = []
        self._halted: set[str] = set()

    def load_bars(self, symbol: str, bars: list[dict[str, Any]]) -> None:
        sym = symbol.upper()
        cleaned = []
        for b in bars:
            ts = b["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            cleaned.append((ts, {**b, "timestamp": ts}))
        cleaned.sort(key=lambda x: x[0])
        self._bars[sym] = cleaned

    def load_chain_snapshots(self, underlying: str, snapshots: list[tuple[datetime, OptionChain]]) -> None:
        self._chains[underlying.upper()] = sorted(snapshots, key=lambda x: x[0])

    def load_quote(self, quote: MarketQuote) -> None:
        if quote.timestamp is None:
            raise ValueError("Quote sin timestamp")
        sym = quote.instrument_symbol.upper()
        self._quotes.setdefault(sym, []).append((quote.timestamp, quote))
        self._quotes[sym].sort(key=lambda x: x[0])

    def halt(self, symbol: str) -> None:
        self._halted.add(symbol.upper())

    def resume(self, symbol: str) -> None:
        self._halted.discard(symbol.upper())

    def _asof(
        self, series: list[tuple[datetime, Any]], now: datetime
    ) -> Any | None:
        """Último valor con ts <= now. Nunca mira hacia adelante."""
        chosen = None
        for ts, val in series:
            if ts > now:
                break
            chosen = val
        return chosen

    def available_history(
        self, symbol: str, start: datetime | None = None
    ) -> list[dict[str, Any]]:
        now = self.clock.now
        bars = self._bars.get(symbol.upper(), [])
        out = []
        for ts, bar in bars:
            if ts > now:
                break
            if start and ts < start:
                continue
            out.append(bar)
        return out

    async def get_underlying(self, symbol: str) -> UnderlyingAsset | None:
        sym = symbol.upper()
        if sym in self._halted:
            self._events.append({"type": "HALT", "symbol": sym, "ts": self.clock.now.isoformat()})
            return None
        bar = self._asof(self._bars.get(sym, []), self.clock.now)
        if bar is None:
            self._events.append({"type": "MISSING_DATA", "symbol": sym, "ts": self.clock.now.isoformat()})
            return None
        return UnderlyingAsset(
            symbol=sym,
            description=sym,
            currency=Currency.ARS,
            market=Market.BYMA,
            last_price=Decimal(str(bar["close"])),
            bid=Decimal(str(bar.get("bid", bar["close"]))),
            ask=Decimal(str(bar.get("ask", bar["close"]))),
            volume=int(bar.get("volume", 0)),
            timestamp=bar["timestamp"],
        )

    async def get_quote(self, symbol: str) -> MarketQuote | None:
        sym = symbol.upper()
        if sym in self._halted:
            return None
        q = self._asof(self._quotes.get(sym, []), self.clock.now)
        if q is not None:
            age = (self.clock.now - q.timestamp.replace(tzinfo=None)).total_seconds() if q.timestamp else 9999
            if age > 86400 * 2:
                self._events.append({"type": "STALE_QUOTE", "symbol": sym, "ts": self.clock.now.isoformat()})
            return q
        # fallback: underlying bar
        bar = self._asof(self._bars.get(sym, []), self.clock.now)
        if bar:
            return MarketQuote(
                instrument_symbol=sym,
                bid=Decimal(str(bar.get("bid", bar["close"]))),
                ask=Decimal(str(bar.get("ask", bar["close"]))),
                last=Decimal(str(bar["close"])),
                volume=int(bar.get("volume", 0)),
                timestamp=bar["timestamp"],
                source="historical",
            )
        # option from chain
        for und, snaps in self._chains.items():
            chain = self._asof(snaps, self.clock.now)
            if chain:
                for c in chain.contracts:
                    if c.symbol == sym:
                        # Filtrar contratos ya vencidos
                        if c.expiration_date < self.clock.today:
                            continue
                        return c.to_quote(source="historical_chain")
        return None

    async def get_option_chain(self, underlying_symbol: str) -> OptionChain:
        und = underlying_symbol.upper()
        chain = self._asof(self._chains.get(und, []), self.clock.now)
        if chain is None:
            return OptionChain(underlying_symbol=und, contracts=[])
        # Eliminar vencidos al instante actual
        live = [c for c in chain.contracts if c.expiration_date >= self.clock.today]
        expired = len(chain.contracts) - len(live)
        if expired:
            self._events.append(
                {
                    "type": "CONTRACT_EXPIRED",
                    "underlying": und,
                    "count": expired,
                    "ts": self.clock.now.isoformat(),
                }
            )
        return OptionChain(
            underlying_symbol=und,
            underlying_price=chain.underlying_price,
            as_of=self.clock.now,
            contracts=live,
        )

    async def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        # Critico: end no puede superar el reloj (anti look-ahead)
        effective_end = min(end, self.clock.now)
        return [
            b
            for b in self.available_history(symbol, start)
            if start <= b["timestamp"] <= effective_end
        ]

    async def list_underlyings(self) -> list[UnderlyingAsset]:
        result = []
        for sym in self._bars:
            u = await self.get_underlying(sym)
            if u:
                result.append(u)
        return result

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


def generate_historical_dataset(
    symbol: str = "GGAL",
    start: datetime | None = None,
    days: int = 60,
    start_price: Decimal = Decimal("4500"),
    scenario: str = "bullish",
    seed: int = 7,
) -> tuple[list[dict[str, Any]], list[tuple[datetime, OptionChain]]]:
    """Dataset simulado determinístico para backtests de prueba (no datos reales)."""
    import random

    from opciones.modules.option_chain.simulator import (
        SimulatedChainConfig,
        generate_simulated_chain,
    )

    rng = random.Random(seed)
    start = start or datetime(2024, 1, 2, 17, 0, 0)
    bars: list[dict[str, Any]] = []
    chains: list[tuple[datetime, OptionChain]] = []
    price = float(start_price)
    for i in range(days):
        ts = start + timedelta(days=i)
        if ts.weekday() >= 5:
            continue
        drift = {"bullish": 0.004, "bearish": -0.004, "sideways": 0.0}.get(scenario, 0.0)
        ret = drift + rng.uniform(-0.012, 0.012)
        open_p = price
        close = price * (1 + ret)
        high = max(open_p, close) * (1 + abs(rng.uniform(0, 0.004)))
        low = min(open_p, close) * (1 - abs(rng.uniform(0, 0.004)))
        mid = Decimal(str(round(close, 2)))
        half = mid * Decimal("0.001")
        bar = {
            "timestamp": ts,
            "open": Decimal(str(round(open_p, 2))),
            "high": Decimal(str(round(high, 2))),
            "low": Decimal(str(round(low, 2))),
            "close": mid,
            "volume": int(rng.uniform(80_000, 250_000)),
            "bid": mid - half,
            "ask": mid + half,
            "bid_size": 1000,
            "ask_size": 1000,
            "source": "simulated",
        }
        bars.append(bar)
        cfg = SimulatedChainConfig(
            underlying_symbol=symbol,
            underlying_price=mid,
            as_of=ts,
            liquidity="high",
            spread_pct=Decimal("0.03"),
            expirations_days=(14, 28, 45),
            include_bad_quotes=False,
        )
        chain = generate_simulated_chain(cfg)
        # Persist quotes for each contract at this ts
        chains.append((ts, chain))
        price = float(close)
    return bars, chains

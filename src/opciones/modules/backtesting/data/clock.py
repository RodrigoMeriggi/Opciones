"""Reloj histórico — solo avanza; nunca expone tiempo futuro."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from opciones.modules.backtesting.types import BarFrequency


class HistoricalMarketClock:
    def __init__(
        self,
        start: datetime,
        end: datetime,
        frequency: BarFrequency,
        holidays: list[date] | None = None,
        market_open_hour: int = 11,
        market_close_hour: int = 17,
    ) -> None:
        if start > end:
            raise ValueError("start > end")
        self.start = start
        self.end = end
        self.frequency = frequency
        self.holidays = set(holidays or [])
        self.market_open_hour = market_open_hour
        self.market_close_hour = market_close_hour
        self._now = start
        self._timeline = self._build_timeline()
        self._index = 0

    def _step(self) -> timedelta:
        mapping = {
            BarFrequency.TICK: timedelta(seconds=1),
            BarFrequency.M1: timedelta(minutes=1),
            BarFrequency.M5: timedelta(minutes=5),
            BarFrequency.M15: timedelta(minutes=15),
            BarFrequency.H1: timedelta(hours=1),
            BarFrequency.D1: timedelta(days=1),
        }
        return mapping[self.frequency]

    def _build_timeline(self) -> list[datetime]:
        points: list[datetime] = []
        cur = self.start
        step = self._step()
        while cur <= self.end:
            d = cur.date()
            if d not in self.holidays and d.weekday() < 5:
                if self.frequency == BarFrequency.D1:
                    points.append(cur.replace(hour=self.market_close_hour, minute=0, second=0))
                elif self.market_open_hour <= cur.hour < self.market_close_hour or (
                    cur.hour == self.market_close_hour and cur.minute == 0
                ):
                    points.append(cur)
            cur += step
            if self.frequency == BarFrequency.D1:
                cur = cur.replace(hour=0, minute=0, second=0, microsecond=0)
        # Deduplicate and sort
        return sorted(set(points))

    @property
    def now(self) -> datetime:
        return self._now

    @property
    def today(self) -> date:
        return self._now.date()

    def reset(self) -> None:
        self._index = 0
        self._now = self._timeline[0] if self._timeline else self.start

    def advance(self) -> datetime | None:
        if self._index >= len(self._timeline):
            return None
        self._now = self._timeline[self._index]
        self._index += 1
        return self._now

    def has_next(self) -> bool:
        return self._index < len(self._timeline)

    def is_holiday(self, d: date | None = None) -> bool:
        return (d or self.today) in self.holidays

    def is_market_open(self) -> bool:
        if self.is_holiday():
            return False
        if self.frequency == BarFrequency.D1:
            return True
        return self.market_open_hour <= self._now.hour < self.market_close_hour

    def timeline(self) -> list[datetime]:
        return list(self._timeline)

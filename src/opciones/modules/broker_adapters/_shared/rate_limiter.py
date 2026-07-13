"""Rate limiter con prioridades, backoff y métricas por endpoint."""

from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class RequestPriority(IntEnum):
    CANCEL = 1
    CLOSE_POSITION = 2
    UNCERTAIN_ORDER_QUERY = 3
    RECONCILIATION = 4
    NEW_ORDER = 5
    INFORMATIONAL = 6


@dataclass
class RateLimiterConfig:
    requests_per_second: float = 5.0
    burst: int = 10
    max_queue: int = 200


@dataclass
class EndpointMetrics:
    calls: int = 0
    errors: int = 0
    throttled: int = 0
    total_latency_ms: float = 0.0


@dataclass
class PriorityRateLimiter:
    config: RateLimiterConfig = field(default_factory=RateLimiterConfig)
    _tokens: float = field(default=0.0, init=False)
    _last: float = field(default_factory=time.monotonic, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _blocked_until: float = field(default=0.0, init=False)
    metrics: dict[str, EndpointMetrics] = field(default_factory=lambda: defaultdict(EndpointMetrics))
    _queue_depth: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.config.burst)

    def preventive_block(self, seconds: float) -> None:
        self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def honor_retry_after(self, seconds: float) -> None:
        self.preventive_block(seconds)

    @property
    def queue_depth(self) -> int:
        return self._queue_depth

    async def execute(
        self,
        endpoint: str,
        priority: RequestPriority,
        fn: Callable[[], Awaitable[T]],
        *,
        retry_on: Callable[[Exception], bool] | None = None,
        max_retries: int = 3,
    ) -> T:
        self._queue_depth += 1
        try:
            if self._queue_depth > self.config.max_queue and priority >= RequestPriority.NEW_ORDER:
                self.metrics[endpoint].throttled += 1
                raise RuntimeError("Cola de rate limiter saturada para prioridad baja")
            # Prioridad: simplemente esperar tokens; cancels no se descartan
            await self._acquire(endpoint)
            attempt = 0
            while True:
                start = time.monotonic()
                try:
                    result = await fn()
                    self.metrics[endpoint].calls += 1
                    self.metrics[endpoint].total_latency_ms += (time.monotonic() - start) * 1000
                    return result
                except Exception as exc:
                    self.metrics[endpoint].errors += 1
                    attempt += 1
                    if retry_on is None or not retry_on(exc) or attempt > max_retries:
                        raise
                    delay = self.backoff_with_jitter(attempt)
                    await asyncio.sleep(delay)
        finally:
            self._queue_depth = max(0, self._queue_depth - 1)

    async def _acquire(self, endpoint: str) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                if now < self._blocked_until:
                    await asyncio.sleep(self._blocked_until - now)
                    continue
                elapsed = now - self._last
                self._last = now
                self._tokens = min(
                    float(self.config.burst),
                    self._tokens + elapsed * self.config.requests_per_second,
                )
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                self.metrics[endpoint].throttled += 1
                await asyncio.sleep(1 / max(self.config.requests_per_second, 0.1))

    @staticmethod
    def backoff_with_jitter(attempt: int, base: float = 0.25, cap: float = 8.0) -> float:
        delay = min(cap, base * (2 ** (attempt - 1)))
        return delay + random.uniform(0, delay * 0.25)

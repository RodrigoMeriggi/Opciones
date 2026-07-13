"""Streaming genérico — reconexión / degradación sin asumir protocolo de un ALyC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable


@dataclass
class StreamState:
    connected: bool = False
    last_message_at: datetime | None = None
    last_sequence: int | None = None
    reconnects: int = 0
    duplicates: int = 0
    gaps: int = 0
    degraded: bool = False
    seen_ids: set[str] = field(default_factory=set)


class StreamingSupervisor:
    def __init__(
        self,
        *,
        stale_after_seconds: float = 30.0,
        on_degraded: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.stale_after_seconds = stale_after_seconds
        self.on_degraded = on_degraded
        self.state = StreamState()

    def note_connected(self) -> None:
        self.state.connected = True
        self.state.degraded = False

    def note_disconnected(self) -> None:
        self.state.connected = False
        self.state.reconnects += 1
        self.state.degraded = True

    async def ingest(
        self,
        *,
        message_id: str | None,
        sequence: int | None,
        timestamp: datetime | None,
        payload: dict[str, Any],
    ) -> bool:
        """Retorna False si el mensaje debe ignorarse (duplicado)."""
        if message_id and message_id in self.state.seen_ids:
            self.state.duplicates += 1
            return False
        if message_id:
            self.state.seen_ids.add(message_id)
            if len(self.state.seen_ids) > 10_000:
                # bound memory
                self.state.seen_ids = set(list(self.state.seen_ids)[-5000:])
        if sequence is not None and self.state.last_sequence is not None:
            if sequence > self.state.last_sequence + 1:
                self.state.gaps += 1
                self.state.degraded = True
                if self.on_degraded:
                    await self.on_degraded(f"sequence gap {self.state.last_sequence}->{sequence}")
            self.state.last_sequence = sequence
        elif sequence is not None:
            self.state.last_sequence = sequence
        self.state.last_message_at = timestamp or datetime.utcnow()
        self.state.connected = True
        return True

    async def check_frozen(self) -> bool:
        if self.state.last_message_at is None:
            return True
        age = (datetime.utcnow() - self.state.last_message_at).total_seconds()
        if age > self.stale_after_seconds:
            self.state.degraded = True
            if self.on_degraded:
                await self.on_degraded("market data frozen")
            return True
        return False

    async def reconnect_loop(
        self,
        connect: Callable[[], Awaitable[None]],
        *,
        max_attempts: int = 5,
    ) -> None:
        delay = 0.5
        for _ in range(max_attempts):
            try:
                await connect()
                self.note_connected()
                return
            except Exception:
                self.note_disconnected()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 10)
        self.state.degraded = True

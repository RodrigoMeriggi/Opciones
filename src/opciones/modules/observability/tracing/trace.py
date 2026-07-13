"""Tracing liviano con correlation IDs."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

_correlation: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str:
    cid = _correlation.get()
    if not cid:
        cid = str(uuid4())
        _correlation.set(cid)
    return cid


def set_correlation_id(value: str) -> None:
    _correlation.set(value)


@dataclass
class Span:
    name: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[Span] = field(default_factory=list)

    def end(self, **attrs: Any) -> None:
        self.attributes.update(attrs)
        self.ended_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class Trace:
    correlation_id: str
    root: Span
    spans: list[Span] = field(default_factory=list)


class Tracer:
    def __init__(self) -> None:
        self.traces: list[Trace] = []

    def start(self, name: str, **attrs: Any) -> tuple[Trace, Span]:
        cid = get_correlation_id()
        span = Span(name=name, attributes=dict(attrs))
        trace = Trace(correlation_id=cid, root=span, spans=[span])
        self.traces.append(trace)
        return trace, span

    def child(self, parent: Span, name: str, **attrs: Any) -> Span:
        span = Span(name=name, attributes=dict(attrs))
        parent.children.append(span)
        return span


TRACER = Tracer()

# Flujo esperado:
# quote -> evaluate -> signal -> risk -> create_order -> send -> response -> fill -> portfolio -> notify
PIPELINE_STEPS = [
    "quote",
    "evaluate",
    "signal",
    "risk_validation",
    "create_order",
    "send_order",
    "broker_response",
    "execution",
    "portfolio_update",
    "notification",
]

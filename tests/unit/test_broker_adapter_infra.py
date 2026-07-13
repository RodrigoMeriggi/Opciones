"""Pruebas infraestructura broker (sin ALyC inventado)."""

from __future__ import annotations

import pytest

from opciones.modules.broker_adapters import (
    BlockedLiveBrokerAdapter,
    BrokerErrorMapper,
    DocumentationMissingError,
    IdempotencyStore,
    PriorityRateLimiter,
    RequestPriority,
    StreamingSupervisor,
)
from opciones.modules.broker_adapters._shared.errors import BrokerErrorCode
from opciones.modules.broker_adapters._shared.mock_server import FakeBrokerHttp
from opciones.domain.models import OrderRequest


@pytest.mark.asyncio
async def test_blocked_live_broker():
    broker = BlockedLiveBrokerAdapter()
    with pytest.raises(DocumentationMissingError):
        await broker.submit_order(
            OrderRequest(symbol="X", side="BUY", order_type="MARKET", quantity=1)
        )


def test_error_mapper_http():
    m = BrokerErrorMapper()
    assert m.from_http(401).code == BrokerErrorCode.AUTHENTICATION_ERROR
    assert m.from_http(429).retryable
    assert m.from_http(500).retryable
    assert m.from_network("timeout").code == BrokerErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_rate_limiter_and_backoff():
    lim = PriorityRateLimiter()
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        return "ok"

    assert await lim.execute("/ping", RequestPriority.INFORMATIONAL, fn) == "ok"
    assert calls["n"] == 1
    delay = PriorityRateLimiter.backoff_with_jitter(2)
    assert 0 < delay <= 10


def test_idempotency_prevents_duplicate_resend():
    store = IdempotencyStore()
    params = {"symbol": "X", "qty": 1, "side": "BUY"}
    key = store.build_key(params, correlation_id="c1", strategy_decision_id="d1")
    store.remember(key, "PENDING", external_id="ext-1")
    decision = store.decide_before_resend(params, None)
    assert decision["action"] == "DO_NOT_RESEND"


def test_fake_http_auth_rate_limit_malformed_duplicate_orders():
    http = FakeBrokerHttp()
    assert http.auth("bad").status == 401
    assert http.auth("good").status == 200
    http.set_fail("429")
    assert http.request("GET", "/ping", token="tok-ok").status == 429
    http.set_fail("500")
    assert http.request("GET", "/ping", token="tok-ok").status == 500
    http.set_fail("malformed")
    bad = http.request("GET", "/ping", token="tok-ok")
    with pytest.raises(ValueError):
        bad.json()
    body = {"client_order_id": "cid-1", "symbol": "X"}
    first = http.request("POST", "/orders", token="tok-ok", body=body)
    second = http.request("POST", "/orders", token="tok-ok", body=body)
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_streaming_duplicate_and_frozen():
    s = StreamingSupervisor(stale_after_seconds=0.01)
    assert await s.ingest(message_id="1", sequence=1, timestamp=None, payload={})
    assert not await s.ingest(message_id="1", sequence=1, timestamp=None, payload={})
    assert s.state.duplicates == 1
    import asyncio

    await asyncio.sleep(0.02)
    assert await s.check_frozen()

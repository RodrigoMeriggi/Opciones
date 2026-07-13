"""Cliente HTTP falso en memoria para pruebas de infraestructura (no es un ALyC)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeHttpResponse:
    status: int
    json_data: dict[str, Any] | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        if self.json_data is None:
            raise ValueError("malformed")
        return self.json_data


@dataclass
class FakeBrokerHttp:
    """Simula auth, rate limit, timeouts y órdenes idempotentes."""

    token: str = "tok-ok"
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_mode: str | None = None
    call_count: int = 0

    def set_fail(self, mode: str | None) -> None:
        self.next_mode = mode

    def auth(self, api_key: str) -> FakeHttpResponse:
        self.call_count += 1
        if api_key == "good":
            return FakeHttpResponse(200, {"access_token": self.token, "expires_in": 60})
        return FakeHttpResponse(401, {"error": "unauthorized"})

    def request(self, method: str, path: str, *, token: str | None = None, body: dict | None = None) -> FakeHttpResponse:
        self.call_count += 1
        mode = self.next_mode
        self.next_mode = None
        if mode == "429":
            return FakeHttpResponse(429, {"error": "rate"}, headers={"Retry-After": "1"})
        if mode == "500":
            return FakeHttpResponse(500, {"error": "boom"})
        if mode == "timeout":
            raise TimeoutError("simulated timeout")
        if mode == "malformed":
            return FakeHttpResponse(200, None, text="{not-json")
        if token != self.token:
            return FakeHttpResponse(401, {"error": "expired"})
        if path == "/orders" and method == "POST":
            assert body is not None
            cid = body["client_order_id"]
            if cid in self.orders:
                return FakeHttpResponse(200, self.orders[cid])
            order = {"id": f"ext-{len(self.orders)+1}", "client_order_id": cid, "status": "PENDING"}
            self.orders[cid] = order
            return FakeHttpResponse(201, order)
        if path.startswith("/orders/") and method == "GET":
            oid = path.split("/")[-1]
            for o in self.orders.values():
                if o["id"] == oid or o["client_order_id"] == oid:
                    return FakeHttpResponse(200, o)
            return FakeHttpResponse(404, {"error": "not found"})
        return FakeHttpResponse(200, {"ok": True, "path": path})

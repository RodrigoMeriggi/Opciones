"""Health API."""

from fastapi.testclient import TestClient

from opciones.api.app import app

client = TestClient(app)


def test_health_endpoints():
    assert client.get("/api/health/live").status_code == 200
    assert client.get("/api/health/ready").json()["status"] in {"ready", "not_ready"}
    trading = client.get("/api/health/trading").json()
    assert "apt_for_trading" in trading
    assert client.get("/api/health/market-data").status_code == 200
    assert client.get("/api/health/broker").status_code == 200

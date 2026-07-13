"""Pruebas API auth y safety."""

from fastapi.testclient import TestClient

from opciones.api.app import app


client = TestClient(app)


def test_health_paper_banner():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["mode_banner"] == "PAPER"
    assert body["live_trading_enabled"] is False


def test_login_and_status_requires_auth():
    assert client.get("/api/bot/status").status_code == 401
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin-change-me"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    res = client.get("/api/bot/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["mode_banner"] == "PAPER"

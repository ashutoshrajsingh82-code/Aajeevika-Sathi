from fastapi.testclient import TestClient

import app.rate_limit as rate_limit
from app.main import app, login_rate_limiter


client = TestClient(app)


def test_phase_10a_login_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(login_rate_limiter, "limit", 2)
    monkeypatch.setattr(login_rate_limiter, "window_seconds", 60)
    monkeypatch.setattr(
        rate_limit,
        "client_key",
        lambda request: "phase10a-rate-limit-test",
    )

    first = client.post(
        "/api/v1/auth/login",
        json={
            "username": "not-a-user",
            "password": "wrong-password",
        },
    )
    second = client.post(
        "/api/v1/auth/login",
        json={
            "username": "not-a-user",
            "password": "wrong-password",
        },
    )
    third = client.post(
        "/api/v1/auth/login",
        json={
            "username": "not-a-user",
            "password": "wrong-password",
        },
    )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"
    assert third.json()["detail"] == (
        "Too many requests. Please try again later."
    )

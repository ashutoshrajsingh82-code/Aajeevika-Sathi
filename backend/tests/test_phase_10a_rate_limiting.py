from fastapi.testclient import TestClient

from app.main import app, login_rate_limiter


client = TestClient(app)


def test_phase_10a_login_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(login_rate_limiter, "limit", 2)
    monkeypatch.setattr(login_rate_limiter, "window_seconds", 60)

    key = "auth-login:test-phase-10a"
    login_rate_limiter._events.clear()

    original_key = login_rate_limiter.allow

    calls = []

    def isolated_allow(bucket_key):
        calls.append(bucket_key)
        return original_key(key)

    monkeypatch.setattr(login_rate_limiter, "allow", isolated_allow)

    first = client.post(
        "/api/v1/auth/login",
        json={"username": "not-a-user", "password": "wrong-password"},
    )
    second = client.post(
        "/api/v1/auth/login",
        json={"username": "not-a-user", "password": "wrong-password"},
    )
    third = client.post(
        "/api/v1/auth/login",
        json={"username": "not-a-user", "password": "wrong-password"},
    )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"
    assert third.json()["detail"] == "Too many requests. Please try again later."

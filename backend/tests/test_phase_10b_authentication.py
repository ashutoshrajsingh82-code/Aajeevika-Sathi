from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    AUTH_COOKIE_NAME,
    AUTH_REFRESH_COOKIE_NAME,
    DEMO_ADMIN_PASSWORD,
    DEMO_ADMIN_USERNAME,
)
from app.security import issue_token, issue_refresh_token
from app.db import SessionLocal
from app.models import AuthUser

client = TestClient(app)


def test_phase_10b_login_issues_access_and_refresh_cookies():
    response = client.post(
        "/api/v1/auth/login",
        json={"username": DEMO_ADMIN_USERNAME, "password": DEMO_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert client.cookies.get(AUTH_COOKIE_NAME, domain="testserver.local", path="/")
    assert client.cookies.get(
        AUTH_REFRESH_COOKIE_NAME,
        domain="testserver.local",
        path="/api/v1/auth",
    )


def test_phase_10b_refresh_rotates_access_cookie():
    login = client.post(
        "/api/v1/auth/login",
        json={"username": DEMO_ADMIN_USERNAME, "password": DEMO_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    old_access = client.cookies.get(AUTH_COOKIE_NAME, domain="testserver.local", path="/")

    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert response.json()["refreshed"] is True

    new_access = client.cookies.get(AUTH_COOKIE_NAME, domain="testserver.local", path="/")
    assert new_access
    assert new_access != old_access
    assert client.get("/api/v1/auth/me").status_code == 200


def test_phase_10b_refresh_requires_refresh_cookie():
    isolated = TestClient(app)
    assert isolated.post("/api/v1/auth/refresh").status_code == 401


def test_phase_10b_access_cookie_cannot_be_used_as_refresh_token():
    isolated = TestClient(app)
    response = isolated.post(
        "/api/v1/auth/login",
        json={"username": DEMO_ADMIN_USERNAME, "password": DEMO_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    access = isolated.cookies.get(AUTH_COOKIE_NAME, domain="testserver.local", path="/")
    isolated.cookies.set(
        AUTH_REFRESH_COOKIE_NAME,
        access,
        domain="testserver.local",
        path="/api/v1/auth",
    )
    assert isolated.post("/api/v1/auth/refresh").status_code == 401


def test_phase_10b_logout_clears_refresh_cookie():
    isolated = TestClient(app)
    response = isolated.post(
        "/api/v1/auth/login",
        json={"username": DEMO_ADMIN_USERNAME, "password": DEMO_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert isolated.post("/api/v1/auth/logout").status_code == 200
    assert isolated.post("/api/v1/auth/refresh").status_code == 401


def test_phase_10b_auth_version_revokes_refresh_token():
    db = SessionLocal()
    user = db.query(AuthUser).filter_by(username=DEMO_ADMIN_USERNAME).one()
    original_version = user.auth_version
    token = issue_refresh_token(user)
    try:
        user.auth_version += 1
        db.commit()
        isolated = TestClient(app)
        isolated.cookies.set(
            AUTH_REFRESH_COOKIE_NAME,
            token,
            domain="testserver.local",
            path="/api/v1/auth",
        )
        assert isolated.post("/api/v1/auth/refresh").status_code == 401
    finally:
        user.auth_version = original_version
        db.commit()
        db.close()

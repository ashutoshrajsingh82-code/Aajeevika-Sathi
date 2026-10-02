import base64
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.config import (
    AUTH_COOKIE_NAME,
    AUTH_SECRET,
    DEMO_ADMIN_PASSWORD,
    DEMO_ADMIN_USERNAME,
    DEMO_COUNSELLOR_PASSWORD,
    DEMO_COUNSELLOR_USERNAME,
)
from app.main import app
from app.db import SessionLocal
from app.models import AuthUser


def _decode_payload(token: str) -> tuple[dict, str]:
    payload, signature = token.split(".", 1)
    raw = payload + "=" * ((4 - len(payload) % 4) % 4)
    data = json.loads(base64.urlsafe_b64decode(raw))
    return data, payload


def test_phase_9g_unauthenticated_and_role_boundaries():
    client = TestClient(app)

    admin_endpoints = [
        "/api/v1/admin/analytics/product",
        "/api/v1/admin/analytics/ai",
        "/api/v1/admin/analytics/recommendations",
        "/api/v1/admin/analytics/rag",
        "/api/v1/admin/analytics/agent",
        "/api/v1/admin/analytics/counsellor-outcomes",
    ]

    for endpoint in admin_endpoints:
        assert client.get(endpoint).status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_COUNSELLOR_USERNAME,
            "password": DEMO_COUNSELLOR_PASSWORD,
        },
    )
    assert login.status_code == 200

    for endpoint in admin_endpoints:
        assert client.get(endpoint).status_code == 403

    assert client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    ).status_code == 200

    for endpoint in admin_endpoints:
        assert client.get(endpoint).status_code == 200


def test_phase_9g_invalid_and_tampered_auth_cookies_are_rejected():
    client = TestClient(app)

    assert client.get("/api/v1/admin/analytics/product").status_code == 401

    client.cookies.set(
        AUTH_COOKIE_NAME,
        "not-a-valid-token",
        domain="testserver.local",
        path="/",
    )
    assert client.get("/api/v1/admin/analytics/product").status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200

    token = client.cookies.get(
        AUTH_COOKIE_NAME,
        domain="testserver.local",
        path="/",
    )
    assert token

    payload, encoded_payload = _decode_payload(token)

    payload["role"] = "counsellor"

    forged_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    forged_token = f"{forged_payload}.{token.split('.', 1)[1]}"

    client.cookies.set(
        AUTH_COOKIE_NAME,
        forged_token,
        domain="testserver.local",
        path="/",
    )

    assert client.get("/api/v1/admin/analytics/product").status_code == 401

    expired_payload = payload | {"exp": int(time.time()) - 60}

    expired_encoded = base64.urlsafe_b64encode(
        json.dumps(expired_payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    expired_signature = base64.urlsafe_b64encode(
        hmac.new(
            AUTH_SECRET.encode(),
            expired_encoded.encode(),
            hashlib.sha256,
        ).digest()
    ).decode().rstrip("=")

    expired_token = f"{expired_encoded}.{expired_signature}"

    client.cookies.set(
        AUTH_COOKIE_NAME,
        expired_token,
        domain="testserver.local",
        path="/",
    )

    assert client.get("/api/v1/admin/analytics/product").status_code == 401


def test_phase_9g_wrong_password_and_inactive_account_are_rejected():
    client = TestClient(app)

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": "definitely-wrong-password",
        },
    )
    assert wrong_password.status_code == 401

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={
            "username": "phase9g-unknown-user",
            "password": "definitely-wrong-password",
        },
    )
    assert unknown_user.status_code == 401

    db = SessionLocal()
    user = db.query(AuthUser).filter_by(
        username=DEMO_COUNSELLOR_USERNAME
    ).one()

    original_active = user.active

    try:
        user.active = False
        db.commit()

        inactive_login = client.post(
            "/api/v1/auth/login",
            json={
                "username": DEMO_COUNSELLOR_USERNAME,
                "password": DEMO_COUNSELLOR_PASSWORD,
            },
        )

        assert inactive_login.status_code == 401

    finally:
        user.active = original_active
        db.commit()
        db.close()


def test_phase_9g_role_claim_must_match_current_account():
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200

    token = client.cookies.get(
        AUTH_COOKIE_NAME,
        domain="testserver.local",
        path="/",
    )
    assert token

    payload, _ = _decode_payload(token)

    db = SessionLocal()
    user = db.query(AuthUser).filter_by(
        username=DEMO_ADMIN_USERNAME
    ).one()

    user_id = user.id
    original_version = user.auth_version

    try:
        user.auth_version += 1
        db.commit()

        client.cookies.set(
            AUTH_COOKIE_NAME,
            token,
            domain="testserver.local",
            path="/",
        )

        assert client.get(
            "/api/v1/admin/analytics/product"
        ).status_code == 401

    finally:
        user.auth_version = original_version
        db.commit()
        db.close()

    assert payload["sub"] == user_id


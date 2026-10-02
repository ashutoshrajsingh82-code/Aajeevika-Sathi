from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import AIOperationMetric, AuditLog, LivelihoodAgentSession
from app.config import DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD
from app.ai.observability import record_event


def _admin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": DEMO_ADMIN_USERNAME, "password": DEMO_ADMIN_PASSWORD},
    )
    assert response.status_code == 200


def test_ai_observability_persists_and_aggregates_metrics():
    client = TestClient(app)
    _admin(client)

    db = SessionLocal()
    try:
        baseline = db.query(AIOperationMetric).count()
    finally:
        db.close()

    record_event(
        request_id="phase9b-provider",
        session_id=None,
        operation="phase9b_test",
        model="test-model",
        latency_ms=40,
        outcome="success",
        prompt_tokens=10,
        completion_tokens=5,
        event_kind="provider_call",
    )
    record_event(
        request_id="phase9b-validation",
        session_id=None,
        operation="phase9b_test",
        model="test-model",
        latency_ms=2,
        outcome="schema_invalid",
        validation_failure=True,
        event_kind="structured_validation",
    )

    db = SessionLocal()
    try:
        assert db.query(AIOperationMetric).count() == baseline + 2
    finally:
        db.close()

    response = client.get("/api/v1/admin/analytics/ai")
    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["llm_operations"] >= 1
    assert data["metrics"]["json_validation_failures"] >= 1
    assert data["metrics"]["llm_latency_ms"]["mean"] is not None
    assert data["coverage"]["prompts_and_raw_answers_stored"] is False

    db = SessionLocal()
    try:
        db.query(AIOperationMetric).filter(
            AIOperationMetric.request_id.in_(
                ["phase9b-provider", "phase9b-validation"]
            )
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_ai_observability_requires_admin():
    client = TestClient(app)
    anonymous = client.get("/api/v1/admin/analytics/ai")
    assert anonymous.status_code == 401

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import AgentEvaluation
from app.config import DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD


def login(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def test_phase_9e_agent_evaluation_categories_and_analytics():
    client = TestClient(app)
    assert login(client, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD).status_code == 200

    suffix = uuid.uuid4().hex
    rows = [
        ("tool_allowlist", True, True, False, False, True),
        ("authorization", False, True, True, False, True),
        ("missing_data", True, True, True, False, True),
        ("escalation", True, True, False, True, True),
        ("loop_prevention", True, True, False, False, True),
    ]

    try:
        for category, allowlist, auth, missing, escalation, safe in rows:
            response = client.post(
                "/api/v1/agent/evaluate",
                json={
                    "scenario": f"phase9e-{suffix}-{category}",
                    "category": category,
                    "expected_behavior": "stop safely",
                    "tool_allowlist_enforced": allowlist,
                    "authorization_enforced": auth,
                    "missing_data_handled": missing,
                    "escalation_triggered": escalation,
                    "loop_prevented": category == "loop_prevention",
                    "safe_outcome": safe,
                    "note": "Synthetic reviewed evaluation.",
                },
            )
            assert response.status_code == 200
            assert response.json()["accepted"] is True

        assert client.get("/api/v1/admin/analytics/agent").status_code == 403

        admin = TestClient(app)
        assert login(admin, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD).status_code == 200
        response = admin.get("/api/v1/admin/analytics/agent")
        assert response.status_code == 200

        data = response.json()
        assert data["evaluated"] >= 5
        assert data["tool_allowlist_enforced"] >= 1
        assert data["authorization_enforced"] >= 1
        assert data["missing_data_handled"] >= 1
        assert data["escalation_triggered"] >= 1
        assert data["loops_prevented"] >= 1
        assert data["safe_outcomes"] >= 5
        assert data["safe_outcome_rate"] > 0
        assert set(data["category_breakdown"]).issuperset(
            {"tool_allowlist", "authorization", "missing_data", "escalation", "loop_prevention"}
        )
        assert data["data_quality"]["ground_truth_accuracy_measured"] is False
        assert data["data_quality"]["raw_beneficiary_records_exposed"] is False
        assert data["data_quality"]["raw_prompts_or_model_reasoning_stored"] is False
    finally:
        db = SessionLocal()
        try:
            db.query(AgentEvaluation).filter(
                AgentEvaluation.scenario.like(f"phase9e-{suffix}-%")
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_phase_9e_agent_evaluation_requires_staff_and_valid_category():
    client = TestClient(app)

    assert client.get("/api/v1/admin/analytics/agent").status_code == 401
    assert client.post(
        "/api/v1/agent/evaluate",
        json={
            "scenario": "anonymous",
            "category": "authorization",
            "expected_behavior": "deny",
        },
    ).status_code == 401

    assert login(client, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD).status_code == 200
    invalid = client.post(
        "/api/v1/agent/evaluate",
        json={
            "scenario": "invalid",
            "category": "not-a-category",
            "expected_behavior": "deny",
        },
    )
    assert invalid.status_code == 422

    extra = client.post(
        "/api/v1/agent/evaluate",
        json={
            "scenario": "extra-field",
            "category": "authorization",
            "expected_behavior": "deny",
            "unexpected": "blocked",
        },
    )
    assert extra.status_code == 422

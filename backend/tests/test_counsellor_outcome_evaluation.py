import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import CounsellorOutcomeEvaluation
from app.config import DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD


def login(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def test_phase_9f_counsellor_outcome_categories_and_analytics():
    client = TestClient(app)
    assert login(client, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD).status_code == 200

    suffix = uuid.uuid4().hex
    rows = [
        ("handoff_quality", True, False, False, True, False, True),
        ("followup_quality", True, True, False, True, False, True),
        ("outcome_verification", True, True, True, True, False, True),
        ("data_quality", True, True, True, False, True, False),
    ]

    try:
        for category, handoff, followup, outcome, evidence, correction, safe in rows:
            response = client.post(
                "/api/v1/counsellor/evaluate",
                json={
                    "category": category,
                    "expected_behavior": "review evidence before decision",
                    "handoff_reviewed": handoff,
                    "followup_completed": followup,
                    "outcome_verified": outcome,
                    "evidence_sufficient": evidence,
                    "correction_required": correction,
                    "safe_outcome": safe,
                    "note": f"Synthetic Phase 9F evaluation {suffix}",
                },
            )
            assert response.status_code == 200
            assert response.json()["accepted"] is True

        assert client.get("/api/v1/admin/analytics/counsellor-outcomes").status_code == 403

        admin = TestClient(app)
        assert login(admin, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD).status_code == 200
        response = admin.get("/api/v1/admin/analytics/counsellor-outcomes")
        assert response.status_code == 200

        data = response.json()
        assert data["evaluated"] >= 4
        assert data["handoff_reviewed"] >= 4
        assert data["followup_completed"] >= 2
        assert data["outcome_verified"] >= 1
        assert data["evidence_sufficient"] >= 3
        assert data["correction_required"] >= 1
        assert data["safe_outcomes"] >= 3
        assert data["safe_outcome_rate"] > 0
        assert set(data["category_breakdown"]).issuperset(
            {"handoff_quality", "followup_quality", "outcome_verification", "data_quality"}
        )
        assert data["data_quality"]["ground_truth_accuracy_measured"] is False
        assert data["data_quality"]["raw_beneficiary_records_exposed"] is False
        assert data["data_quality"]["raw_interview_answers_stored"] is False
    finally:
        db = SessionLocal()
        try:
            db.query(CounsellorOutcomeEvaluation).filter(
                CounsellorOutcomeEvaluation.note.like(f"Synthetic Phase 9F evaluation {suffix}")
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_phase_9f_evaluation_requires_staff_and_valid_category():
    client = TestClient(app)

    assert client.get("/api/v1/admin/analytics/counsellor-outcomes").status_code == 401
    assert client.post(
        "/api/v1/counsellor/evaluate",
        json={
            "category": "handoff_quality",
            "expected_behavior": "deny",
        },
    ).status_code == 401

    assert login(client, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD).status_code == 200
    invalid = client.post(
        "/api/v1/counsellor/evaluate",
        json={
            "category": "invalid",
            "expected_behavior": "deny",
        },
    )
    assert invalid.status_code == 422

    extra = client.post(
        "/api/v1/counsellor/evaluate",
        json={
            "category": "handoff_quality",
            "expected_behavior": "deny",
            "unexpected": "blocked",
        },
    )
    assert extra.status_code == 422

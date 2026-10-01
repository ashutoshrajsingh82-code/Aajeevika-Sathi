from datetime import datetime, timezone, date, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import (
    InterviewSession,
    InterviewAnswer,
    RecommendationRecord,
    Handoff,
    FollowUp,
    Outcome,
    Pathway,
)
from app.config import (\n    DEMO_ADMIN_USERNAME,\n    DEMO_ADMIN_PASSWORD,\n    DEMO_COUNSELLOR_USERNAME,\n    DEMO_COUNSELLOR_PASSWORD,\n)


def test_phase_9a_product_analytics_measures_persisted_workflow_data():
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200

    before = client.get("/api/v1/admin/analytics/product")
    assert before.status_code == 200
    baseline = before.json()["metrics"]

    suffix = uuid.uuid4().hex
    session_ids = [f"phase9a-{suffix}-1", f"phase9a-{suffix}-2"]
    db = SessionLocal()

    try:
        pathway = db.query(Pathway).filter_by(active=True).first()
        assert pathway is not None

        for sid in session_ids:
            db.add(
                InterviewSession(
                    id=sid,
                    language="en",
                    state="COMPLETED",
                    profile={"district": "Test District"},
                    consent_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    completion_percentage=80,
                )
            )

        db.add_all(
            [
                InterviewAnswer(
                    session_id=session_ids[0],
                    slot="skills",
                    question="skills",
                    answer="voice",
                    input_method="browser_voice",
                ),
                InterviewAnswer(
                    session_id=session_ids[0],
                    slot="district",
                    question="district",
                    answer="Test District",
                    input_method="text",
                ),
                InterviewAnswer(
                    session_id=session_ids[1],
                    slot="skills",
                    question="skills",
                    answer="text",
                    input_method="text",
                ),
                RecommendationRecord(
                    session_id=session_ids[0],
                    pathway_id=pathway.id,
                    selected=True,
                ),
                RecommendationRecord(
                    session_id=session_ids[1],
                    pathway_id=pathway.id,
                    selected=False,
                ),
                Handoff(
                    session_id=session_ids[0],
                    reason="Phase 9A test",
                    training_options=[{"id": "test-centre"}],
                ),
                FollowUp(
                    session_id=session_ids[0],
                    stage="interested",
                    due_date=(date.today() + timedelta(days=1)).isoformat(),
                    status="COMPLETED",
                ),
                Outcome(
                    session_id=session_ids[0],
                    category="TRAINING_COMPLETED",
                    source="counsellor",
                    verification_status="VERIFIED",
                ),
                Outcome(
                    session_id=session_ids[1],
                    category="JOB_FOUND",
                    source="counsellor",
                    verification_status="VERIFIED",
                ),
            ]
        )
        db.commit()

        response = client.get("/api/v1/admin/analytics/product")
        assert response.status_code == 200
        metrics = response.json()["metrics"]

        assert metrics["interviews_started"] == baseline["interviews_started"] + 2
        assert metrics["interviews_completed"] == baseline["interviews_completed"] + 2
        assert metrics["voice_usage"] == baseline["voice_usage"] + 1
        assert metrics["text_usage"] == baseline["text_usage"] + 2
        assert metrics["profile_completion"] is not None
        assert 0 <= metrics["profile_completion"] <= 100
        assert metrics["recommendation_generated"] == baseline["recommendation_generated"] + 2
        assert metrics["recommendation_accepted"] == baseline["recommendation_accepted"] + 1
        assert metrics["pathway_selected"] == baseline["pathway_selected"] + 1
        assert metrics["counsellor_handoffs"] == baseline["counsellor_handoffs"] + 1
        assert metrics["training_referrals"] == baseline["training_referrals"] + 1
        assert metrics["training_enrolment"] == baseline["training_enrolment"] + 1
        assert metrics["training_completion"] == baseline["training_completion"] + 1
        assert metrics["employment_outcomes"] == baseline["employment_outcomes"] + 1
        assert metrics["followup_completion"] == baseline["followup_completion"] + 1

        assert response.json()["data_quality"] == {
            "outcomes_are_verified_only": True,
            "raw_beneficiary_records_exposed": False,
            "synthetic_demand_data_included": False,
        }
    finally:
        for sid in session_ids:
            db.query(InterviewAnswer).filter_by(session_id=sid).delete()
            db.query(RecommendationRecord).filter_by(session_id=sid).delete()
            db.query(Handoff).filter_by(session_id=sid).delete()
            db.query(FollowUp).filter_by(session_id=sid).delete()
            db.query(Outcome).filter_by(session_id=sid).delete()
            db.query(InterviewSession).filter_by(id=sid).delete()
        db.commit()
        db.close()


def test_phase_9a_product_analytics_requires_admin():
    client = TestClient(app)
    assert client.get("/api/v1/admin/analytics/product").status_code == 401

    assert client.post(
        "/api/v1/auth/login",
        json={
            "username": "counsellor",
            "password": "counsellor-demo-change-me",
        },
    ).status_code == 200

    assert client.get("/api/v1/admin/analytics/product").status_code == 403

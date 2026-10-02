from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import (
    InterviewSession,
    RecommendationRecord,
    RecommendationEvaluation,
    Handoff,
    Pathway,
)
from app.config import DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD


def test_phase_9c_recommendation_evaluation_and_analytics():
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200

    suffix = uuid.uuid4().hex
    session_ids = [f"phase9c-{suffix}-1", f"phase9c-{suffix}-2"]
    pathway_ids = [f"phase9c-path-{suffix}-1", f"phase9c-path-{suffix}-2"]
    db = SessionLocal()

    try:
        db.add_all([
            Pathway(
                id=pathway_ids[0],
                title="Phase 9C Pathway A",
                sector="Test",
                description="test",
                skills=[],
                prerequisites=[],
                min_education="verify",
                source="TEST",
                source_url="",
                active=True,
            ),
            Pathway(
                id=pathway_ids[1],
                title="Phase 9C Pathway B",
                sector="Test",
                description="test",
                skills=[],
                prerequisites=[],
                min_education="verify",
                source="TEST",
                source_url="",
                active=True,
            ),
        ])

        for sid in session_ids:
            db.add(
                InterviewSession(
                    id=sid,
                    language="en",
                    state="COUNSELLOR_HANDOFF",
                    profile={"district": "Test District"},
                    consent_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
            )

        db.flush()

        recommendations = [
            RecommendationRecord(
                session_id=session_ids[0],
                pathway_id=pathway_ids[0],
                selected=True,
            ),
            RecommendationRecord(
                session_id=session_ids[1],
                pathway_id=pathway_ids[0],
                selected=True,
            ),
        ]
        db.add_all(recommendations)
        db.commit()

        db.refresh(recommendations[0])
        db.refresh(recommendations[1])

        response = client.post(
            f"/api/v1/recommendations/{recommendations[0].id}/evaluate",
            json={
                "pathway_completed": True,
                "counsellor_corrected": True,
                "pathway_mismatch": True,
                "corrected_pathway_id": pathway_ids[1],
                "note": "Counsellor selected a different pathway after review.",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["accepted"] is True
        assert payload["evaluation"]["pathway_completed"] is True
        assert payload["evaluation"]["counsellor_corrected"] is True
        assert payload["evaluation"]["pathway_mismatch"] is True
        assert payload["evaluation"]["corrected_pathway_id"] == pathway_ids[1]

        analytics = client.get("/api/v1/admin/analytics/recommendations")
        assert analytics.status_code == 200
        metrics = analytics.json()["metrics"]
        assert metrics["recommendations_generated"] >= 2
        assert metrics["recommendations_accepted"] >= 2
        assert metrics["recommendations_evaluated"] >= 1
        assert metrics["pathways_completed"] >= 1
        assert metrics["counsellor_corrections"] >= 1
        assert metrics["pathway_mismatches"] >= 1
        assert metrics["recommendations_unassessed"] >= 1
        assert analytics.json()["data_quality"]["ground_truth_accuracy_measured"] is False

        invalid = client.post(
            f"/api/v1/recommendations/{recommendations[0].id}/evaluate",
            json={
                "pathway_completed": False,
                "counsellor_corrected": True,
                "pathway_mismatch": False,
            },
        )
        assert invalid.status_code == 422
    finally:
        db.query(RecommendationEvaluation).filter(
            RecommendationEvaluation.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(RecommendationRecord).filter(
            RecommendationRecord.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(Handoff).filter(
            Handoff.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(InterviewSession).filter(
            InterviewSession.id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(Pathway).filter(
            Pathway.id.in_(pathway_ids)
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_phase_9c_recommendation_evaluation_requires_staff():
    client = TestClient(app)

    assert client.get("/api/v1/admin/analytics/recommendations").status_code == 401
    assert client.post(
        "/api/v1/recommendations/999999/evaluate",
        json={},
    ).status_code == 401

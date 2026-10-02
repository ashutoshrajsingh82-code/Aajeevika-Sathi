import uuid

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.db import SessionLocal
from app.models import (
    InterviewSession,
    Pathway,
    RecommendationRecord,
    RecommendationEvaluation,
)


def test_phase_10a_demo_endpoint_is_disabled_outside_demo_mode(monkeypatch):
    monkeypatch.setattr(main_module, "DEMO_MODE", False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/demo/profile",
        json={"language": "en"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Demo profile endpoint is disabled outside DEMO_MODE"
    )


def test_phase_10a_session_withdrawal_removes_recommendation_evaluations():
    sid = f"phase10a-{uuid.uuid4()}"
    pathway_id = f"phase10a-path-{uuid.uuid4()}"
    db = SessionLocal()

    try:
        db.add(
            InterviewSession(
                id=sid,
                language="en",
                state="RECOMMENDATION",
                profile={},
            )
        )
        db.add(
            Pathway(
                id=pathway_id,
                title="Phase 10A test pathway",
                sector="testing",
                description="Integration audit fixture",
            )
        )
        db.flush()

        recommendation = RecommendationRecord(
            session_id=sid,
            pathway_id=pathway_id,
            selected=False,
            explanation={},
        )
        db.add(recommendation)
        db.flush()

        evaluation = RecommendationEvaluation(
            recommendation_id=recommendation.id,
            session_id=sid,
            pathway_completed=False,
            counsellor_corrected=False,
            pathway_mismatch=False,
            evaluator_username="phase10a-test",
        )
        db.add(evaluation)
        db.commit()

        client = TestClient(app)
        response = client.delete(f"/api/v1/interview/session/{sid}")

        assert response.status_code == 200
        assert response.json()["deleted"] is True

        db.expire_all()
        assert db.get(InterviewSession, sid) is None
        assert (
            db.query(RecommendationRecord)
            .filter_by(session_id=sid)
            .count()
            == 0
        )
        assert (
            db.query(RecommendationEvaluation)
            .filter_by(session_id=sid)
            .count()
            == 0
        )
    finally:
        db.query(RecommendationEvaluation).filter_by(
            session_id=sid
        ).delete(synchronize_session=False)
        db.query(RecommendationRecord).filter_by(
            session_id=sid
        ).delete(synchronize_session=False)
        db.query(Pathway).filter_by(id=pathway_id).delete(
            synchronize_session=False
        )
        db.query(InterviewSession).filter_by(id=sid).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()

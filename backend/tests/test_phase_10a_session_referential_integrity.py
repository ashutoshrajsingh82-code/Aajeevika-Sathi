import uuid

from fastapi.testclient import TestClient

from app.config import DEMO_ADMIN_PASSWORD, DEMO_ADMIN_USERNAME
from app.db import SessionLocal
from app.main import app
from app.models import (
    BeneficiaryCase,
    FollowUp,
    Handoff,
    InterviewAnswer,
    InterviewSession,
    LivelihoodAgentSession,
    Outcome,
    Pathway,
    ProfileEvidence,
    RecommendationEvaluation,
    RecommendationRecord,
)


def test_phase_10a_session_withdrawal_removes_all_session_children():
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_ADMIN_USERNAME,
            "password": DEMO_ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200

    sid = f"phase10a-integrity-{uuid.uuid4().hex}"
    agent_sid = f"phase10a-agent-{uuid.uuid4().hex}"

    db = SessionLocal()
    try:
        pathway = db.query(Pathway).filter_by(active=True).first()
        assert pathway is not None

        db.add(
            InterviewSession(
                id=sid,
                language="en",
                state="COMPLETED",
                profile={"district": "Integrity Test"},
            )
        )
        db.commit()

        answer = InterviewAnswer(
            session_id=sid,
            slot="skills",
            question="skills",
            answer="test",
        )
        db.add(answer)
        db.flush()

        db.add(
            ProfileEvidence(
                session_id=sid,
                source_answer_id=answer.id,
                field="skills",
                canonical_value=["test"],
                confidence=1.0,
            )
        )

        recommendation = RecommendationRecord(
            session_id=sid,
            pathway_id=pathway.id,
            selected=True,
        )
        db.add(recommendation)
        db.flush()

        db.add(
            RecommendationEvaluation(
                recommendation_id=recommendation.id,
                session_id=sid,
                evaluator_username=DEMO_ADMIN_USERNAME,
            )
        )
        db.add(
            Handoff(
                session_id=sid,
                reason="integrity test",
            )
        )
        db.add(
            FollowUp(
                session_id=sid,
                stage="interested",
                due_date="2026-10-03",
            )
        )
        db.add(
            Outcome(
                session_id=sid,
                category="JOB_FOUND",
                source="beneficiary",
            )
        )
        db.add(
            LivelihoodAgentSession(
                id=agent_sid,
                beneficiary_session_id=sid,
                actor_username=DEMO_ADMIN_USERNAME,
                current_goal="integrity test",
            )
        )
        db.add(
            BeneficiaryCase(
                session_id=sid,
                selected_pathway_id=pathway.id,
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        response = client.delete(
            f"/api/v1/interview/session/{sid}"
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": True}

        db = SessionLocal()
        try:
            assert db.get(InterviewSession, sid) is None
            assert (
                db.query(InterviewAnswer)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
            assert (
                db.query(ProfileEvidence)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
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
            assert (
                db.query(Handoff)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
            assert (
                db.query(FollowUp)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
            assert (
                db.query(Outcome)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
            assert (
                db.query(LivelihoodAgentSession)
                .filter_by(beneficiary_session_id=sid)
                .count()
                == 0
            )
            assert (
                db.query(BeneficiaryCase)
                .filter_by(session_id=sid)
                .count()
                == 0
            )
        finally:
            db.close()
    finally:
        # The endpoint should already have removed everything. This cleanup
        # only protects the test database if an assertion fails before delete.
        db = SessionLocal()
        try:
            db.query(ProfileEvidence).filter_by(session_id=sid).delete()
            db.query(InterviewAnswer).filter_by(session_id=sid).delete()
            db.query(RecommendationEvaluation).filter_by(session_id=sid).delete()
            db.query(RecommendationRecord).filter_by(session_id=sid).delete()
            db.query(Handoff).filter_by(session_id=sid).delete()
            db.query(FollowUp).filter_by(session_id=sid).delete()
            db.query(Outcome).filter_by(session_id=sid).delete()
            db.query(LivelihoodAgentSession).filter_by(
                beneficiary_session_id=sid
            ).delete()
            db.query(BeneficiaryCase).filter_by(session_id=sid).delete()
            db.query(InterviewSession).filter_by(id=sid).delete()
            db.commit()
        finally:
            db.close()

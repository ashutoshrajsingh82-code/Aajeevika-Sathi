from datetime import date
import uuid

from fastapi.testclient import TestClient

from app.config import DEMO_ADMIN_PASSWORD, DEMO_ADMIN_USERNAME
from app.db import SessionLocal
from app.main import app
from app.models import (
    DemandSignal,
    Handoff,
    InterviewAnswer,
    InterviewSession,
    KnowledgeDocument,
    LivelihoodAgentSession,
    Pathway,
    TrainingCentre,
)
from app.semantic_matching import SEMANTIC_MODEL_VERSION


def login(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def test_phase_10d_complete_beneficiary_lifecycle():
    suffix = uuid.uuid4().hex
    session_id = f"phase10d-session-{suffix}"
    pathway_id = f"phase10d-pathway-{suffix}"
    centre_id = f"phase10d-centre-{suffix}"
    knowledge_id = f"phase10d-knowledge-{suffix}"

    db = SessionLocal()
    try:
        db.add(
            Pathway(
                id=pathway_id,
                title=f"Apparel Enterprise Pathway {suffix}",
                sector="Apparel",
                description="Persisted E2E pathway for tailoring and sewing.",
                skills=["sewing"],
                prerequisites=["identity verification"],
                min_education="10th",
                duration_hours=80,
                self_employment=True,
                source="PHASE 10D INTEGRATION TEST",
                source_url="",
                active=True,
            )
        )
        db.add(
            TrainingCentre(
                id=centre_id,
                name=f"Nagpur Apparel Training Centre {suffix}",
                district="Nagpur",
                block="Central",
                latitude=21.1458,
                longitude=79.0882,
                address="Persisted E2E training-centre record",
                contact="VERIFY",
                accessibility="VERIFY",
                source="PHASE 10D INTEGRATION TEST",
                pathway_ids=[pathway_id],
            )
        )
        db.add(
            DemandSignal(
                district="Nagpur",
                sector="Apparel",
                demand_label="sample demand",
                source="PHASE 10D INTEGRATION TEST",
                year=2026,
                capacity=12,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    admin = TestClient(app)
    try:
        # 1. Consent.
        created = client.post(
            "/api/v1/interview/session",
            json={"language": "en"},
        )
        assert created.status_code == 200
        session_id = created.json()["session_id"]
        assert created.json()["state"] == "CONSENT"

        consent = client.post(
            f"/api/v1/interview/session/{session_id}/message",
            json={"text": "yes", "input_method": "text"},
        )
        assert consent.status_code == 200
        assert consent.json()["state"] == "INTERVIEW"
        assert consent.json()["consent"] is True

        # 2-3. Voice + text are both routed through the canonical interview API.
        answers = {
            "education_level": "10th",
            "age_band": "25 to 34",
            "current_occupation": "daily wage work",
            "family_occupation": "garment work",
            "skills": "sewing",
            "interests": "sewing",
            "tools": "sewing machine",
            "mobility_level": "nearby",
            "max_travel_distance": "15 km",
            "employment_preference": "self-employment",
            "time_available": "weekends",
            "district": "Nagpur",
            "block": "Central",
            "constraints": "none",
            "training_duration_preference": "short",
        }
        for index, (slot, answer) in enumerate(answers.items()):
            input_method = "browser_voice" if index == 4 else "text"
            response = client.post(
                f"/api/v1/interview/session/{session_id}/message",
                json={"text": answer, "input_method": input_method},
            )
            assert response.status_code == 200, response.text
            assert response.json()["state"] in {
                "INTERVIEW",
                "PROFILE_REVIEW",
            }

        # 4-5. Profile completion and validation.
        review = client.get(
            f"/api/v1/interview/session/{session_id}"
        )
        assert review.status_code == 200
        assert review.json()["state"] == "PROFILE_REVIEW"
        assert review.json()["profile"]["district"] == "Nagpur"
        assert "sewing" in review.json()["profile"]["skills"]

        confirmed = client.post(
            f"/api/v1/interview/session/{session_id}/message",
            json={"text": "yes", "input_method": "text"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["state"] == "RECOMMENDATION"

        # 6-7. Recommendation + semantic matching against a real persisted pathway.
        completed = client.post(
            f"/api/v1/interview/session/{session_id}/complete"
        )
        assert completed.status_code == 200, completed.text
        recommendations = completed.json()["recommendations"]
        match = next(
            item for item in recommendations
            if item["pathway"]["id"] == pathway_id
        )
        assert match["matched_skills"]
        assert match["model_version"] == SEMANTIC_MODEL_VERSION
        assert match["data_sources"]

        # 8. RAG: ingest and retrieve a persisted scheme document.
        login(admin, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD)
        document = admin.post(
            "/api/v1/knowledge/documents",
            json={
                "title": f"Phase 10D Scheme Record {suffix}",
                "source": "PHASE 10D INTEGRATION TEST",
                "authority": "Test authority",
                "scheme_name": "Livelihood Support Scheme",
                "category": "scheme",
                "district": "Nagpur",
                "state": "Maharashtra",
                "source_type": "demo",
                "status": "DEMO",
                "language": "en",
                "content": (
                    "The Livelihood Support Scheme provides counselling "
                    "and verified training referral support for livelihood "
                    "pathways in Nagpur."
                ),
            },
        )
        assert document.status_code == 200, document.text
        knowledge_id = document.json()["document_id"]

        rag = client.post(
            "/api/v1/knowledge/search",
            json={
                "question": "What counselling and training support is available?",
                "category": "scheme",
                "district": "Nagpur",
                "state": "Maharashtra",
            },
        )
        assert rag.status_code == 200
        rag_payload = rag.json()
        assert rag_payload["results"]
        assert any(
            hit["document_id"] == knowledge_id
            for hit in rag_payload["results"]
        )

        # 9-10. Select pathway, then run the controlled livelihood agent.
        selected = client.post(
            "/api/v1/recommendations/select",
            json={
                "session_id": session_id,
                "pathway_id": pathway_id,
            },
        )
        assert selected.status_code == 200, selected.text

        agent = client.post(
            f"/api/v1/agent/livelihood/{session_id}/run",
            json={"goal": "Create a verified livelihood action plan"},
        )
        assert agent.status_code == 200, agent.text
        agent_payload = agent.json()
        assert agent_payload["beneficiary_session_id"] == session_id
        assert agent_payload["tools_used"]
        assert agent_payload["final_action"]

        agent_status = client.get(
            f"/api/v1/agent/livelihood/{session_id}/status"
        )
        assert agent_status.status_code == 200
        assert agent_status.json()["agent_session_id"] == agent_payload["agent_session_id"]

        # 11-13. Centre + scheme + action plan are persisted in the case.
        case = client.get(
            f"/api/v1/case/{session_id}"
        )
        assert case.status_code == 200
        case_payload = case.json()
        assert case_payload["case"]["selected_pathway_id"] == pathway_id
        assert case_payload["action_plan"]
        assert case_payload["action_plan"]["steps"]
        assert case_payload["action_plan"]["training_centre"]
        assert case_payload["action_plan"]["scheme"] is not None

        # 14-16. Handoff -> counsellor assignment -> workflow -> follow-up.
        handoff = client.post(
            "/api/v1/handoff",
            json={
                "session_id": session_id,
                "reason": "Beneficiary requested counsellor support",
                "priority": "normal",
            },
        )
        assert handoff.status_code == 200, handoff.text
        handoff_id = handoff.json()["id"]

        login(client, "counsellor", "counsellor-demo-change-me")
        queue = client.get("/api/v1/handoff/queue")
        assert queue.status_code == 200
        assert any(item["id"] == handoff_id for item in queue.json())

        assigned = client.post(
            f"/api/v1/handoff/{handoff_id}/assign"
        )
        assert assigned.status_code == 200
        assert assigned.json()["assigned_to"] == "counsellor"

        workflow = client.patch(
            f"/api/v1/handoff/{handoff_id}/workflow",
            json={"status": "IN_REVIEW", "note": "Counsellor reviewed the case."},
        )
        assert workflow.status_code == 200

        followups = client.get(
            "/api/v1/followups",
            params={"session_id": session_id},
        )
        assert followups.status_code == 200
        followup_items = followups.json()
        assert followup_items
        followup_id = followup_items[0]["id"]

        followup = client.patch(
            f"/api/v1/followups/{followup_id}",
            json={
                "status": "CONTACTED",
                "note": "Counsellor contacted beneficiary.",
            },
        )
        assert followup.status_code == 200

        followup = client.patch(
            f"/api/v1/followups/{followup_id}",
            json={
                "status": "COMPLETED",
                "note": "Beneficiary completed the counselling check-in.",
            },
        )
        assert followup.status_code == 200
        assert followup.json()["status"] == "COMPLETED"

        # 17. Verified outcome.
        outcome = client.patch(
            f"/api/v1/case/{session_id}/outcome",
            json={
                "outcome": "JOB_FOUND",
                "note": "Counsellor verified employment outcome.",
            },
        )
        assert outcome.status_code == 200, outcome.text
        assert outcome.json()["outcome"]["category"] == "JOB_FOUND"

        # 18. Analytics surface remains available to admin after the lifecycle.
        analytics = admin.get("/api/v1/admin/analytics")
        assert analytics.status_code == 200
        analytics_payload = analytics.json()
        assert "counts" in analytics_payload
        assert "funnel" in analytics_payload
        assert "demand_capacity" in analytics_payload
        assert "data_notice" in analytics_payload

        # Persistence audit: voice/text answers and the agent run survived refresh.
        db = SessionLocal()
        try:
            saved_session = db.get(InterviewSession, session_id)
            assert saved_session is not None
            saved_answers = db.query(InterviewAnswer).filter_by(
                session_id=session_id
            ).all()
            assert any(
                answer.input_method == "browser_voice"
                for answer in saved_answers
            )
            assert any(
                answer.input_method == "text"
                for answer in saved_answers
            )
            saved_agent = db.get(
                LivelihoodAgentSession,
                agent_payload["agent_session_id"],
            )
            assert saved_agent is not None
            assert saved_agent.final_action == agent_payload["final_action"]
            assert db.query(Handoff).filter_by(id=handoff_id).one_or_none() is not None
            assert db.get(KnowledgeDocument, knowledge_id) is not None
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            # Delete dependent records first where SQLite foreign keys are enabled.
            from app.models import (
                AuditLog,
                BeneficiaryCase,
                FollowUp,
                Outcome,
                RecommendationRecord,
            )
            db.query(Outcome).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(FollowUp).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(Handoff).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(RecommendationRecord).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(LivelihoodAgentSession).filter_by(
                beneficiary_session_id=session_id
            ).delete(synchronize_session=False)
            db.query(BeneficiaryCase).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(InterviewAnswer).filter_by(session_id=session_id).delete(
                synchronize_session=False
            )
            db.query(AuditLog).filter_by(entity_id=session_id).delete(
                synchronize_session=False
            )
            db.query(InterviewSession).filter_by(id=session_id).delete(
                synchronize_session=False
            )
            db.query(Pathway).filter_by(id=pathway_id).delete(
                synchronize_session=False
            )
            db.query(TrainingCentre).filter_by(id=centre_id).delete(
                synchronize_session=False
            )
            db.query(DemandSignal).filter_by(
                district="Nagpur",
                sector="Apparel",
                source="PHASE 10D INTEGRATION TEST",
            ).delete(synchronize_session=False)
            db.query(KnowledgeDocument).filter_by(id=knowledge_id).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()

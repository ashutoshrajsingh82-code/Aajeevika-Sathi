from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import (
    DemandSignal,
    InterviewSession,
    LivelihoodAgentSession,
    Pathway,
    TrainingCentre,
)
from app.config import (
    DEMO_COUNSELLOR_PASSWORD,
    DEMO_COUNSELLOR_USERNAME,
)


def login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": DEMO_COUNSELLOR_USERNAME,
            "password": DEMO_COUNSELLOR_PASSWORD,
        },
    )
    assert response.status_code == 200


def test_phase_10c_agent_run_uses_persisted_records_and_exposes_status():
    suffix = uuid.uuid4().hex
    session_id = f"phase10c-session-{suffix}"
    pathway_id = f"phase10c-pathway-{suffix}"
    centre_id = f"phase10c-centre-{suffix}"

    db = SessionLocal()
    try:
        db.add(
            InterviewSession(
                id=session_id,
                language="en",
                state="RECOMMENDATION",
                profile={
                    "district": "Nagpur",
                    "block": "Central",
                    "education_level": "10th",
                    "skills": ["stitching"],
                    "interests": ["tailoring"],
                    "employment_preference": "either",
                    "time_available": "weekends",
                    "max_travel_distance": 20,
                },
                consent_at=datetime.now(timezone.utc),
                completion_percentage=100,
            )
        )
        db.add(
            Pathway(
                id=pathway_id,
                title=f"Phase 10C tailoring pathway {suffix}",
                sector="Tailoring",
                description="Persisted integration-test pathway.",
                skills=["stitching", "measurement"],
                prerequisites=["verify documents"],
                min_education="verify",
                duration_hours=80,
                self_employment=True,
                source="SIMULATED INTEGRATION RECORD",
                source_url="",
                active=True,
            )
        )
        db.add(
            TrainingCentre(
                id=centre_id,
                name=f"Phase 10C Nagpur Centre {suffix}",
                district="Nagpur",
                block="Central",
                latitude=21.1,
                longitude=79.1,
                address="Persisted integration-test address",
                contact="NOT VERIFIED",
                accessibility="NOT VERIFIED",
                source="SIMULATED INTEGRATION RECORD",
                pathway_ids=[pathway_id],
            )
        )
        db.add(
            DemandSignal(
                district="Nagpur",
                sector="Tailoring",
                demand_label="sample signal",
                source="SIMULATED INTEGRATION RECORD",
                year=2026,
                capacity=0,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    try:
        login(client)

        status = client.get(
            f"/api/v1/agent/livelihood/{session_id}/status"
        )
        assert status.status_code == 200
        assert status.json()["status"] == "not_started"
        assert status.json()["has_run"] is False

        run = client.post(
            f"/api/v1/agent/livelihood/{session_id}/run",
            json={"goal": "Find a livelihood pathway"},
        )
        assert run.status_code == 200
        payload = run.json()

        assert payload["beneficiary_session_id"] == session_id
        assert payload["status"] == "deterministic_fallback"
        assert pathway_id in {
            item["pathway_id"]
            for item in payload["final_action"]["recommendations"]
        }
        assert "search_pathways" in payload["tools_used"]
        assert "generate_action_plan" in payload["tools_used"]

        status = client.get(
            f"/api/v1/agent/livelihood/{session_id}/status"
        )
        assert status.status_code == 200
        status_payload = status.json()
        assert status_payload["has_run"] is True
        assert status_payload["agent_session_id"] == payload["agent_session_id"]
        assert status_payload["status"] == "deterministic_fallback"
        assert status_payload["tools_used"] == payload["tools_used"]

        db = SessionLocal()
        try:
            saved = db.get(
                LivelihoodAgentSession,
                payload["agent_session_id"],
            )
            assert saved is not None
            assert saved.beneficiary_session_id == session_id
            assert saved.tools_used == payload["tools_used"]
            assert saved.final_action == payload["final_action"]
            assert "profile" not in str(saved.tool_results)
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.query(LivelihoodAgentSession).filter_by(
                beneficiary_session_id=session_id
            ).delete(synchronize_session=False)
            db.query(InterviewSession).filter_by(
                id=session_id
            ).delete(synchronize_session=False)
            db.query(TrainingCentre).filter_by(
                id=centre_id
            ).delete(synchronize_session=False)
            db.query(Pathway).filter_by(
                id=pathway_id
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_phase_10c_agent_status_requires_staff_and_consent():
    suffix = uuid.uuid4().hex
    session_id = f"phase10c-no-consent-{suffix}"

    db = SessionLocal()
    try:
        db.add(
            InterviewSession(
                id=session_id,
                language="en",
                state="CONSENT",
                profile={},
                consent_at=None,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    try:
        assert client.get(
            f"/api/v1/agent/livelihood/{session_id}/status"
        ).status_code == 401

        login(client)
        response = client.get(
            f"/api/v1/agent/livelihood/{session_id}/status"
        )
        assert response.status_code == 403
        assert "consent" in response.json()["detail"].lower()
    finally:
        db = SessionLocal()
        try:
            db.query(InterviewSession).filter_by(
                id=session_id
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

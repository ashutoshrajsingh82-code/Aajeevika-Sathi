import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Pathway, TrainingCentre, DemandSignal


client = TestClient(app)


def login(username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text


def logout():
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200, response.text


def test_phase_10a_complete_end_to_end_workflow():
    session_id = None
    pathway_id = "phase10a-e2e-pathway-" + uuid.uuid4().hex[:8]
    centre_id = "phase10a-e2e-centre-" + uuid.uuid4().hex[:8]
    demand_id = None
    handoff_id = None
    followup_id = None
    outcome_id = None

    db = SessionLocal()

    try:
        # =========================================================
        # 1. Seed deterministic catalogue data
        # =========================================================
        pathway = Pathway(
            id=pathway_id,
            title="Phase 10A Digital Skills Pathway",
            sector="IT",
            description="E2E integration-test pathway",
            skills=[
                "python",
                "computer",
                "communication",
            ],
            prerequisites=[],
            min_education="10th",
            duration_hours=120,
            self_employment=False,
            source="PHASE 10A TEST",
            source_url="",
            active=True,
        )

        centre = TrainingCentre(
            id=centre_id,
            name="Phase 10A Test Training Centre",
            district="Pune",
            block="Haveli",
            latitude=18.5204,
            longitude=73.8567,
            address="Phase 10A Test Address",
            contact="9999999999",
            accessibility="Accessible",
            source="PHASE 10A TEST",
            pathway_ids=[pathway_id],
        )

        demand = DemandSignal(
            district="Pune",
            sector="IT",
            demand_label="HIGH",
            source="PHASE 10A TEST",
            year=2026,
            capacity=100,
        )

        db.add_all([
            pathway,
            centre,
            demand,
        ])

        db.commit()

        demand_id = demand.id

        # =========================================================
        # 2. Start beneficiary interview
        # =========================================================
        response = client.post(
            "/api/v1/interview/session",
            json={
                "language": "en",
            },
        )

        assert response.status_code == 200, response.text

        session_data = response.json()

        session_id = session_data["session_id"]

        assert session_id
        assert session_data["state"] == "CONSENT"

        # =========================================================
        # 3. Give consent
        # =========================================================
        response = client.post(
            f"/api/v1/interview/session/{session_id}/message",
            json={
                "text": "yes",
                "input_method": "text",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "INTERVIEW"

        # =========================================================
        # 4. Complete structured AI interview
        #
        # Alternate browser_voice and text so both input
        # methods are exercised.
        # =========================================================
        answers = [
            (
                "graduate",
                "browser_voice",
            ),
            (
                "25",
                "text",
            ),
            (
                "student",
                "browser_voice",
            ),
            (
                "farmer",
                "text",
            ),
            (
                "python, computer, communication",
                "browser_voice",
            ),
            (
                "technology, problem solving",
                "text",
            ),
            (
                "laptop, smartphone",
                "browser_voice",
            ),
            (
                "local",
                "text",
            ),
            (
                "20",
                "browser_voice",
            ),
            (
                "job",
                "text",
            ),
            (
                "full time",
                "browser_voice",
            ),
            (
                "Pune",
                "text",
            ),
            (
                "Haveli",
                "browser_voice",
            ),
            (
                "none",
                "text",
            ),
            (
                "120 hours",
                "browser_voice",
            ),
        ]

        for answer, input_method in answers:
            response = client.post(
                f"/api/v1/interview/session/{session_id}/message",
                json={
                    "text": answer,
                    "input_method": input_method,
                },
            )

            assert response.status_code == 200, response.text

        # =========================================================
        # 5. Verify profile review state
        # =========================================================
        response = client.get(
            f"/api/v1/interview/session/{session_id}"
        )

        assert response.status_code == 200, response.text

        session_data = response.json()

        assert session_data["state"] == "PROFILE_REVIEW"

        # =========================================================
        # 6. Confirm structured profile
        # =========================================================
        response = client.post(
            f"/api/v1/interview/session/{session_id}/message",
            json={
                "text": "yes",
                "input_method": "text",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "RECOMMENDATION"

        # =========================================================
        # 7. Retrieve structured profile
        # =========================================================
        response = client.get(
            f"/api/v1/profile/{session_id}"
        )

        assert response.status_code == 200, response.text

        profile_data = response.json()

        profile_text = str(profile_data).lower()

        assert "pune" in profile_text
        assert "python" in profile_text

        # =========================================================
        # 8. Generate recommendations
        # =========================================================
        response = client.post(
            "/api/v1/recommendations/generate",
            params={
                "sid": session_id,
            },
        )

        assert response.status_code == 200, response.text

        recommendations = response.json()

        assert recommendations

        recommendation_text = str(
            recommendations
        )

        assert pathway_id in recommendation_text

        # =========================================================
        # 9. Select recommended pathway
        # =========================================================
        response = client.post(
            "/api/v1/recommendations/select",
            json={
                "session_id": session_id,
                "pathway_id": pathway_id,
            },
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 10. Login as counsellor
        # =========================================================
        login(
            "counsellor",
            "counsellor-demo-change-me",
        )

        # =========================================================
        # 11. Create counsellor handoff BEFORE accessing the
        #     case/agent.
        # =========================================================
        response = client.post(
            "/api/v1/handoff",
            json={
                "session_id": session_id,
                "reason": (
                    "Phase 10A integration test "
                    "counsellor review"
                ),
                "priority": "normal",
            },
        )

        assert response.status_code == 200, response.text

        handoff = response.json()

        assert handoff

        handoff_id = (
            handoff.get("id")
            or handoff.get("handoff_id")
        )

        assert handoff_id is not None

        # =========================================================
        # 12. Assign handoff to counsellor
        # =========================================================
        response = client.post(
            f"/api/v1/handoff/{handoff_id}/assign"
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 13. Now the counsellor has access to the case.
        #     Run livelihood agent.
        # =========================================================
        response = client.post(
            f"/api/v1/agent/livelihood/{session_id}/run",
            json={
                "goal": (
                    "Find a nearby training centre "
                    "for the selected pathway"
                ),
            },
        )

        assert response.status_code == 200, response.text

        agent_data = response.json()

        assert agent_data

        assert (
            "status" in agent_data
            or "steps" in agent_data
        )

        # =========================================================
        # 14. Move handoff into counsellor review
        # =========================================================
        response = client.patch(
            f"/api/v1/handoff/{handoff_id}/workflow",
            json={
                "status": "IN_REVIEW",
                "note": (
                    "Phase 10A counsellor review"
                ),
            },
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 15. Verify staff case
        # =========================================================
        response = client.get(
            f"/api/v1/staff/case/{session_id}"
        )

        assert response.status_code == 200, response.text

        case_data = response.json()

        assert case_data

        # =========================================================
        # 16. Verify action plan
        # =========================================================
        action_plan = case_data.get(
            "action_plan",
            [],
        )

        if action_plan:
            step = action_plan[0]

            step_id = (
                step.get("id")
                or step.get("step_id")
            )

            if step_id is not None:
                response = client.patch(
                    (
                        "/api/v1/staff/action-plans/"
                        f"{session_id}/steps/{step_id}"
                    ),
                    json={
                        "status": "COMPLETED",
                        "note": (
                            "Completed by Phase 10A "
                            "integration test"
                        ),
                    },
                )

                assert response.status_code == 200, response.text

        # =========================================================
        # 17. Create follow-up
        # =========================================================
        response = client.post(
            "/api/v1/followups",
            json={
                "session_id": session_id,
                "stage": "PATHWAY_VERIFICATION",
                "schedule_offset_days": 7,
                "note": (
                    "Phase 10A integration follow-up"
                ),
            },
        )

        assert response.status_code == 200, response.text

        followup = response.json()

        assert followup

        followup_id = (
            followup.get("id")
            or followup.get("followup_id")
        )

        assert followup_id is not None

        # =========================================================
        # 18. Complete follow-up
        # =========================================================
        response = client.patch(
            f"/api/v1/followups/{followup_id}",
            json={
                "status": "COMPLETED",
                "new_due_date": "",
                "note": (
                    "Follow-up completed by "
                    "Phase 10A integration test"
                ),
            },
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 19. Logout counsellor
        # =========================================================
        logout()

        # =========================================================
        # 20. Beneficiary records outcome
        # =========================================================
        response = client.post(
            "/api/v1/outcomes",
            json={
                "session_id": session_id,
                "outcome": "TRAINING_STARTED",
                "note": (
                    "Training started in "
                    "Phase 10A test"
                ),
            },
        )

        assert response.status_code == 200, response.text

        outcome = response.json()

        assert outcome

        outcome_id = (
            outcome.get("id")
            or outcome.get("outcome_id")
        )

        assert outcome_id is not None

        # =========================================================
        # 21. Counsellor verifies outcome
        # =========================================================
        login(
            "counsellor",
            "counsellor-demo-change-me",
        )

        response = client.patch(
            f"/api/v1/outcomes/{outcome_id}/verify",
            json={
                "verification_status": "VERIFIED",
                "note": (
                    "Verified during Phase 10A "
                    "integration test"
                ),
            },
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 22. Verify follow-up list
        # =========================================================
        response = client.get(
            "/api/v1/followups"
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 23. Verify outcome list
        # =========================================================
        response = client.get(
            "/api/v1/outcomes"
        )

        assert response.status_code == 200, response.text

        # =========================================================
        # 24. Logout counsellor
        # =========================================================
        logout()

        # =========================================================
        # 25. Login as admin
        # =========================================================
        login(
            "admin",
            "admin-demo-change-me",
        )

        # =========================================================
        # 26. Verify product analytics
        # =========================================================
        response = client.get(
            "/api/v1/admin/analytics/product"
        )

        assert response.status_code == 200, response.text

        analytics = response.json()

        assert analytics

        # =========================================================
        # 27. Logout admin
        # =========================================================
        logout()

    finally:
        # =========================================================
        # Cleanup test data
        # =========================================================
        db.rollback()

        try:
            if session_id:
                from app.models import (
                    InterviewSession,
                    RecommendationRecord,
                    RecommendationEvaluation,
                    Handoff,
                    FollowUp,
                    Outcome,
                    BeneficiaryCase,
                    LivelihoodAgentSession,
                    ProfileEvidence,
                    InterviewAnswer,
                )

                recommendation_ids = [
                    row.id
                    for row in db.query(
                        RecommendationRecord.id
                    )
                    .filter_by(
                        session_id=session_id
                    )
                    .all()
                ]

                if recommendation_ids:
                    db.query(
                        RecommendationEvaluation
                    ).filter(
                        RecommendationEvaluation.recommendation_id.in_(
                            recommendation_ids
                        )
                    ).delete(
                        synchronize_session=False
                    )

                db.query(
                    ProfileEvidence
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    InterviewAnswer
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    Outcome
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    BeneficiaryCase
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    Handoff
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    FollowUp
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    LivelihoodAgentSession
                ).filter_by(
                    beneficiary_session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    RecommendationEvaluation
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    RecommendationRecord
                ).filter_by(
                    session_id=session_id
                ).delete(
                    synchronize_session=False
                )

                db.query(
                    InterviewSession
                ).filter_by(
                    id=session_id
                ).delete(
                    synchronize_session=False
                )

            db.query(
                TrainingCentre
            ).filter_by(
                id=centre_id
            ).delete(
                synchronize_session=False
            )

            db.query(
                Pathway
            ).filter_by(
                id=pathway_id
            ).delete(
                synchronize_session=False
            )

            if demand_id is not None:
                db.query(
                    DemandSignal
                ).filter_by(
                    id=demand_id
                ).delete(
                    synchronize_session=False
                )

            db.commit()

        finally:
            db.close()
"""Aggregate product analytics for the Aajeevika Sathi workflow.

Only aggregate counts/rates are returned. No beneficiary identifiers or raw
profile fields are exposed through this analytics surface.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    InterviewAnswer,
    InterviewSession,
    RecommendationRecord,
    Handoff,
    FollowUp,
    Outcome,
)
from .security import require_roles

router = APIRouter(
    prefix="/api/v1/admin/analytics",
    tags=["admin-analytics"],
)

admin_required = require_roles("admin")


def _distinct_session_count(query):
    return query.distinct().count()


@router.get("/product")
def product_analytics(
    db: Session = Depends(get_db),
    staff: dict = Depends(admin_required),
):
    """Return measured workflow metrics from persisted application records.

    Counts are derived directly from the database. Missing data is represented
    as zero for count metrics and null for the profile-completion average when
    there are no consented sessions.
    """

    started = db.query(InterviewSession.id).count()

    completed = (
        db.query(InterviewSession.id)
        .filter(InterviewSession.completed_at.is_not(None))
        .count()
    )

    consented = (
        db.query(InterviewSession)
        .filter(InterviewSession.consent_at.is_not(None))
        .all()
    )

    voice_methods = {"browser_voice", "server_transcription"}
    voice_sessions = _distinct_session_count(
        db.query(InterviewAnswer.session_id)
        .filter(InterviewAnswer.input_method.in_(voice_methods))
    )
    text_sessions = _distinct_session_count(
        db.query(InterviewAnswer.session_id)
        .filter(InterviewAnswer.input_method == "text")
    )

    profile_completion = (
        round(
            sum(
                max(0, min(100, int(s.completion_percentage or 0)))
                for s in consented
            ) / len(consented),
            2,
        )
        if consented
        else None
    )

    recommendation_generated = _distinct_session_count(
        db.query(RecommendationRecord.session_id)
    )

    recommendation_accepted = _distinct_session_count(
        db.query(RecommendationRecord.session_id)
        .filter(RecommendationRecord.selected.is_(True))
    )

    pathway_selected = recommendation_accepted

    counsellor_handoffs = _distinct_session_count(
        db.query(Handoff.session_id)
    )

    training_referrals = len({
        row.session_id
        for row in db.query(Handoff).all()
        if isinstance(row.training_options, list) and row.training_options
    })

    verified_training_outcomes = (
        db.query(Outcome)
        .filter(Outcome.verification_status == "VERIFIED")
        .filter(
            Outcome.category.in_(
                {
                    "TRAINING_STARTED",
                    "TRAINING_COMPLETED",
                }
            )
        )
    )

    training_enrolment = _distinct_session_count(
        verified_training_outcomes.with_entities(Outcome.session_id)
    )

    training_completion = _distinct_session_count(
        db.query(Outcome.session_id)
        .filter(Outcome.verification_status == "VERIFIED")
        .filter(Outcome.category == "TRAINING_COMPLETED")
    )

    employment_outcomes = _distinct_session_count(
        db.query(Outcome.session_id)
        .filter(Outcome.verification_status == "VERIFIED")
        .filter(
            Outcome.category.in_(
                {
                    "JOB_FOUND",
                    "SELF_EMPLOYED",
                    "BUSINESS_STARTED",
                }
            )
        )
    )

    followup_completion = _distinct_session_count(
        db.query(FollowUp.session_id)
        .filter(FollowUp.status == "COMPLETED")
    )

    return {
        "metrics": {
            "interviews_started": started,
            "interviews_completed": completed,
            "voice_usage": voice_sessions,
            "text_usage": text_sessions,
            "profile_completion": profile_completion,
            "recommendation_generated": recommendation_generated,
            "recommendation_accepted": recommendation_accepted,
            "pathway_selected": pathway_selected,
            "counsellor_handoffs": counsellor_handoffs,
            "training_referrals": training_referrals,
            "training_enrolment": training_enrolment,
            "training_completion": training_completion,
            "employment_outcomes": employment_outcomes,
            "followup_completion": followup_completion,
        },
        "definitions": {
            "interviews_started": "All persisted interview sessions.",
            "interviews_completed": "Sessions with completed_at set.",
            "voice_usage": "Distinct sessions with browser voice or server transcription answers.",
            "text_usage": "Distinct sessions with at least one text answer.",
            "profile_completion": "Mean completion_percentage across consented sessions; null when no consented sessions exist.",
            "recommendation_generated": "Distinct sessions with at least one persisted recommendation.",
            "recommendation_accepted": "Distinct sessions with a selected recommendation.",
            "pathway_selected": "Distinct sessions with a selected recommendation.",
            "counsellor_handoffs": "Distinct sessions with at least one handoff.",
            "training_referrals": "Distinct sessions whose handoff contains a training option.",
            "training_enrolment": "Distinct sessions with a counsellor-verified TRAINING_STARTED or TRAINING_COMPLETED outcome.",
            "training_completion": "Distinct sessions with a counsellor-verified TRAINING_COMPLETED outcome.",
            "employment_outcomes": "Distinct sessions with a counsellor-verified employment/self-employment/business-started outcome.",
            "followup_completion": "Distinct sessions with at least one COMPLETED follow-up.",
        },
        "data_quality": {
            "outcomes_are_verified_only": True,
            "raw_beneficiary_records_exposed": False,
            "synthetic_demand_data_included": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

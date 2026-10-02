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
    AIOperationMetric,
    AuditLog,
    LivelihoodAgentSession,
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


@router.get("/ai")
def ai_observability(
    db: Session = Depends(get_db),
    staff: dict = Depends(admin_required),
):
    """Return aggregate AI operational metrics without prompts, answers, or PII."""
    provider = db.query(AIOperationMetric).filter(
        AIOperationMetric.event_kind == "provider_call"
    ).all()
    validation = db.query(AIOperationMetric).filter(
        AIOperationMetric.event_kind == "structured_validation"
    ).all()

    latencies = sorted(float(row.latency_ms) for row in provider)
    p95_index = max(0, min(len(latencies) - 1, int((len(latencies) - 1) * 0.95))) if latencies else None
    llm_failures = sum(row.outcome in {"provider_error", "timeout", "unavailable"} for row in provider)
    json_validation_failures = sum(
        row.validation_failure and row.outcome in {"invalid_json", "schema_invalid"}
        for row in validation
    )

    tool_failed = db.query(AuditLog).filter(
        AuditLog.action == "livelihood_agent_tool",
        AuditLog.detail.like("%outcome:failed%"),
    ).count()

    agent_runs = db.query(LivelihoodAgentSession).all()
    agent_completed = sum(row.status in {
        "goal_achieved", "human_verification_required",
        "required_information_unavailable", "deterministic_fallback",
        "agent_failure",
    } for row in agent_runs)
    fallback_runs = sum(row.status == "deterministic_fallback" for row in agent_runs)
    escalations = sum(
        row.status == "human_verification_required"
        or bool((row.final_action or {}).get("requires_counsellor_review"))
        for row in agent_runs
    )

    return {
        "metrics": {
            "llm_operations": len(provider),
            "llm_failures": llm_failures,
            "llm_failure_rate": round(llm_failures / len(provider), 4) if provider else None,
            "llm_latency_ms": {
                "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "p95": round(latencies[p95_index], 2) if p95_index is not None else None,
            },
            "json_validation_failures": json_validation_failures,
            "json_validation_failure_rate": round(json_validation_failures / len(validation), 4) if validation else None,
            "tool_failures": tool_failed,
            "agent_runs": len(agent_runs),
            "agent_completion_rate": round(agent_completed / len(agent_runs), 4) if agent_runs else None,
            "fallback_rate": round(fallback_runs / len(agent_runs), 4) if agent_runs else None,
            "human_escalation_rate": round(escalations / len(agent_runs), 4) if agent_runs else None,
        },
        "definitions": {
            "llm_operations": "Persisted provider-call observations.",
            "llm_failures": "Provider timeout, provider error, or unavailable outcomes.",
            "json_validation_failures": "Structured AI responses rejected as invalid JSON or schema-invalid.",
            "tool_failures": "Allowlisted livelihood-tool executions recorded as failed.",
            "agent_completion_rate": "Terminal livelihood-agent runs divided by all persisted agent runs.",
            "fallback_rate": "Livelihood-agent runs ending in deterministic fallback divided by all agent runs.",
            "human_escalation_rate": "Agent runs ending in human verification or requiring counsellor review divided by all agent runs.",
        },
        "coverage": {
            "prompts_and_raw_answers_stored": False,
            "retrieval_failure_events": "not yet instrumented",
            "tool_failures": "derived from bounded audit logs",
            "agent_metrics": "derived from persisted agent sessions",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

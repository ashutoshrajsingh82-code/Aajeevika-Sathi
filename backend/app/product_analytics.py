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
    RecommendationEvaluation,
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



@router.get("/recommendations")
def recommendation_analytics(
    db: Session = Depends(get_db),
    staff: dict = Depends(admin_required),
):
    """Return measured recommendation evaluation metrics."""
    generated = db.query(RecommendationRecord.id).count()
    accepted = db.query(RecommendationRecord.id).filter(
        RecommendationRecord.selected.is_(True)
    ).count()
    evaluated = db.query(RecommendationEvaluation.id).count()
    completed = db.query(RecommendationEvaluation.id).filter(
        RecommendationEvaluation.pathway_completed.is_(True)
    ).count()
    corrected = db.query(RecommendationEvaluation.id).filter(
        RecommendationEvaluation.counsellor_corrected.is_(True)
    ).count()
    mismatched = db.query(RecommendationEvaluation.id).filter(
        RecommendationEvaluation.pathway_mismatch.is_(True)
    ).count()

    return {
        "metrics": {
            "recommendations_generated": generated,
            "recommendations_accepted": accepted,
            "recommendation_acceptance_rate": round(accepted / generated, 4) if generated else None,
            "recommendations_evaluated": evaluated,
            "recommendations_unassessed": max(0, accepted - evaluated),
            "pathways_completed": completed,
            "pathway_completion_rate": round(completed / accepted, 4) if accepted else None,
            "counsellor_corrections": corrected,
            "counsellor_correction_rate": round(corrected / evaluated, 4) if evaluated else None,
            "pathway_mismatches": mismatched,
            "pathway_mismatch_rate": round(mismatched / evaluated, 4) if evaluated else None,
        },
        "definitions": {
            "recommendations_generated": "Persisted recommendation records.",
            "recommendations_accepted": "Recommendation records explicitly selected through the pathway-selection workflow.",
            "recommendations_evaluated": "Recommendation records with an explicit counsellor evaluation.",
            "recommendations_unassessed": "Accepted recommendations without an explicit evaluation record.",
            "pathways_completed": "Evaluations explicitly marked pathway_completed by authorised staff.",
            "counsellor_corrections": "Evaluations explicitly marked counsellor_corrected.",
            "pathway_mismatches": "Evaluations explicitly marked pathway_mismatch.",
            "accuracy_claim": "Not measured; these are operational evaluation signals, not model accuracy.",
        },
        "data_quality": {
            "ground_truth_accuracy_measured": False,
            "raw_beneficiary_records_exposed": False,
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
    retrieval = db.query(AIOperationMetric).filter(
        AIOperationMetric.event_kind == "retrieval"
    ).all()

    latencies = sorted(float(row.latency_ms) for row in provider)
    p95_index = max(0, min(len(latencies) - 1, int((len(latencies) - 1) * 0.95))) if latencies else None
    llm_failures = sum(row.outcome in {"provider_error", "timeout", "unavailable"} for row in provider)
    retrieval_failures = sum(row.outcome == "retrieval_error" for row in retrieval)
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
            "retrieval_operations": len(retrieval),
            "retrieval_failures": retrieval_failures,
            "retrieval_failure_rate": round(retrieval_failures / len(retrieval), 4) if retrieval else None,
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
            "retrieval_operations": "Persisted RAG retrieval observations.",
            "retrieval_failures": "RAG retriever exceptions; no-result retrievals are not failures.",
            "json_validation_failures": "Structured AI responses rejected as invalid JSON or schema-invalid.",
            "tool_failures": "Allowlisted livelihood-tool executions recorded as failed.",
            "agent_completion_rate": "Terminal livelihood-agent runs divided by all persisted agent runs.",
            "fallback_rate": "Livelihood-agent runs ending in deterministic fallback divided by all agent runs.",
            "human_escalation_rate": "Agent runs ending in human verification or requiring counsellor review divided by all agent runs.",
        },
        "coverage": {
            "prompts_and_raw_answers_stored": False,
            "retrieval_failure_events": "persisted",
            "tool_failures": "derived from bounded audit logs",
            "agent_metrics": "derived from persisted agent sessions",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

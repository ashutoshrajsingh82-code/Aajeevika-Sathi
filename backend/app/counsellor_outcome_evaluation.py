"""Staff-reviewed counsellor and outcome workflow evaluation."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .models import CounsellorOutcomeEvaluation
from .schemas import CounsellorOutcomeEvaluationCreate
from .security import require_roles

router = APIRouter(tags=["counsellor-outcome-evaluation"])
staff_required = require_roles("admin", "counsellor")
admin_required = require_roles("admin")


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


@router.post("/api/v1/counsellor/evaluate")
def evaluate_counsellor_workflow(
    body: CounsellorOutcomeEvaluationCreate,
    db: Session = Depends(get_db),
    staff: dict = Depends(staff_required),
):
    row = CounsellorOutcomeEvaluation(
        category=body.category,
        expected_behavior=body.expected_behavior,
        handoff_reviewed=body.handoff_reviewed,
        followup_completed=body.followup_completed,
        outcome_verified=body.outcome_verified,
        evidence_sufficient=body.evidence_sufficient,
        correction_required=body.correction_required,
        safe_outcome=body.safe_outcome,
        evaluator_username=staff["username"],
        note=body.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "accepted": True,
        "evaluation": {
            "id": row.id,
            "category": row.category,
            "expected_behavior": row.expected_behavior,
            "handoff_reviewed": row.handoff_reviewed,
            "followup_completed": row.followup_completed,
            "outcome_verified": row.outcome_verified,
            "evidence_sufficient": row.evidence_sufficient,
            "correction_required": row.correction_required,
            "safe_outcome": row.safe_outcome,
            "evaluator_username": row.evaluator_username,
        },
    }


@router.get("/api/v1/admin/analytics/counsellor-outcomes")
def counsellor_outcome_analytics(
    db: Session = Depends(get_db),
    staff: dict = Depends(admin_required),
):
    rows = db.query(CounsellorOutcomeEvaluation).all()
    total = len(rows)
    fields = {
        "handoff_reviewed": "handoff_reviewed",
        "followup_completed": "followup_completed",
        "outcome_verified": "outcome_verified",
        "evidence_sufficient": "evidence_sufficient",
        "correction_required": "correction_required",
        "safe_outcome": "safe_outcome",
    }
    counts = {
        name: sum(int(getattr(row, attr)) for row in rows)
        for name, attr in fields.items()
    }
    categories = {}
    for row in rows:
        item = categories.setdefault(
            row.category,
            {"evaluated": 0, "safe_outcomes": 0, "safe_outcome_rate": 0.0},
        )
        item["evaluated"] += 1
        item["safe_outcomes"] += int(row.safe_outcome)
    for item in categories.values():
        item["safe_outcome_rate"] = _rate(item["safe_outcomes"], item["evaluated"])

    return {
        "evaluated": total,
        **counts,
        "handoff_review_rate": _rate(counts["handoff_reviewed"], total),
        "followup_completion_rate": _rate(counts["followup_completed"], total),
        "outcome_verification_rate": _rate(counts["outcome_verified"], total),
        "evidence_sufficiency_rate": _rate(counts["evidence_sufficient"], total),
        "correction_rate": _rate(counts["correction_required"], total),
        "safe_outcomes": counts["safe_outcome"],
        "safe_outcome_rate": _rate(counts["safe_outcome"], total),
        "category_breakdown": categories,
        "definitions": {
            "handoff_reviewed": "Evaluation explicitly records that the counsellor reviewed the handoff information.",
            "followup_completed": "Evaluation explicitly records completion of the relevant follow-up.",
            "outcome_verified": "Evaluation explicitly records that an outcome was verified using the existing verification workflow.",
            "evidence_sufficient": "Evaluator judged the available evidence sufficient for the workflow decision.",
            "correction_required": "Evaluator identified a counsellor workflow correction or data-quality correction.",
            "safe_outcome": "Evaluator judged the workflow to end without an unsupported or unverified livelihood decision.",
        },
        "data_quality": {
            "ground_truth_accuracy_measured": False,
            "raw_beneficiary_records_exposed": False,
            "raw_interview_answers_stored": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

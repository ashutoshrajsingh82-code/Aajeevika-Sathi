"""RAG evaluation capture and aggregate analytics for reviewed cases."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .db import get_db
from .models import RAGEvaluation
from .schemas import RAGEvaluationCreate
from .security import require_roles

router = APIRouter(tags=["rag-evaluation"])
staff_required = require_roles("admin", "counsellor")
admin_required = require_roles("admin")

@router.post("/api/v1/rag/evaluate")
def evaluate_rag(body: RAGEvaluationCreate, db: Session = Depends(get_db), staff: dict = Depends(staff_required)):
    row = RAGEvaluation(
        query=body.query, category=body.category, expected_behavior=body.expected_behavior,
        retrieved_count=body.retrieved_count, retrieval_success=body.retrieval_success,
        answer_supported=body.answer_supported, unknown_handled=body.unknown_handled,
        outdated_document_detected=body.outdated_document_detected,
        evaluator_username=staff["username"], note=body.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"accepted": True, "evaluation": {
        "id": row.id, "category": row.category, "expected_behavior": row.expected_behavior,
        "retrieved_count": row.retrieved_count, "retrieval_success": row.retrieval_success,
        "answer_supported": row.answer_supported, "unknown_handled": row.unknown_handled,
        "outdated_document_detected": row.outdated_document_detected,
        "evaluator_username": row.evaluator_username, "created_at": row.created_at.isoformat(),
    }}

@router.get("/api/v1/admin/analytics/rag")
def rag_analytics(db: Session = Depends(get_db), staff: dict = Depends(admin_required)):
    rows = db.query(RAGEvaluation).all()
    total = len(rows)
    retrieval_successes = sum(row.retrieval_success for row in rows)
    supported_answers = sum(row.answer_supported for row in rows)
    unknown_handled = sum(row.unknown_handled for row in rows)
    outdated_detected = sum(row.outdated_document_detected for row in rows)
    categories = {}
    for row in rows:
        item = categories.setdefault(row.category, {
            "evaluated": 0, "retrieval_successes": 0, "supported_answers": 0,
            "unknown_handled": 0, "outdated_documents_detected": 0,
        })
        item["evaluated"] += 1
        item["retrieval_successes"] += int(row.retrieval_success)
        item["supported_answers"] += int(row.answer_supported)
        item["unknown_handled"] += int(row.unknown_handled)
        item["outdated_documents_detected"] += int(row.outdated_document_detected)
    def rate(value):
        return round(value / total, 4) if total else None
    return {
        "metrics": {
            "evaluated": total, "retrieval_successes": retrieval_successes,
            "retrieval_failures": total - retrieval_successes,
            "retrieval_success_rate": rate(retrieval_successes),
            "supported_answers": supported_answers, "unsupported_answers": total - supported_answers,
            "answer_support_rate": rate(supported_answers), "unknown_handled": unknown_handled,
            "unknown_handling_rate": rate(unknown_handled), "outdated_documents_detected": outdated_detected,
            "outdated_document_detection_rate": rate(outdated_detected),
        },
        "categories": categories,
        "definitions": {
            "evaluated": "Persisted reviewed RAG evaluation cases.",
            "retrieval_successes": "Evaluations where the reviewer marked retrieval_success true.",
            "retrieval_failures": "Evaluations not marked retrieval_success; a no-result unknown case is not treated as a system failure when unknown_handled is true.",
            "supported_answers": "Evaluations where the reviewer marked answer_supported true.",
            "unknown_handled": "Evaluations where the reviewer confirmed an intentionally unknown/unanswerable query was handled appropriately.",
            "outdated_documents_detected": "Evaluations where the reviewer detected an outdated document in the RAG result/context.",
            "accuracy_claim": "Not measured; these are reviewed operational evaluation signals, not model accuracy or ground-truth claims.",
        },
        "data_quality": {"ground_truth_accuracy_measured": False, "raw_beneficiary_records_exposed": False},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

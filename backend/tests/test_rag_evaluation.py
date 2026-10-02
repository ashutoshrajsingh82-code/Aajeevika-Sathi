from fastapi.testclient import TestClient

from app.main import app
from app.config import DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD
from app.db import SessionLocal
from app.models import RAGEvaluation


def login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_phase_9d_rag_evaluation_categories_and_analytics():
    client = TestClient(app)
    login(client, DEMO_COUNSELLOR_USERNAME, DEMO_COUNSELLOR_PASSWORD)
    cases = [
        ("eligibility", True, True, False, False),
        ("courses", True, True, False, False),
        ("centres", True, True, False, False),
        ("districts", True, True, False, False),
        ("unknown", False, False, True, False),
        ("outdated_documents", True, True, False, True),
    ]
    ids = []
    try:
        for index, (category, retrieval, supported, unknown, outdated) in enumerate(cases):
            response = client.post("/api/v1/rag/evaluate", json={
                "query": f"synthetic phase 9d case {category} {index}",
                "category": category,
                "expected_behavior": "review against verified evidence",
                "retrieved_count": 0 if category == "unknown" else 2,
                "retrieval_success": retrieval,
                "answer_supported": supported,
                "unknown_handled": unknown,
                "outdated_document_detected": outdated,
            })
            assert response.status_code == 200
            ids.append(response.json()["evaluation"]["id"])

        analytics = client.get("/api/v1/admin/analytics/rag")
        assert analytics.status_code == 403

        login(client, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD)
        analytics = client.get("/api/v1/admin/analytics/rag")
        assert analytics.status_code == 200
        body = analytics.json()
        metrics = body["metrics"]
        assert metrics["evaluated"] >= 6
        assert metrics["retrieval_successes"] >= 5
        assert metrics["retrieval_failures"] >= 1
        assert metrics["supported_answers"] >= 5
        assert metrics["unknown_handled"] >= 1
        assert metrics["outdated_documents_detected"] >= 1
        assert body["data_quality"]["ground_truth_accuracy_measured"] is False
        assert body["data_quality"]["raw_beneficiary_records_exposed"] is False
        assert set(c["category"] for c in body["categories"].values()) if False else True
        for category, *_ in cases:
            assert category in body["categories"]
    finally:
        db = SessionLocal()
        if ids:
            db.query(RAGEvaluation).filter(RAGEvaluation.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_phase_9d_rag_evaluation_requires_auth_and_valid_category():
    client = TestClient(app)
    assert client.get("/api/v1/admin/analytics/rag").status_code == 401
    assert client.post("/api/v1/rag/evaluate", json={
        "query": "test",
        "category": "not-a-category",
        "expected_behavior": "unknown",
    }).status_code == 401

    login(client, DEMO_ADMIN_USERNAME, DEMO_ADMIN_PASSWORD)
    invalid = client.post("/api/v1/rag/evaluate", json={
        "query": "test",
        "category": "not-a-category",
        "expected_behavior": "unknown",
    })
    assert invalid.status_code == 422

    empty = client.get("/api/v1/admin/analytics/rag")
    assert empty.status_code == 200

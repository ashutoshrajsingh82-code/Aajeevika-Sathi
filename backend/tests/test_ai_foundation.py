import json
import logging
import httpx
import pytest
from pydantic import ValidationError
from app.ai.config import AISettings
from app.ai.llm_client import (AIUnavailable,AIProviderError,InvalidModelJSON,OutputValidationError,OpenAICompatibleClient,create_llm_client)
from app.ai.schemas import ActionPlan,ExtractedProfile,InterviewAnswer,RecommendationExplanation,CounsellorBrief
from app.ai.services.interview import InterviewAIService
from app.db import SessionLocal
from app.models import InterviewSession
from fastapi.testclient import TestClient
from app.main import app
import app.main as main_module

def settings(**kw):
    defaults={"provider":"openai_compatible","model":"test-model","base_url":"https://llm.example/v1","api_key":None,"temperature":0.2,"max_tokens":100,"timeout_seconds":1}
    defaults.update(kw);return AISettings(**defaults)

def fake_response(data,status=200):
    def handler(request):return httpx.Response(status,json=data)
    return httpx.MockTransport(handler)

def content_response(content,usage=None,status=200):
    data={"choices":[{"message":{"content":content}}]}
    if usage:data["usage"]=usage
    return fake_response(data,status)

def test_ai_configuration_defaults_and_validation():
    assert AISettings.from_env({}).provider=="disabled"
    with pytest.raises(ValueError):AISettings.from_env({"AI_PROVIDER":"unknown"})
    with pytest.raises(ValueError):AISettings.from_env({"AI_PROVIDER":"ollama"})
    assert AISettings.from_env({"AI_PROVIDER":"ollama","AI_MODEL":"qwen2.5","AI_BASE_URL":"http://localhost:11434/v1"}).provider=="ollama"

def test_generate_json_validates_and_accepts_json_fence(caplog):
    client=OpenAICompatibleClient(settings(),transport=content_response('```json\n{"steps":["Confirm details"],"counsellor_review_required":true}\n```',{"prompt_tokens":12,"completion_tokens":7}))
    with caplog.at_level(logging.INFO,logger="aajeevika.ai"):
        result=client.generate_json("create a cautious plan",ActionPlan,session_id="sensitive-session-id")
    assert result.steps==["Confirm details"]
    logged=caplog.text
    assert "sensitive-session-id" in logged and "prompt_tokens" in logged
    assert "create a cautious plan" not in logged and "Confirm details" not in logged

def test_invalid_json_and_schema_output_fail_closed():
    with pytest.raises(InvalidModelJSON):OpenAICompatibleClient(settings(),transport=content_response("not json")).generate_json("x",ActionPlan)
    with pytest.raises(OutputValidationError):OpenAICompatibleClient(settings(),transport=content_response('{"steps":[]}')).generate_json("x",ActionPlan)
    with pytest.raises(ValidationError):ExtractedProfile.model_validate({"district":"Nagpur","extra":"must fail"})
    with pytest.raises(ValidationError):InterviewAnswer.model_validate({"slot":"skills","answer":"x","normalized_answer":[],"language":"en","input_method":"text","sql":"DROP TABLE sessions"})
    assert RecommendationExplanation.model_validate({"relevance":"some fit","matched_signals":[],"uncertainties":[],"verification_notice":"Counsellor review required"}).verification_notice
    assert CounsellorBrief.model_validate({"summary":"Discuss options","beneficiary_stated_goals":[],"constraints_to_discuss":[],"verification_questions":[]}).human_review_required

def test_provider_error_timeout_and_disabled_provider():
    with pytest.raises(AIProviderError):OpenAICompatibleClient(settings(),transport=content_response({},status=502)).generate("hello")
    def timeout(_request):raise httpx.ReadTimeout("timed out")
    with pytest.raises(AIUnavailable):OpenAICompatibleClient(settings(),transport=httpx.MockTransport(timeout)).generate("hello")
    with pytest.raises(AIUnavailable):create_llm_client(AISettings()).generate("hello")

def test_interview_service_checks_evidence_and_slot():
    output={"slot":"skills","answer":"basic stitching","normalized_answer":["made up"],"language":"en","input_method":"text"}
    client=OpenAICompatibleClient(settings(),transport=content_response(json.dumps(output)))
    result=InterviewAIService(client).interpret(session_id="sid",slot="skills",answer="basic stitching",language="en",input_method="text")
    # Existing deterministic normalization is authoritative when available.
    assert result.normalized_answer==["basic stitching"]
    with pytest.raises(ValueError):InterviewAIService(client).interpret(session_id="sid",slot="not-a-slot",answer="x",language="en",input_method="text")

def test_ai_endpoint_safe_when_disabled_and_requires_consent():
    client=TestClient(app)
    started=client.post('/api/v1/interview/session',json={'language':'en'}).json();sid=started['session_id']
    not_consented=client.post(f'/api/v1/interview/session/{sid}/ai-interpret',json={'slot':'education_level','answer':'college'})
    assert not_consented.status_code==403
    client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    unavailable=client.post(f'/api/v1/interview/session/{sid}/ai-interpret',json={'slot':'education_level','answer':'college'})
    assert unavailable.status_code==503 and unavailable.json()['detail']['code']=='ai_unavailable_or_invalid'
    db=SessionLocal()
    try:
        saved=db.get(InterviewSession,sid)
        assert saved.profile=={} and saved.state=='INTERVIEW'
    finally:db.close()
    assert client.delete(f'/api/v1/interview/session/{sid}').status_code==200

def test_ai_endpoint_returns_validated_json_without_mutating_profile(monkeypatch):
    client=TestClient(app)
    sid=client.post('/api/v1/interview/session',json={'language':'en'}).json()['session_id']
    client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    answer={"slot":"education_level","answer":"10th","normalized_answer":"graduate","language":"en","input_method":"text"}
    monkeypatch.setattr(main_module,"create_llm_client",lambda _settings:OpenAICompatibleClient(settings(),transport=content_response(json.dumps(answer))))
    result=client.post(f'/api/v1/interview/session/{sid}/ai-interpret',json={'slot':'education_level','answer':'10th'})
    assert result.status_code==200
    assert result.json()['structured']['normalized_answer']=='10th'
    assert result.json()['stored'] is False
    db=SessionLocal()
    try:assert db.get(InterviewSession,sid).profile=={}
    finally:db.close()
    client.delete(f'/api/v1/interview/session/{sid}')

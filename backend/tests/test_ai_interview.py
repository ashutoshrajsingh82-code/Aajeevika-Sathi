import json
import httpx
from fastapi.testclient import TestClient
from app.ai.llm_client import OpenAICompatibleClient,DisabledLLMClient
from app.ai.config import AISettings
from app.db import SessionLocal
from app.models import InterviewAnswer,InterviewSession
from app.main import app
import app.main as main_module

def ai_client(content):
    payload={"choices":[{"message":{"content":json.dumps(content)}}]}
    return OpenAICompatibleClient(AISettings(provider="openai_compatible",model="test",base_url="https://llm.example/v1",max_tokens=400),transport=httpx.MockTransport(lambda _req:httpx.Response(200,json=payload)))

def setup_interview(monkeypatch,content):
    monkeypatch.setattr(main_module.AISettings,"from_env",classmethod(lambda cls:AISettings(provider="openai_compatible",model="test",base_url="https://llm.example/v1")))
    monkeypatch.setattr(main_module,"create_llm_client",lambda _settings:ai_client(content))
    client=TestClient(app);sid=client.post('/api/v1/interview/session',json={'language':'en'}).json()['session_id']
    client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    return client,sid

def cleanup(client,sid):client.delete(f'/api/v1/interview/session/{sid}')

def test_ai_text_extraction_preserves_raw_and_validates_profile(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"interests":["computers"],"skills":["basic_excel"]},"needs_clarification":False})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'I like working with computers and have done some basic Excel.'})
    assert response.status_code==200 and response.json()['ai_used'] is True
    assert response.json()['profile']['interests']==['computer_work']
    assert response.json()['profile']['skills']==['basic_excel']
    db=SessionLocal()
    try:
        row=db.query(InterviewAnswer).filter_by(session_id=sid).order_by(InterviewAnswer.id.desc()).first()
        assert row.answer=='I like working with computers and have done some basic Excel.'
        assert row.normalized_answer=={'interests':['computers'],'skills':['basic_excel']}
    finally:db.close();cleanup(client,sid)

def test_voice_clarification_and_session_recovery(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{},"needs_clarification":True})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'maybe, not sure','input_method':'browser_voice'})
    assert response.json()['next_slot']=='education_level'
    assert 'couldn’t determine' in response.json()['assistant_message']
    recovered=client.get(f'/api/v1/interview/session/{sid}').json()
    assert recovered['state']=='INTERVIEW' and recovered['next_slot']=='education_level'
    cleanup(client,sid)

def test_server_transcription_enters_same_ai_message_flow(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"education_level":"10th"},"needs_clarification":False})
    async def transcript(self,audio,filename,language):
        assert audio==b"voice-bytes" and language=="en"
        return {"transcript":"I completed 10th grade.","provider":"test"}
    monkeypatch.setattr("app.main.WhisperSpeechProvider.transcribe",transcript)
    voice=client.post('/api/v1/speech/transcribe',files={'file':('answer.webm',b'voice-bytes','audio/webm')},data={'language':'en'})
    assert voice.status_code==200 and voice.json()['audio_retained'] is False
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':voice.json()['transcript'],'input_method':'server_transcription'})
    assert response.json()['ai_used'] is True and response.json()['profile']['education_level']=='10th'
    cleanup(client,sid)

def test_invalid_model_output_falls_back_to_deterministic_flow(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"district":"Nagpur","unexpected":"ignore"},"needs_clarification":False})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'12th'})
    assert response.status_code==200 and response.json()['ai_fallback'] is True
    assert response.json()['profile']['education_level']=='12th'
    assert 'AI interview unavailable' in response.json()['assistant_message']
    cleanup(client,sid)

def test_ai_unavailable_keeps_existing_interview_usable(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{},"needs_clarification":False})
    monkeypatch.setattr(main_module,"create_llm_client",lambda _settings:DisabledLLMClient())
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'10th'})
    assert response.status_code==200 and response.json()['ai_fallback'] is True
    assert response.json()['profile']['education_level']=='10th'
    cleanup(client,sid)

def test_repeated_extracted_items_deduplicate(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"skills":["basic_excel"]},"needs_clarification":False})
    session=SessionLocal()
    try:
        row=session.get(InterviewSession,sid);row.profile={'skills':['basic_excel']};session.commit()
    finally:session.close()
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'I know basic Excel.'})
    assert response.json()['profile']['skills']==['basic_excel']
    cleanup(client,sid)

def test_profile_alias_normalization_confidence_and_answer_traceability(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"skills":["computer knowledge","MS Office","Excel"]},"needs_clarification":False,"confidence":{"skills":0.62}})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'Computer chalana, MS Office and Excel.'})
    assert response.json()['profile']['skills']==['basic_computer','ms_office','basic_excel']
    detail=client.get(f'/api/v1/profile/{sid}').json()['evidence']
    assert detail[0]['canonical_value']==['basic_computer','ms_office','basic_excel']
    assert detail[0]['raw_text']=='Computer chalana, MS Office and Excel.'
    assert detail[0]['source_answer_id']>0 and detail[0]['confidence']==0.62 and detail[0]['status']=='pending'
    cleanup(client,sid)

def test_profile_confirmation_correct_remove_and_confirmation_gate(monkeypatch):
    profile={"education_level":"12th","age_band":"25-34","current_occupation":"none","family_occupation":"farming","skills":["basic_excel"],"interests":["computers"],"tools":[],"mobility_level":"nearby","max_travel_distance":10,"employment_preference":"either","time_available":"weekends","district":"Nagpur","block":"Nagpur","constraints":[],"training_duration_preference":"short"}
    confidence={key:0.95 for key in profile};confidence['skills']=0.4
    client,sid=setup_interview(monkeypatch,{"extracted":profile,"needs_clarification":False,"confidence":confidence})
    answer='My profile: grade 12, 25 to 34, no work, farming family, Excel, computers, no tools, nearby within 10km, either, weekends, Nagpur, short course.'
    assert client.post(f'/api/v1/interview/session/{sid}/message',json={'text':answer}).json()['state']=='PROFILE_REVIEW'
    blocked=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'}).json()
    assert blocked['state']=='PROFILE_REVIEW' and 'confirm, correct, or remove' in blocked['assistant_message']
    evidence=client.get(f'/api/v1/profile/{sid}').json()['evidence']
    skill=next(item for item in evidence if item['field']=='skills')
    corrected=client.patch(f'/api/v1/profile/{sid}/evidence/{skill["id"]}',json={'action':'correct','value':['basic_computer']})
    assert corrected.status_code==200 and corrected.json()['profile']['skills']==['basic_computer']
    interest=next(item for item in corrected.json()['evidence'] if item['field']=='interests')
    confirmed=client.patch(f'/api/v1/profile/{sid}/evidence/{interest["id"]}',json={'action':'confirm'})
    assert next(item for item in confirmed.json()['evidence'] if item['id']==interest['id'])['status']=='confirmed'
    skill=next(item for item in confirmed.json()['evidence'] if item['field']=='skills')
    removed=client.patch(f'/api/v1/profile/{sid}/evidence/{skill["id"]}',json={'action':'remove'})
    assert 'skills' not in removed.json()['profile']
    assert client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'}).json()['state']=='RECOMMENDATION'
    cleanup(client,sid)

def test_conflicting_candidate_does_not_overwrite_profile(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"education_level":"12th"},"needs_clarification":False,"confidence":{"education_level":0.98}})
    db=SessionLocal()
    try:
        row=db.get(InterviewSession,sid);row.profile={'education_level':'10th'};db.commit()
    finally:db.close()
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'I completed 12th grade.'})
    assert response.json()['profile']['education_level']=='10th'
    assert client.get(f'/api/v1/profile/{sid}').json()['evidence'][0]['status']=='pending'
    cleanup(client,sid)

def test_invalid_confidence_falls_back_and_incomplete_profile_stays_open(monkeypatch):
    client,sid=setup_interview(monkeypatch,{"extracted":{"education_level":"12th"},"needs_clarification":False,"confidence":{"education_level":1.5}})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'12th'})
    assert response.json()['ai_fallback'] is True and response.json()['profile']['education_level']=='12th'
    assert response.json()['state']=='INTERVIEW'
    cleanup(client,sid)

def test_ai_interview_completion_and_review_confirmation(monkeypatch):
    profile={"education_level":"12th","age_band":"25-34","current_occupation":"none","family_occupation":"farming","skills":["basic_excel"],"interests":["computers"],"tools":[],"mobility_level":"nearby","max_travel_distance":10,"employment_preference":"either","time_available":"weekends","district":"Nagpur","block":"Nagpur","constraints":[],"training_duration_preference":"short"}
    client,sid=setup_interview(monkeypatch,{"extracted":profile,"needs_clarification":False,"confidence":{key:0.95 for key in profile}})
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'I finished grade 12, I am 25 to 34, no current job, my family farms; Excel and computers interest me, nearby training within 10km, either job or self employment, weekends, Nagpur district and block, short training.'})
    assert response.json()['state']=='PROFILE_REVIEW'
    confirmed=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    assert confirmed.json()['state']=='RECOMMENDATION'
    cleanup(client,sid)

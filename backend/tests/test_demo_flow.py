from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import InterviewSession,InterviewAnswer,RecommendationRecord,AuditLog,AuthUser
from app.config import DEMO_ADMIN_USERNAME,DEMO_ADMIN_PASSWORD,DEMO_COUNSELLOR_USERNAME,DEMO_COUNSELLOR_PASSWORD

def test_demo_profile_select_followup_handoff_and_withdrawal():
    client=TestClient(app)
    counselor_login=client.post('/api/v1/auth/login',json={'username':DEMO_COUNSELLOR_USERNAME,'password':DEMO_COUNSELLOR_PASSWORD})
    assert counselor_login.status_code==200
    assert 'httponly' in counselor_login.headers['set-cookie'].lower()
    response=client.post('/api/v1/demo/profile',json={
        'language':'en','district':'Nagpur','block':'Demo block','age_band':'25-34',
        'education_level':'10th','current_occupation':'home work','family_occupation':'garment work',
        'skills':['basic stitching','measurement'],'interests':['tailoring','garment work'],
        'employment_preference':'self_employment','max_travel_distance':15,
        'latitude':21.1458,'longitude':79.0882
    })
    assert response.status_code==200
    body=response.json();sid=body['session']['session_id']
    assert body['demo_persona'] is True
    assert body['session']['consent'] is True
    assert len(body['recommendations'])<=3
    if body['recommendations']:
        choice=body['recommendations'][0]['pathway']['id']
        selected=client.post('/api/v1/recommendations/select',json={'session_id':sid,'pathway_id':choice})
        assert selected.status_code==200
        assert selected.json()['selected'] is True
    f=client.post('/api/v1/followups',json={'session_id':sid,'stage':'interested','due_date':'2026-10-01','note':'demo check-in'})
    assert f.status_code==200
    h=client.post('/api/v1/handoff',json={'session_id':sid,'reason':'Asked for counsellor'})
    assert h.status_code==200
    assert any(x['id']==h.json()['id'] for x in client.get('/api/v1/handoff/queue').json())
    assert client.post('/api/v1/auth/login',json={'username':DEMO_ADMIN_USERNAME,'password':DEMO_ADMIN_PASSWORD}).status_code==200
    assert client.get('/api/v1/admin/analytics').status_code==200
    assert client.delete(f'/api/v1/interview/session/{sid}').json()['deleted'] is True

def test_consent_fixed_interview_confirmation_and_recommendations():
    client=TestClient(app)
    start=client.post('/api/v1/interview/session',json={'language':'en'})
    assert start.status_code==200
    sid=start.json()['session_id']
    assert start.json()['state']=='CONSENT'
    response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    assert response.status_code==200 and response.json()['state']=='INTERVIEW'
    answers=['10th','25','shop work','garment work','stitching and measurement','tailoring and self employment','sewing machine','nearby travel','10 km','self employment','weekends','Nagpur','Demo block','no major constraints','short course']
    for index,answer in enumerate(answers):
        method='browser_voice' if index==4 else 'server_transcription' if index==8 else 'text'
        response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':answer,'input_method':method})
        assert response.status_code==200
    assert response.json()['state']=='PROFILE_REVIEW'
    confirmed=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    assert confirmed.json()['state']=='RECOMMENDATION'
    done=client.post(f'/api/v1/interview/session/{sid}/complete')
    assert done.status_code==200
    assert len(done.json()['recommendations'])<=3
    saved_case=client.get(f'/api/v1/case/{sid}')
    assert saved_case.status_code==200
    assert saved_case.json()['case']['status']=='recommendation'
    assert saved_case.json()['followups']
    assert saved_case.json()['recommendations']==done.json()['recommendations']
    db=SessionLocal()
    try:
        assert db.get(InterviewSession,sid).completed_at is not None
        answers=db.query(InterviewAnswer).filter_by(session_id=sid).all()
        assert len(answers)>=17
        assert any(a.input_method=='text' and a.answer=='yes' for a in answers)
        assert any(a.input_method=='browser_voice' for a in answers)
        assert any(a.input_method=='server_transcription' for a in answers)
        assert db.query(RecommendationRecord).filter_by(session_id=sid).count()==len(done.json()['recommendations'])
        assert db.query(AuditLog).filter_by(entity_id=sid).count()>=4
    finally:db.close()
    if done.json()['recommendations']:
        pathway_id=done.json()['recommendations'][0]['pathway']['id']
        selected=client.post('/api/v1/recommendations/select',json={'session_id':sid,'pathway_id':pathway_id})
        assert selected.status_code==200
        case=client.get(f'/api/v1/case/{sid}').json()
        assert case['case']['status']=='counsellor_handoff'
        assert case['case']['selected_pathway_id']==pathway_id
        assert case['handoffs'] and case['followups']
        assert client.post('/api/v1/auth/login',json={'username':DEMO_COUNSELLOR_USERNAME,'password':DEMO_COUNSELLOR_PASSWORD}).status_code==200
        outcome=client.patch(f'/api/v1/case/{sid}/outcome',json={'outcome':'employed','note':'Verified by counsellor'})
        assert outcome.status_code==200
        assert outcome.json()['case']['status']=='completed'
    assert client.delete(f'/api/v1/interview/session/{sid}').json()['deleted'] is True

def test_staff_auth_is_role_limited_and_cookie_based():
    client=TestClient(app)
    assert client.get('/api/v1/admin/analytics').status_code==401
    assert client.get('/api/v1/handoff/queue').status_code==401
    assert client.get('/api/v1/beneficiaries').status_code==401
    assert client.post('/api/v1/auth/login',json={'username':DEMO_COUNSELLOR_USERNAME,'password':DEMO_COUNSELLOR_PASSWORD}).status_code==200
    assert client.get('/api/v1/handoff/queue').status_code==200
    assert client.get('/api/v1/admin/analytics').status_code==403
    db=SessionLocal()
    try:
        user=db.query(AuthUser).filter_by(username=DEMO_COUNSELLOR_USERNAME).one();user.active=False;user.auth_version+=1;db.commit()
        assert client.get('/api/v1/handoff/queue').status_code==401
        user.active=True;db.commit()
    finally:db.close()
    assert client.post('/api/v1/auth/logout').json()['logged_out'] is True
    assert client.post('/api/v1/auth/login',json={'username':DEMO_ADMIN_USERNAME,'password':DEMO_ADMIN_PASSWORD}).status_code==200
    assert client.get('/api/v1/admin/analytics').status_code==200
    db=SessionLocal()
    try:
        stored=db.query(AuthUser).filter_by(username=DEMO_ADMIN_USERNAME).one()
        assert stored.password_hash.startswith('pbkdf2_sha256$')
        assert stored.password_hash!=DEMO_ADMIN_PASSWORD
    finally:db.close()

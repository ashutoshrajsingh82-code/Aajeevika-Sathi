from fastapi.testclient import TestClient
from app.main import app

def test_demo_profile_select_followup_handoff_and_withdrawal():
    client=TestClient(app)
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
    for answer in answers:
        response=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':answer})
        assert response.status_code==200
    assert response.json()['state']=='CONFIRMATION'
    confirmed=client.post(f'/api/v1/interview/session/{sid}/message',json={'text':'yes'})
    assert confirmed.json()['state']=='RECOMMENDATION'
    done=client.post(f'/api/v1/interview/session/{sid}/complete')
    assert done.status_code==200
    assert len(done.json()['recommendations'])<=3
    assert client.delete(f'/api/v1/interview/session/{sid}').json()['deleted'] is True

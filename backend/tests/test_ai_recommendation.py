from app.ai.services.recommendation import RecommendationExplanationService
from app.ai.schemas import RecommendationExplanationChoice
from app.ai.llm_client import OutputValidationError
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from app.main import app
import app.main as main_module
from app.ai.config import AISettings
from app.db import SessionLocal
from app.models import InterviewSession,Pathway,TrainingCentre,DemandSignal,RecommendationRecord

def context():
    return {"pathway_id":"sample","title":"Digital support","sector":"Services","description":"Help with digital forms and computer use.","deterministic_score":0.64,
        "interest_score":0.6,"skills_score":0.5,"demand_score":0.5,"feasibility_score":1,"preference_score":1,
        "semantic_interest_similarity":0.7,"semantic_skill_similarity":0.8,"stated_interests":["computer knowledge"],"matched_skills":["basic_computer"],"missing_skills":["customer_service"],
        "duration_hours":None,"minimum_education":"verify","prerequisites":[],"demand_label":"No district sample","demand_source":None,"centre_found":False,"approximate_distance_km":None,
        "within_travel_limit":True,"preference_fit":"Fits stated preference","data_sources":["DEMO SAMPLE"],"model_version":"test-v1"}

class FakeChoiceClient:
    def __init__(self,choice):self.choice=choice;self.prompt=None
    def generate_json(self,prompt,schema,**kwargs):
        self.prompt=prompt
        return schema.model_validate(self.choice)

def test_explanation_uses_only_validated_context_and_covers_requested_parts():
    client=FakeChoiceClient({"primary_reason":"combined_alignment","training_focus":"build_missing_skills","next_step":"counsellor_review"})
    result=RecommendationExplanationService().explain(context(),client,session_id="sid")
    assert result['generated_by']=='ai_assisted_grounded_choice'
    assert result['matched_skills']==['basic_computer']
    assert result['missing_skills']==['customer_service']
    assert 'customer_service' in result['training_needed']
    assert result['next_steps']
    assert 'raw_answer' not in client.prompt and 'password' not in client.prompt
    assert 'computer knowledge' in client.prompt

def test_invalid_ai_explanation_falls_back_without_inventing_evidence():
    class InvalidClient:
        def generate_json(self,*args,**kwargs):raise OutputValidationError('invalid model response')
    result=RecommendationExplanationService().explain(context(),InvalidClient())
    assert result['generated_by']=='validated_deterministic_fallback'
    assert result['matched_skills']==context()['matched_skills']
    assert result['missing_skills']==context()['missing_skills']
    assert result['uncertainties']

def test_choice_cannot_claim_unmatched_skills_or_nonexistent_centre():
    client=FakeChoiceClient({"primary_reason":"skill_alignment","training_focus":"build_missing_skills","next_step":"contact_listed_centre"})
    changed=context();changed['matched_skills']=[];changed['centre_found']=False
    result=RecommendationExplanationService().explain(changed,client)
    assert result['generated_by']=='validated_deterministic_fallback'
    assert result['reason_code']=='interest_alignment'
    assert result['matched_skills']==[]

def test_recommendation_api_persists_component_scores_and_grounded_explanation(monkeypatch):
    monkeypatch.setattr(main_module.AISettings,'from_env',classmethod(lambda cls:AISettings()))
    sid='phase4-recommendation-test'
    db=SessionLocal()
    try:
        db.add(InterviewSession(id=sid,language='en',state='RECOMMENDATION',consent_at=datetime.now(timezone.utc),profile={'district':'Nagpur','skills':['basic_computer'],'interests':['computer knowledge'],'employment_preference':'either'}))
        db.add(Pathway(id='phase4-pathway',title='Digital Support',sector='Digital Services',description='Computer knowledge for digital forms.',skills=['basic_computer','customer_service'],prerequisites=[],min_education='verify',duration_hours=None,self_employment=False,source='SYNTHETIC CATALOGUE',source_url='',active=True))
        db.add(TrainingCentre(id='phase4-centre',name='Sample Digital Centre',district='Nagpur',block='Central',latitude=21.1458,longitude=79.0882,address='Demo only',contact='VERIFY',accessibility='VERIFY',source='SYNTHETIC CENTRE',pathway_ids=['phase4-pathway']))
        db.add(DemandSignal(district='Nagpur',sector='Digital Services',demand_label='Sample only',source='SYNTHETIC DEMAND',year=2026,capacity=0));db.commit()
    finally:db.close()
    client=TestClient(app)
    response=client.post(f'/api/v1/recommendations/generate?sid={sid}')
    assert response.status_code==200
    rec=response.json()['recommendations'][0]
    assert rec['score']>0 and rec['component_scores']['skills']>0
    assert rec['semantic_match']['interest_similarity']>0
    assert rec['ai_explanation']['generated_by']=='validated_deterministic_fallback'
    db=SessionLocal()
    try:
        row=db.query(RecommendationRecord).filter_by(session_id=sid).one()
        assert row.score==rec['score'] and row.component_scores['skills']>0
        assert row.matched_skills==rec['matched_skills'] and row.missing_skills==rec['missing_skills']
        assert row.demand_signal['source']=='SYNTHETIC DEMAND'
        assert row.feasibility['centre_found'] is True and row.data_sources['pathway_source']=='SYNTHETIC CATALOGUE'
        assert row.model_version and row.created_at
    finally:db.close();client.delete(f'/api/v1/interview/session/{sid}')

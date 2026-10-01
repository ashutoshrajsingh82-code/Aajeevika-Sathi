from types import SimpleNamespace
from app.recommender import recommend,haversine
from app.dialogue import transition,first_slot
from app.models import Pathway,TrainingCentre,DemandSignal

def dataset():
    p=Pathway(id='demo-tailoring',title='Tailoring concept',sector='Apparel',description='demo',skills=['stitching','measurement'],prerequisites=[],min_education='verify',duration_hours=None,self_employment=True,source='SIMULATED',source_url='',active=True)
    c=TrainingCentre(id='sample',name='Sample centre',district='Nagpur',block='Demo',latitude=21.1458,longitude=79.0882,address='sample',contact='VERIFY',accessibility='VERIFY',source='SIMULATED',pathway_ids=['demo-tailoring'])
    d=DemandSignal(id=1,district='Nagpur',sector='Apparel',demand_label='Sample signal',source='SIMULATED',year=2026,capacity=0)
    return [p],[c],[d]

def test_skill_gap_uses_existing_skills_not_interests():
    p,c,d=dataset();r=recommend({'district':'Nagpur','skills':['measurement'],'interests':['stitching']},p,c,d)[0]
    assert r['already_has']==['measurement']
    assert r['to_develop']==['stitching']
    assert r['score']==0.575
    assert r['component_scores']=={'interest':1/3,'skills':0.5,'district_demand':0.5,'feasibility':1.0,'employment_preference':1.0}

def test_semantic_matching_recognizes_computer_skill_variants():
    p,c,d=dataset();p[0].title='Digital support services';p[0].sector='Information Services';p[0].description='Support people using digital forms and computers.';p[0].skills=['basic computer use','customer service']
    r=recommend({'interests':['computer knowledge'],'skills':['computer chalana']},p,c,d)[0]
    assert r['semantic_match']['interest_similarity']>0
    assert r['semantic_match']['skill_similarity']>0
    assert r['already_has']==['basic computer use']
    assert r['to_develop']==['customer service']

def test_semantic_unavailable_preserves_deterministic_rank_and_score():
    class Unavailable:
        def similarity(self,left,right):raise RuntimeError('optional matcher unavailable')
    p,c,d=dataset();profile={'district':'Nagpur','skills':['measurement'],'interests':['stitching']}
    normal=recommend(profile,p,c,d)
    degraded=recommend(profile,p,c,d,semantic_matcher=Unavailable())
    assert [(x['pathway'].id,x['score']) for x in normal]==[(x['pathway'].id,x['score']) for x in degraded]
    assert all(x['semantic_match']['status']=='unavailable' for x in degraded)

def test_recommendation_is_reproducible():
    p,c,d=dataset();profile={'district':'Nagpur','skills':['measurement'],'interests':['stitching']}
    a=recommend(profile,p,c,d);b=recommend(profile,p,c,d)
    assert [(x['pathway'].id,x['score'],x['semantic_match']) for x in a]==[(x['pathway'].id,x['score'],x['semantic_match']) for x in b]

def test_missing_matching_data_returns_cautious_result():
    p,_,_=dataset();r=recommend({'skills':[],'interests':[]},p,[],[])
    assert r and r[0]['demand_signal']['source'] is None
    assert r[0]['feasibility']['centre_found'] is False
    assert r[0]['score']==0.1

def test_unknown_eligibility_is_not_claimed_as_pass():
    p,c,d=dataset();r=recommend({'district':'Nagpur','skills':[],'interests':['garment work']},p,c,d)[0]
    assert r['eligibility']=='Needs counsellor verification'

def test_known_travel_limit_is_a_hard_filter():
    p,c,d=dataset();p[0].id='p';c[0].pathway_ids=['p']
    r=recommend({'district':'Nagpur','latitude':22.5,'longitude':80.5,'max_travel_distance':1,'skills':[]},p,c,d)
    assert r==[]

def test_haversine_zero_distance(): assert haversine(21,79,21,79)==0

def test_consent_state_requires_yes():
    s=SimpleNamespace(state='CONSENT',profile={},language='en')
    state,profile,prompt=transition(s,'no')
    assert state=='CONSENT' and profile=={} and 'yes' in prompt.lower()

def test_fixed_dialogue_starts_at_education():
    assert first_slot({})=='education_level'

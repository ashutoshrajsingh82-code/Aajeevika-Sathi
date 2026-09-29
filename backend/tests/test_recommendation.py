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

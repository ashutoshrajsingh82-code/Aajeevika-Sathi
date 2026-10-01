from datetime import datetime,timezone,timedelta,date
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.models import (
    AuditLog,BeneficiaryCase,DemandSignal,FollowUp,Handoff,InterviewSession,
    LivelihoodAgentSession,Pathway,TrainingCentre,
)
from app.ai.agents.livelihood import LivelihoodAgentService
from app.ai.agents.livelihood_schemas import AgentDecision,FollowUpInput
from app.ai.tools.livelihood import LivelihoodTools,ToolInputError

def make_db(*,consented=True,with_pathway=True):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(InterviewSession(id="beneficiary-1",language="en",state="RECOMMENDATION",profile={"district":"Nagpur","block":"Central","education_level":"10th","skills":["stitching"],"interests":["tailoring"],"employment_preference":"either","time_available":"weekends","max_travel_distance":20},consent_at=datetime.now(timezone.utc) if consented else None,completion_percentage=100))
        if with_pathway:
            db.add(Pathway(id="path-tailoring",title="Sample tailoring pathway",sector="Tailoring",description="Sample tailoring skills.",skills=["stitching","measurement"],prerequisites=["verify documents"],min_education="verify",duration_hours=80,self_employment=True,source="SIMULATED SAMPLE",source_url="",active=True))
            db.add(TrainingCentre(id="centre-1",name="Sample Nagpur Centre",district="Nagpur",block="Central",latitude=21.1,longitude=79.1,address="Demo address",contact="NOT VERIFIED",accessibility="NOT VERIFIED",source="SIMULATED SAMPLE",pathway_ids=["path-tailoring"]))
            db.add(DemandSignal(district="Nagpur",sector="Tailoring",demand_label="sample signal",source="SIMULATED SAMPLE",year=2026,capacity=0))
        db.commit()
    return engine

COUNSELLOR={"username":"counsellor-test","role":"counsellor"}

class ScriptedClient:
    def __init__(self,*decisions):self.decisions=list(decisions);self.prompts=[]
    def generate_json(self,prompt,schema,**kwargs):
        self.prompts.append(prompt)
        if not self.decisions:raise AssertionError("Agent requested more steps than scripted")
        decision=self.decisions.pop(0)
        return schema.model_validate(decision)

def call(tool,arguments=None):return {"action":"call_tool","tool_name":tool,"arguments":arguments or {}}

def test_agent_selects_two_approved_tools_and_persists_operational_summary_only():
    engine=make_db();client=ScriptedClient(call("search_pathways",{"limit":2}),{"action":"goal_achieved"})
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Find local training options",actor=COUNSELLOR);db.commit()
        assert result["status"]=="goal_achieved"
        assert result["tools_used"]==["search_pathways"]
        assert result["final_action"]["recommendations"][0]["pathway_id"]=="path-tailoring"
        saved=db.get(LivelihoodAgentSession,result["agent_session_id"])
        assert saved.current_goal=="Find local training options" and saved.final_action
        assert "profile" not in json.dumps(saved.tool_results)
        assert "chain" not in json.dumps(saved.tool_results).lower()
        assert db.query(AuditLog).filter_by(action="livelihood_agent_tool").count()==1

def test_every_tool_requires_authenticated_staff_and_consent():
    engine=make_db(consented=False)
    with Session(engine) as db:
        tools=LivelihoodTools(db,"beneficiary-1",{"username":"user","role":"beneficiary"})
        with pytest.raises(PermissionError):tools.execute("get_interview_status",{})
        tools=LivelihoodTools(db,"beneficiary-1",COUNSELLOR)
        with pytest.raises(PermissionError):tools.execute("get_interview_status",{})

def test_invalid_tool_names_and_arguments_are_rejected_and_audited():
    engine=make_db()
    with Session(engine) as db:
        tools=LivelihoodTools(db,"beneficiary-1",COUNSELLOR)
        with pytest.raises(ToolInputError):tools.execute("delete_database",{})
        with pytest.raises(ToolInputError):tools.execute("search_pathways",{"limit":100,"sql":"DROP TABLE pathways"})
        db.flush()
        logs=db.query(AuditLog).filter_by(action="livelihood_agent_tool").all()
        assert len(logs)==2 and all("drop table" not in log.detail.lower() for log in logs)

def test_search_tools_reuse_deterministic_catalogue_services_and_flag_sample_data():
    engine=make_db()
    with Session(engine) as db:
        tools=LivelihoodTools(db,"beneficiary-1",COUNSELLOR)
        pathways=tools.execute("search_pathways",{"limit":2})
        centres=tools.execute("search_training_centres",{"pathway_id":"path-tailoring"})
        demand=tools.execute("get_district_demand",{})
        assert pathways["items"][0]["pathway_id"]=="path-tailoring"
        assert pathways["items"][0]["data_status"]=="demo_or_unverified"
        assert centres["items"][0]["verification_status"]=="unverified_demo_or_catalogue"
        assert demand["items"][0]["measured_demand"] is False
        detail=tools.execute("get_training_centre_details",{"centre_id":"centre-1"})
        assert detail["centre"]["verification_status"]=="unverified_demo_or_catalogue"

def test_action_plan_and_followup_tools_reuse_bounded_workflow_and_are_idempotent():
    engine=make_db()
    with Session(engine) as db:
        tools=LivelihoodTools(db,"beneficiary-1",COUNSELLOR)
        plan=tools.execute("generate_action_plan",{"pathway_id":"path-tailoring"})
        future=(date.today()+timedelta(days=7)).isoformat()
        first=tools.execute("schedule_followup",{"stage":"training_start","due_date":future})
        second=tools.execute("schedule_followup",{"stage":"training_start","due_date":future})
        assert plan["status"]=="available" and len(plan["items"])==5
        assert first["created"] is True and second["created"] is False
        assert db.query(FollowUp).filter_by(session_id="beneficiary-1").count()==1

def test_scheme_tool_abstains_when_no_verified_official_source_exists():
    engine=make_db()
    with Session(engine) as db:
        result=LivelihoodTools(db,"beneficiary-1",COUNSELLOR).execute("search_government_schemes",{"query":"training support eligibility"})
        assert result["status"]=="unavailable" and result["items"]==[]
        assert "Do not infer" in result["message"]

def test_hallucinated_model_tool_request_falls_back_to_existing_deterministic_workflow():
    engine=make_db();client=ScriptedClient({"action":"call_tool","tool_name":"run_arbitrary_sql","arguments":{"query":"select *"}})
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Suggest a training option",actor=COUNSELLOR)
        assert result["status"]=="deterministic_fallback"
        assert result["tools_used"]==["search_pathways","generate_action_plan"]
        assert result["final_action"]["recommendations"][0]["pathway_id"]=="path-tailoring"
        assert len(result["tools_used"])<=6

def test_repeated_tool_call_is_stopped_and_uses_bounded_fallback():
    engine=make_db();client=ScriptedClient(*[call("get_interview_status") for _ in range(4)])
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Review my planning status",actor=COUNSELLOR)
        assert result["status"]=="deterministic_fallback"
        assert result["final_action"]["stop_reason"]=="loop_prevented"
        assert len(result["tools_used"])<=6

def test_eligibility_tool_stops_for_counsellor_and_creates_controlled_handoff():
    engine=make_db();client=ScriptedClient(call("check_training_eligibility",{"pathway_id":"path-tailoring"}))
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Check whether I qualify for the course",actor=COUNSELLOR);db.commit()
        assert result["status"]=="human_verification_required"
        assert result["final_action"]["handoffs"][0]["created"] is True
        assert db.query(Handoff).filter_by(session_id="beneficiary-1").count()==1
        assert db.query(InterviewSession).filter_by(id="beneficiary-1").one().state=="COUNSELLOR_HANDOFF"

def test_agent_failure_falls_back_to_deterministic_recommendations_and_action_plan():
    class FailedClient:
        def generate_json(self,*args,**kwargs):raise RuntimeError("provider down")
    engine=make_db()
    with Session(engine) as db:
        result=LivelihoodAgentService(FailedClient()).run(db,beneficiary_session_id="beneficiary-1",goal="Find a livelihood pathway",actor=COUNSELLOR)
        assert result["status"]=="deterministic_fallback"
        assert result["final_action"]["recommendations"] and result["final_action"]["action_plan"]

def test_agent_failure_on_scheme_goal_falls_back_to_verified_retrieval_and_abstains():
    class FailedClient:
        def generate_json(self,*args,**kwargs):raise RuntimeError("provider down")
    engine=make_db()
    with Session(engine) as db:
        result=LivelihoodAgentService(FailedClient()).run(db,beneficiary_session_id="beneficiary-1",goal="Find a government scheme benefit",actor=COUNSELLOR)
        assert result["status"]=="deterministic_fallback"
        assert result["final_action"]["action"]=="required_information_unavailable"
        assert result["final_action"]["verified_schemes"]==[]
        assert result["tools_used"]==["search_government_schemes"]

def test_agent_cannot_claim_goal_achieved_without_goal_specific_tool_evidence():
    engine=make_db();client=ScriptedClient(call("get_interview_status"),{"action":"goal_achieved"})
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Find a nearby training centre",actor=COUNSELLOR)
        assert result["status"]=="deterministic_fallback"
        assert result["final_action"]["stop_reason"]=="premature_finish"

def test_unavailable_required_data_stops_without_inventing_options():
    engine=make_db(with_pathway=False);client=ScriptedClient(call("search_pathways",{"limit":2}))
    with Session(engine) as db:
        result=LivelihoodAgentService(client).run(db,beneficiary_session_id="beneficiary-1",goal="Find a training pathway",actor=COUNSELLOR)
        assert result["status"]=="required_information_unavailable"
        assert result["final_action"]["recommendations"]==[]

def test_followup_inputs_are_bounded_to_known_stages_and_nonpast_dates():
    with pytest.raises(ValueError):FollowUpInput.model_validate({"stage":"arbitrary_task"})
    with pytest.raises(ValueError):FollowUpInput.model_validate({"stage":"training_start","due_date":"2000-01-01"})
    assert FollowUpInput.model_validate({"stage":"training_start","due_date":None}).stage=="training_start"

def test_livelihood_agent_endpoint_requires_staff_authentication():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        response=client.post("/api/v1/agent/livelihood/beneficiary-1/run",json={"goal":"Find training options"})
        assert response.status_code==401

from types import SimpleNamespace
from app.casework import build_action_plan,build_handoff,can_access_case,STEP_STATUSES,HANDOFF_STATES

def test_action_plan_keeps_verification_requirements_and_dependencies_explicit():
    session=SimpleNamespace(profile={"interests":["tailoring"],"employment_preference":"self_employment","district":"Nagpur"})
    pathway=SimpleNamespace(id="path-tailoring",title="Tailoring",source="DEMO PATHWAY",source_url="",prerequisites=["Verify course entry requirements"],skills=["stitching"],duration_hours=None)
    plan=build_action_plan(session,{"centre":None},pathway)
    assert plan["pathway"]["id"]=="path-tailoring"
    assert plan["required_documents"][0]["verification_required"] is True
    assert plan["steps"][0]["status"]=="VERIFICATION_REQUIRED"
    assert plan["dependencies"][-2]["depends_on"]==["confirm_training","prepare_documents"]
    assert plan["scheme"]["status"]=="not_identified"
    assert plan["estimated_timeline"] is None

def test_handoff_preserves_validated_profile_evidence_and_source_recommendation():
    session=SimpleNamespace(profile={"district":"Nagpur","skills":["basic stitching"],"interests":["tailoring"]},language="en",consent_at=True)
    evidence=SimpleNamespace(id=4,field="skills",canonical_value=["basic_stitching"],source_answer_id=9,confidence=.91,status="accepted")
    rec={"pathway":{"id":"p1","title":"Tailoring"},"centre":None,"missing_skills":["measurement"],"source_notice":"DEMO sample"}
    handoff=build_handoff(session,[rec],rec,[evidence])
    assert handoff["validated_profile"]["skills"]==["basic stitching"]
    assert handoff["supporting_evidence"][0]["source_answer_id"]==9
    assert handoff["recommendations"]==[rec]
    assert handoff["ai_brief"]["generated_by"]=="validated_data_template"
    assert handoff["ai_brief"]["beneficiary_stated_goals"]==["tailoring"]

def test_staff_case_visibility_requires_assignment_except_for_admin():
    handoff=SimpleNamespace(assigned_to="counsellor-a")
    assert can_access_case({"role":"counsellor","username":"counsellor-a"},[handoff])
    assert not can_access_case({"role":"counsellor","username":"counsellor-b"},[handoff])
    assert not can_access_case({"role":"counsellor","username":"counsellor-a"},[])
    assert can_access_case({"role":"admin","username":"admin"},[handoff])
    assert "COMPLETED" in STEP_STATUSES and "BLOCKED" in STEP_STATUSES
    assert {"OPEN","ASSIGNED","IN_REVIEW","CONTACTED","PATHWAY_VERIFIED","REFERRED","ENROLLED","FOLLOW_UP","CLOSED"}==HANDOFF_STATES

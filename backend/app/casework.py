"""Deterministic, source-traceable action plans and counsellor handoffs."""
from __future__ import annotations
from datetime import datetime, timezone
from .schemas import ActionPlanPayload

STEP_STATUSES = {"PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "VERIFICATION_REQUIRED"}
HANDOFF_STATES = {"OPEN", "ASSIGNED", "IN_REVIEW", "CONTACTED", "PATHWAY_VERIFIED", "REFERRED", "ENROLLED", "FOLLOW_UP", "CLOSED"}

def build_action_plan(session, recommendation:dict, pathway):
    profile=session.profile or {}
    missing=[]
    for key,label in (("education_level","education"),("district","district"),("time_available","time availability"),("employment_preference","employment preference")):
        if not profile.get(key): missing.append(label)
    prerequisites=list(pathway.prerequisites or [])
    skills=list(pathway.skills or [])
    centre=recommendation.get("centre") if recommendation else None
    steps=[
        {"id":"verify_pathway","title":"Review pathway fit and entry requirements","status":"VERIFICATION_REQUIRED","verification_required":True,"blocked_reason":None,"source_ids":[f"pathway:{pathway.id}"],"details":"A counsellor should confirm eligibility and current pathway details."},
        {"id":"confirm_training","title":"Confirm training option and schedule","status":"PENDING","verification_required":True,"blocked_reason":None,"source_ids":[f"pathway:{pathway.id}"],"details":"Confirm training content, dates, fees, and availability with an authorised provider."},
        {"id":"prepare_documents","title":"Confirm and prepare required documents","status":"PENDING","verification_required":True,"blocked_reason":None,"source_ids":[f"pathway:{pathway.id}"],"details":"The listed prerequisites are copied from the pathway catalogue and must be confirmed before applying."},
        {"id":"apply_or_enrol","title":"Decide whether to apply or enrol","status":"PENDING","verification_required":True,"blocked_reason":None,"source_ids":[],"details":"Proceed after the beneficiary and counsellor confirm the pathway and training details."},
        {"id":"follow_up","title":"Schedule a progress check-in","status":"PENDING","verification_required":False,"blocked_reason":None,"source_ids":[],"details":"Agree a follow-up date with the beneficiary."},
    ]
    plan={
        "version":"1","goal":{"interests":profile.get("interests",[]),"employment_preference":profile.get("employment_preference")},
        "pathway":{"id":pathway.id,"title":pathway.title,"source":pathway.source,"source_url":pathway.source_url},
        "steps":steps,"required_documents":[{"name":str(x),"source_id":f"pathway:{pathway.id}","verification_required":True} for x in prerequisites],
        "training":{"skills_to_develop":skills,"duration_hours":pathway.duration_hours,"source_id":f"pathway:{pathway.id}","verification_required":True},
        "training_centre":centre,"scheme":{"status":"not_identified","message":"No verified scheme or support option is attached to this plan."},
        "dependencies":[{"step_id":"confirm_training","depends_on":["verify_pathway"]},{"step_id":"prepare_documents","depends_on":["verify_pathway"]},{"step_id":"apply_or_enrol","depends_on":["confirm_training","prepare_documents"]},{"step_id":"follow_up","depends_on":["apply_or_enrol"]}],
        "estimated_timeline":None,"timeline_note":"Not available; confirm with the counsellor.","verification_required":True,
        "missing_information":missing,"status":"VERIFICATION_REQUIRED","created_at":datetime.now(timezone.utc).isoformat()
    }
    return ActionPlanPayload.model_validate(plan).model_dump()

def build_handoff(session, recommendations:list[dict], selected:dict, evidence:list):
    profile=session.profile or {}
    fields=("district","block","education_level","skills","interests","current_occupation","employment_preference","time_available","training_duration_preference","max_travel_distance","constraints")
    validated={key:profile[key] for key in fields if key in profile and profile[key] not in (None, "", [])}
    known={"district":"district","education_level":"education","skills":"skills","interests":"interests","employment_preference":"employment preference","time_available":"time availability"}
    missing=[label for key,label in known.items() if not profile.get(key)]
    uncertainties=["Pathway eligibility, current training availability, costs, and any scheme eligibility require counsellor verification."]
    if selected.get("source_notice"): uncertainties.append(selected["source_notice"])
    selected_pathway=selected.get("pathway") or {}
    questions=["Does this pathway fit the beneficiary’s goal and constraints?","Are the listed entry requirements and documents current?","Is training available and feasible in this district?","Is there a verified support option relevant to this case?"]
    # This brief is deliberately extractive and deterministic; it cannot introduce facts
    # beyond the validated profile and stored recommendation.
    summary={"summary":"Counsellor review requested for the selected pathway.","beneficiary_stated_goals":list(profile.get("interests") or [])[:12],"constraints_to_discuss":list(profile.get("constraints") or [])[:12],"verification_questions":questions,"human_review_required":True,"generated_by":"validated_data_template"}
    return {"beneficiary_summary":{"district":profile.get("district"),"language":session.language,"consent":bool(session.consent_at)},"validated_profile":validated,
        "recommendations":recommendations[:5],"selected_pathway":selected_pathway,
        "supporting_evidence":[{"evidence_id":e.id,"field":e.field,"canonical_value":e.canonical_value,"source_answer_id":e.source_answer_id,"confidence":e.confidence,"status":e.status} for e in evidence],
        "missing_information":missing,"eligibility_uncertainty":uncertainties,"training_options":[{"pathway":selected_pathway,"centre":selected.get("centre"),"skills_to_develop":selected.get("missing_skills",[])}],
        "counsellor_questions":questions,"priority":"normal","ai_brief":summary}

def handoff_view(h):
    return {"id":h.id,"session_id":h.session_id,"reason":h.reason,"priority":h.priority,"status":h.status,"case_state":h.case_state,"assigned_to":h.assigned_to,"created_at":h.created_at.isoformat() if h.created_at else None,
        "beneficiary_summary":h.beneficiary_summary or {},"validated_profile":h.validated_profile or {},"recommendations":h.recommendations or [],"selected_pathway":h.selected_pathway or {},"supporting_evidence":h.supporting_evidence or [],"missing_information":h.missing_information or [],"eligibility_uncertainty":h.eligibility_uncertainty or [],"training_options":h.training_options or [],"counsellor_questions":h.counsellor_questions or [],"ai_brief":h.ai_brief}

def can_access_case(staff:dict, handoffs:list):
    return staff.get("role")=="admin" or any(h.assigned_to==staff.get("username") for h in handoffs)

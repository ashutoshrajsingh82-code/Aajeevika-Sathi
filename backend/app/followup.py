"""Configurable follow-up scheduling and state-aware question prompts."""
from datetime import date, datetime, timedelta, timezone
from .config import FOLLOWUP_INTERVAL_DAYS

FOLLOWUP_STATES={"SCHEDULED","DUE","CONTACTED","COMPLETED","MISSED","RESCHEDULED","CANCELLED"}
OUTCOME_CATEGORIES={"TRAINING_STARTED","TRAINING_COMPLETED","JOB_FOUND","SELF_EMPLOYED","BUSINESS_STARTED","APPLICATION_SUBMITTED","APPLICATION_REJECTED","DROPPED_OUT","NO_OUTCOME_REPORTED"}

def due_date_for(days:int, today:date|None=None)->str:
    return ((today or date.today())+timedelta(days=days)).isoformat()

def parse_due_date(value:str)->date:
    try:
        parsed=date.fromisoformat(value)
        if parsed.isoformat()!=value:raise ValueError("non-canonical date")
        return parsed
    except (ValueError,TypeError) as exc:raise ValueError("due_date must use YYYY-MM-DD format") from exc

def schedule_default_followups(db,session_id:str,stage_prefix:str="pathway_check_in",row_factory=None):
    if row_factory is None:
        from .models import FollowUp
        row_factory=FollowUp
    rows=db.query(row_factory).filter_by(session_id=session_id).all()
    existing={row.schedule_offset_days for row in rows if row.schedule_offset_days is not None and row.status!="RESCHEDULED"}
    created=[]
    for offset in FOLLOWUP_INTERVAL_DAYS:
        if offset in existing:continue
        row=row_factory(session_id=session_id,stage=f"{stage_prefix}_{offset}d",due_date=due_date_for(offset),note="Check progress and record only beneficiary-reported or counsellor-verified information.",status="SCHEDULED",schedule_offset_days=offset)
        db.add(row);created.append(row)
    return created

def refresh_followup_state(row,today:date|None=None)->bool:
    current=row.status.upper()
    if current in {"COMPLETED","CONTACTED","RESCHEDULED","CANCELLED"}:return False
    due=parse_due_date(row.due_date) if row.due_date else None
    desired="MISSED" if due and due<(today or date.today()) else "DUE" if due and due<=(today or date.today()) else "SCHEDULED"
    changed=current!=desired
    if changed:row.status=desired
    return changed

def followup_questions(session,case,latest_outcome=None,pathway_title=None,client=None,session_id=None):
    selected_title=None
    if case and case.selected_pathway_id:
        selected=next((r for r in getattr(case,"_recommendations",[]) if r.get("pathway",{}).get("id")==case.selected_pathway_id),None)
        selected_title=(selected or {}).get("pathway",{}).get("title")
    if not selected_title:selected_title=pathway_title
    if not selected_title and case and case.selected_pathway_id:selected_title=case.selected_pathway_id
    category=latest_outcome.category if latest_outcome else None
    verified=bool(latest_outcome and latest_outcome.verification_status=="VERIFIED")
    if verified and category=="TRAINING_STARTED":allowed=["complete_training","support"]
    elif verified and category=="TRAINING_COMPLETED":allowed=["work_status","support"]
    elif verified and category in {"JOB_FOUND","SELF_EMPLOYED","BUSINESS_STARTED"}:allowed=["continue_work","support"]
    elif category and not verified:allowed=["verify_report","support"]
    elif case and case.selected_pathway_id:allowed=["enrolment","barrier","support"]
    else:allowed=["review_pathway","support"]
    question_templates={
        "en":{"review_pathway":"Were you able to review the recommended pathway?","enrolment":f"Were you able to enrol in {selected_title}?" if selected_title else "Were you able to enrol in the selected training?","barrier":"If not, what prevented enrolment?","complete_training":"Did you complete the recommended training?","work_status":"After training, have you found work or started a business?","continue_work":"Are you still in this work or business?","verify_report":"Would you like to share more so a counsellor can verify this update?","support":"What support would help you take the next step?"},
        "hi":{"review_pathway":"क्या आप सुझाए गए रास्ते की जानकारी देख पाए?","enrolment":f"क्या आप {selected_title} में दाखिला ले पाए?" if selected_title else "क्या आप चुने गए प्रशिक्षण में दाखिला ले पाए?","barrier":"अगर नहीं, तो दाखिले में क्या रुकावट आई?","complete_training":"क्या आपने सुझाया गया प्रशिक्षण पूरा किया?","work_status":"प्रशिक्षण के बाद क्या आपको काम मिला या आपने व्यवसाय शुरू किया?","continue_work":"क्या आप अभी भी इस काम या व्यवसाय में हैं?","verify_report":"क्या आप यह अपडेट साझा करना चाहेंगे ताकि काउंसलर इसकी पुष्टि कर सके?","support":"अगला कदम उठाने में आपको किस सहायता की ज़रूरत है?"}}
    language="hi" if session and getattr(session,"language","en")=="hi" else "en";chosen=allowed;ai_used=False
    if client is not None:
        try:
            from .ai.schemas import FollowUpQuestionSelection
            import json
            prompt=("Choose 1 to 3 question IDs only from allowed_ids. Do not create questions or infer facts. "
                    "Pick only questions relevant to this case state. Context: "+json.dumps({"allowed_ids":allowed,"selected_pathway_id":case.selected_pathway_id if case else None,"outcome":category,"outcome_verified":verified,"interview_state":session.state if session else None},separators=(",",":")))
            result=client.generate_json(prompt,FollowUpQuestionSelection,system="Select grounded follow-up question IDs. Return the required JSON only.",operation="followup_question_selection",session_id=session_id)
            if not result.question_ids or any(code not in allowed for code in result.question_ids):raise ValueError("Model selected a question outside the current case state")
            chosen=list(dict.fromkeys(result.question_ids));ai_used=True
        except Exception:
            chosen=allowed;ai_used=False
    return {"questions":[question_templates[language][code] for code in chosen],"based_on":{"selected_pathway_id":case.selected_pathway_id if case else None,"latest_outcome":category,"outcome_verified":verified,"interview_state":session.state if session else None},"generated_by":"ai_selected_grounded_templates" if ai_used else "validated_case_state","ai_used":ai_used}

def outcome_view(row):
    return {"id":row.id,"session_id":row.session_id,"outcome":row.category,"source":row.source,"timestamp":row.reported_at.isoformat() if row.reported_at else None,"verification_status":row.verification_status,"verification_note":row.verification_note,"verified_by":row.verified_by,"verified_at":row.verified_at.isoformat() if row.verified_at else None,"note":row.note}

def followup_view(row):
    return {"id":row.id,"session_id":row.session_id,"stage":row.stage,"due_date":row.due_date,"note":row.note,"status":row.status.upper(),"schedule_offset_days":row.schedule_offset_days,"rescheduled_from_id":row.rescheduled_from_id,"contacted_at":row.contacted_at.isoformat() if row.contacted_at else None,"completed_at":row.completed_at.isoformat() if row.completed_at else None}

LEGACY_OUTCOMES={"unknown":"NO_OUTCOME_REPORTED","enrolled":"TRAINING_STARTED","training":"TRAINING_STARTED","employed":"JOB_FOUND","self_employed":"SELF_EMPLOYED","not_proceeding":"NO_OUTCOME_REPORTED"}

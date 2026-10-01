import uuid
from datetime import datetime,timezone
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from .db import Base,engine,SessionLocal,get_db
from .models import InterviewSession,InterviewAnswer,ProfileEvidence,BeneficiaryCase,AuthUser,Pathway,TrainingCentre,DemandSignal,RecommendationRecord,Handoff,FollowUp,AuditLog
from .schemas import StartSession,Message,SelectPathway,FollowUpCreate,FollowUpUpdate,HandoffCreate,HandoffUpdate,DemoProfile,OutcomeUpdate,LoginBody,AIInterviewRequest,ProfileEvidenceUpdate
from .dialogue import transition,first_slot,question,SLOTS
from .recommender import recommend
from .speech import WhisperSpeechProvider,BhashiniSpeechProvider
from .config import FRONTEND_ORIGIN,DEMO_MODE,AUTO_CREATE_SCHEMA,AUTH_COOKIE_NAME,AUTH_COOKIE_HOURS,AUTH_COOKIE_SECURE
from .security import authenticate,issue_token,current_staff,require_roles,ensure_demo_accounts
from .ai.config import AISettings
from .ai.llm_client import create_llm_client,AIUnavailable,AIProviderError,InvalidModelJSON,OutputValidationError
from .ai.services.interview import InterviewAIService
from .ai.tools.interview import InterviewTools
from .ai.services.profile_builder import ProfileBuilderService,evidence_views
from .ai.services.recommendation import RecommendationExplanationService
from .semantic_matching import SEMANTIC_MODEL_VERSION

if AUTO_CREATE_SCHEMA:Base.metadata.create_all(bind=engine)
# Additive development upgrade for existing SQLite checkouts. Production deploys
# must run Alembic migrations before starting the API.
if AUTO_CREATE_SCHEMA and engine.dialect.name=="sqlite":
    with engine.begin() as conn:
        columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")}
        for name,definition in (("last_activity_at","DATETIME"),("completion_percentage","INTEGER NOT NULL DEFAULT 0"),("interview_version","VARCHAR NOT NULL DEFAULT '1'")):
            if name not in columns:conn.exec_driver_sql(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
if DEMO_MODE and AUTO_CREATE_SCHEMA:
    with SessionLocal() as db:ensure_demo_accounts(db)
app=FastAPI(title="Aajeevika Sathi API",version="0.1.0",description="Demo-mode voice livelihood pathway assistant. No government systems are connected.")
app.add_middleware(CORSMiddleware,allow_origins=[FRONTEND_ORIGIN,"http://localhost:3000"],allow_credentials=True,allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["*"])
staff_required=require_roles("admin","counsellor")
admin_required=require_roles("admin")

def log(db,action,kind,eid,detail=""):
    db.add(AuditLog(action=action,entity_type=kind,entity_id=str(eid),detail=detail))
def session_or_404(db,sid):
    s=db.get(InterviewSession,sid)
    if not s:raise HTTPException(404,"Session not found")
    return s
def session_view(s):
    return {"session_id":s.id,"language":s.language,"state":s.state,"profile":s.profile or {},"consent":bool(s.consent_at),"created_at":s.created_at.isoformat(),"completed_at":s.completed_at.isoformat() if s.completed_at else None,"completion_percentage":s.completion_percentage,"interview_version":s.interview_version}
def pathway_view(p):
    return {"id":p.id,"title":p.title,"sector":p.sector,"description":p.description,"skills":p.skills,"duration_hours":p.duration_hours,"source":p.source,"source_url":p.source_url,"self_employment":p.self_employment}

@app.get("/health")
def health():return {"status":"ok","mode":"demo" if DEMO_MODE else "configured"}

@app.post("/api/v1/auth/login")
def login(body:LoginBody,response:Response,db:Session=Depends(get_db)):
    user=authenticate(db,body.username,body.password)
    if not user:raise HTTPException(401,"Username or password is incorrect")
    user.last_login_at=datetime.now(timezone.utc);db.commit()
    response.set_cookie(AUTH_COOKIE_NAME,issue_token(user),max_age=AUTH_COOKIE_HOURS*3600,httponly=True,secure=AUTH_COOKIE_SECURE,samesite="strict",path="/")
    return {"username":user.username,"role":user.role}

@app.get("/api/v1/auth/me")
def whoami(staff:dict=Depends(current_staff)):return staff

@app.post("/api/v1/auth/logout")
def logout(response:Response):
    response.delete_cookie(AUTH_COOKIE_NAME,path="/",httponly=True,secure=AUTH_COOKIE_SECURE,samesite="strict")
    return {"logged_out":True}
@app.get("/api/v1/trades")
def trades(db:Session=Depends(get_db)):return [pathway_view(x) for x in db.query(Pathway).filter_by(active=True).all()]
@app.get("/api/v1/training-centres")
def centres(district:str|None=None,db:Session=Depends(get_db)):
    q=db.query(TrainingCentre)
    if district:q=q.filter(func.lower(TrainingCentre.district)==district.lower())
    return [{"id":c.id,"name":c.name,"district":c.district,"block":c.block,"latitude":c.latitude,"longitude":c.longitude,"address":c.address,"contact":c.contact,"accessibility":c.accessibility,"source":c.source,"pathway_ids":c.pathway_ids} for c in q.all()]

@app.post("/api/v1/interview/session")
def create_session(body:StartSession,db:Session=Depends(get_db)):
    sid=str(uuid.uuid4());s=InterviewSession(id=sid,language=body.language,state="CONSENT",profile={})
    db.add(s);log(db,"session_started","session",sid);db.commit()
    welcome={"en":"Hello, I’m Aajeevika Sathi, an AI assistant. I’ll use your answers to suggest livelihood pathways. Your audio is not stored. Do you agree?","hi":"नमस्ते, मैं आजीविका साथी AI सहायक हूँ। आपके जवाबों से आजीविका के रास्ते सुझाऊँगा। आपकी आवाज़ सेव नहीं होगी। क्या आप सहमत हैं?"}
    return {**session_view(s),"assistant_message":welcome[body.language],"next_slot":"consent"}

@app.get("/api/v1/interview/session/{sid}")
def get_session(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid);slot=first_slot(s.profile or {})
    return {**session_view(s),"next_slot":slot,"assistant_message":question(slot,s.language) if s.state=="INTERVIEW" else None}

@app.post("/api/v1/interview/session/{sid}/message")
def message(sid:str,body:Message,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    old=s.state
    if s.state=="CONSENT" and body.text.lower() in {"no","n","नहीं","नही"}:
        db.add(InterviewAnswer(session_id=sid,slot="consent",question="Do you agree to continue?",answer=body.text,normalized_answer={"consent":False},input_method=body.input_method,language=s.language));log(db,"consent_declined","session",sid);db.commit()
        return {**session_view(s),"assistant_message":"No problem. This assessment will not continue.","ended":True}
    slot="consent" if old=="CONSENT" else first_slot(s.profile or {}) if old=="INTERVIEW" else "profile_confirmation" if old=="PROFILE_REVIEW" else "message"
    ai_fallback=False
    if old=="INTERVIEW" and s.consent_at:
        try:
            settings=AISettings.from_env()
            if settings.provider!="disabled":
                tools=InterviewTools(db,s)
                tools.get_interview_state();missing=tools.get_missing_profile_fields()
                if not missing:raise ValueError("No active interview question")
                active_slot=missing[0]
                turn=InterviewAIService(create_llm_client(settings)).interpret_turn(session_id=sid,answer=body.text,language=s.language,input_method=body.input_method,profile=dict(s.profile or {}))
                extracted=turn.extracted.model_dump(exclude_unset=True)
                if not extracted and not turn.needs_clarification:raise ValueError("AI did not extract an answer")
                answer_row=tools.save_answer(raw_answer=body.text,slot=active_slot,input_method=body.input_method,normalized=extracted)
                updated=tools.update_profile(extracted,source_answer=answer_row,confidence=turn.confidence)
                next_slot=first_slot(updated)
                if next_slot=="confirm":
                    tools.complete_interview()
                    summary=", ".join(f"{k.replace('_',' ')}: {v}" for k,v in updated.items() if k!="skipped_slots")
                    prompt=(f"I heard: {summary}. Is this right? Say yes or no." if s.language=="en" else f"मैंने सुना: {summary}. क्या यह सही है? हाँ या नहीं कहें।")
                elif turn.needs_clarification and active_slot not in updated:
                    prompt=("I couldn’t determine that yet. " if s.language=="en" else "यह बात समझ नहीं आई। ")+question(active_slot,s.language)
                    next_slot=active_slot
                else:
                    prompt=tools.ask_next_question()
                    if active_slot not in updated and extracted:
                        prompt=("I’ve noted that. " if s.language=="en" else "मैंने यह जानकारी नोट की। ")+prompt
                answered=len([name for name in SLOTS if name in updated or name in updated.get("skipped_slots",[])])
                s.completion_percentage=round(answered*100/len(SLOTS));s.last_activity_at=datetime.now(timezone.utc)
                log(db,"ai_interview_turn","session",sid,"structured_output_validated")
                log(db,"message_received","session",sid,f"state:{old}; input:{body.input_method}");db.commit()
                return {**session_view(s),"profile_evidence":evidence_views(db,sid),"assistant_message":prompt,"next_slot":next_slot,"speech":{"provider":"browser","text":prompt},"ai_used":True,"ai_fallback":False}
        except (AIUnavailable,AIProviderError,InvalidModelJSON,OutputValidationError,ValueError,TypeError) as exc:
            # Fail closed for AI, then keep the existing deterministic interview usable.
            db.rollback();s=session_or_404(db,sid);old=s.state
            ai_fallback=True
    if old=="PROFILE_REVIEW" and body.text.strip().lower() in {"yes","y","हाँ","हां","हो","correct"}:
        pending=db.query(ProfileEvidence).filter_by(session_id=sid,status="pending").count()
        if pending:
            prompt=("Please confirm, correct, or remove the uncertain profile details below before continuing." if s.language=="en" else "आगे बढ़ने से पहले नीचे दी गई अनिश्चित जानकारी की पुष्टि करें, सुधारें या हटाएँ।")
            db.add(InterviewAnswer(session_id=sid,slot="profile_confirmation",question=question("confirm",s.language),answer=body.text,normalized_answer={"pending_confirmation":True},input_method=body.input_method,language=s.language))
            s.last_activity_at=datetime.now(timezone.utc);db.commit()
            return {**session_view(s),"profile_evidence":evidence_views(db,sid),"assistant_message":prompt,"next_slot":"confirm","ai_used":False,"ai_fallback":False}
    s.state,s.profile,prompt=transition(s,body.text)
    if old=="CONSENT" and s.state=="INTERVIEW":s.consent_at=datetime.now(timezone.utc);log(db,"consent_granted","session",sid)
    normalized=(s.profile or {}).get(slot) if slot not in {"consent","profile_confirmation","message"} else ({"consent":True} if slot=="consent" and s.consent_at else {"confirmed":s.state=="RECOMMENDATION"} if slot=="profile_confirmation" else {"state":s.state})
    if slot not in {"consent","profile_confirmation","message"} and slot not in (s.profile or {}).get("skipped_slots",[]):
        normalized=(s.profile or {}).get(slot)
    question_text="Do you agree to continue?" if slot=="consent" else question("confirm",s.language) if slot=="profile_confirmation" else question(slot,s.language)
    db.add(InterviewAnswer(session_id=sid,slot=slot,question=question_text,answer=body.text,normalized_answer={"value":normalized},input_method=body.input_method,language=s.language))
    answered=len([slot_name for slot_name in SLOTS if slot_name in (s.profile or {}) or slot_name in (s.profile or {}).get("skipped_slots",[])])
    s.completion_percentage=round(answered*100/len(SLOTS))
    s.last_activity_at=datetime.now(timezone.utc)
    if old!=s.state:log(db,"state_transition","session",sid,f"{old}->{s.state}")
    if old=="INTERVIEW" and s.state=="PROFILE_REVIEW":log(db,"profile_completed","session",sid)
    log(db,"message_received","session",sid,f"state:{old}; input:{body.input_method}");db.commit()
    if ai_fallback:prompt=("AI interview unavailable; continuing with the guided questions. " if s.language=="en" else "AI इंटरव्यू उपलब्ध नहीं है; सामान्य सवाल जारी हैं। ")+prompt
    return {**session_view(s),"assistant_message":prompt,"next_slot":first_slot(s.profile or {}),"speech":{"provider":"browser","text":prompt},"ai_used":False,"ai_fallback":ai_fallback}

@app.post("/api/v1/interview/session/{sid}/ai-interpret")
def ai_interpret(sid:str,body:AIInterviewRequest,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required before AI processing")
    if s.state!="INTERVIEW":raise HTTPException(409,"AI interpretation is available only during the interview")
    expected_slot=first_slot(s.profile or {})
    if body.slot!=expected_slot:raise HTTPException(409,"Answer slot does not match the current interview question")
    try:
        client=create_llm_client(AISettings.from_env())
        result=InterviewAIService(client).interpret(session_id=sid,slot=body.slot,answer=body.answer,language=s.language,input_method=body.input_method)
        return {"available":True,"structured":result.model_dump(),"stored":False,"notice":"AI interpretation is optional and not written to the beneficiary profile. Confirm or correct all details in the normal interview flow."}
    except (AIUnavailable,AIProviderError,InvalidModelJSON,OutputValidationError,ValueError) as exc:
        raise HTTPException(503,{"code":"ai_unavailable_or_invalid","message":"AI interpretation is unavailable. Continue with the regular text or voice interview; no profile data was changed."}) from exc

@app.post("/api/v1/interview/session/{sid}/complete")
def complete(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    if s.state!="RECOMMENDATION":raise HTTPException(409,"Confirm the profile before recommendations")
    if s.completed_at:
        existing_case=db.query(BeneficiaryCase).filter_by(session_id=s.id).one_or_none()
        return {"session":session_view(s),"recommendations":get_recommendations(sid,db)["recommendations"],"action_plan":existing_case.action_plan if existing_case else [],"case":case_view(existing_case) if existing_case else None}
    profile=s.profile or {}
    missing=[name for name,ok in (("district",bool(profile.get("district"))), ("skills or interests",bool(profile.get("skills") or profile.get("interests")))) if not ok]
    if missing:raise HTTPException(422,{"message":"A few details are needed before matching.","missing":missing})
    try:
        recs=make_recommendations(s,db)
        plan=action_plan(recs[0] if recs else None)
        s.completed_at=datetime.now(timezone.utc);s.state="RECOMMENDATION"
        case=db.query(BeneficiaryCase).filter_by(session_id=s.id).one_or_none()
        if not case:case=BeneficiaryCase(session_id=s.id)
        case.status="recommendation";case.action_plan=plan;db.add(case)
        if not db.query(FollowUp).filter_by(session_id=s.id).first():
            db.add(FollowUp(session_id=s.id,stage="recommendation_check_in",due_date="",note="Check whether the beneficiary wants to continue."))
        log(db,"interview_completed","session",s.id);db.commit()
    except Exception:
        db.rollback();raise
    return {"session":session_view(s),"recommendations":recs,"action_plan":plan,"case":case_view(case)}

def make_recommendations(s,db):
    options=recommend(s.profile or {},db.query(Pathway).filter_by(active=True).all(),db.query(TrainingCentre).all(),db.query(DemandSignal).all())
    explanation_client=None;explanation_model="deterministic-template-v1"
    try:
        settings=AISettings.from_env()
        if settings.provider!="disabled":
            explanation_client=create_llm_client(settings);explanation_model=settings.model
    except (ValueError,AIUnavailable,AIProviderError):
        explanation_client=None
    records=[];views=[]
    for item in options:
        p=item.pop("pathway")
        centre=item.pop("centre")
        item["pathway"]=pathway_view(p)
        item["centre"]={"id":centre.id,"name":centre.name,"district":centre.district,"block":centre.block,"latitude":centre.latitude,"longitude":centre.longitude,"address":centre.address,"contact":centre.contact,"source":centre.source} if centre else None
        item["source_notice"]="DEMO SAMPLE — verify course, eligibility, availability and local demand with an authorised counsellor."
        component=item["component_scores"];semantic=item["semantic_match"];demand_signal=item["demand_signal"];feasibility=item["feasibility"];sources=item["data_sources"]
        stated_interests=(s.profile or {}).get("interests",[]) if isinstance((s.profile or {}).get("interests",[]),list) else [str((s.profile or {}).get("interests"))]
        context={"pathway_id":str(p.id)[:120],"title":str(p.title or "Unknown pathway")[:200],"sector":str(p.sector or "Unspecified")[:200],"description":str(p.description or "")[:1000],"deterministic_score":item["score"],
            "interest_score":component["interest"],"skills_score":component["skills"],"demand_score":component["district_demand"],"feasibility_score":component["feasibility"],"preference_score":component["employment_preference"],
            "semantic_interest_similarity":semantic["interest_similarity"],"semantic_skill_similarity":semantic["skill_similarity"],"stated_interests":[str(x)[:200] for x in stated_interests[:20] if x],
            "matched_skills":[str(x)[:200] for x in item["matched_skills"][:30]],"missing_skills":[str(x)[:200] for x in item["missing_skills"][:30]],"duration_hours":p.duration_hours,"minimum_education":str(p.min_education or "not specified")[:200],"prerequisites":[str(x)[:200] for x in (p.prerequisites or [])[:30]],
            "demand_label":str(demand_signal["label"])[:200],"demand_source":str(demand_signal["source"])[:200] if demand_signal["source"] else None,"centre_found":feasibility["centre_found"],"approximate_distance_km":item["distance_km"],"within_travel_limit":feasibility["within_travel_limit"],
            "preference_fit":str(feasibility["preference_fit"])[:200],"data_sources":[str(x)[:200] for x in sources.values() if x][:8],"model_version":SEMANTIC_MODEL_VERSION}
        ai_explanation=RecommendationExplanationService().explain(context,explanation_client,session_id=s.id)
        ai_explanation["model"] = explanation_model if ai_explanation["generated_by"]=="ai_assisted_grounded_choice" else "deterministic-template-v1"
        item["ai_explanation"]=ai_explanation
        item["model_version"]=f"deterministic-score-v1+{SEMANTIC_MODEL_VERSION}+{ai_explanation['model']}"
        records.append(RecommendationRecord(session_id=s.id,pathway_id=p.id,explanation={"explanation":item["explanation"],"recommendation":item},score=item["score"],component_scores=component,matched_skills=item["matched_skills"],missing_skills=item["missing_skills"],demand_signal=demand_signal,feasibility=feasibility,data_sources=sources,model_version=item["model_version"]))
        views.append(item)
    db.add_all(records);log(db,"recommendations_generated","session",s.id);return views

def case_view(case):
    return {"id":case.id,"session_id":case.session_id,"status":case.status,"selected_pathway_id":case.selected_pathway_id,"action_plan":case.action_plan or [],"outcome":case.outcome,"outcome_note":case.outcome_note,"updated_at":case.updated_at.isoformat() if case.updated_at else None}

def action_plan(rec):
    if not rec:return []
    return ["Discuss this demo pathway with a counsellor.","Confirm current course, entry requirements, fees and dates with the centre.","Ask whether prior skills can be assessed before training.","Agree on a training and livelihood plan that fits your time and travel needs.","Create a follow-up check-in with your counsellor."]

@app.post("/api/v1/recommendations/generate")
def generate(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    if s.state not in {"RECOMMENDATION","PATHWAY_SELECTED","COUNSELLOR_HANDOFF","FOLLOW_UP","COMPLETED"}:raise HTTPException(409,"Finish and confirm interview first")
    result=make_recommendations(s,db);db.commit();return {"recommendations":result}

@app.get("/api/v1/recommendations/{sid}")
def get_recommendations(sid:str,db:Session=Depends(get_db)):
    session_or_404(db,sid)
    rows=db.query(RecommendationRecord).filter_by(session_id=sid).order_by(RecommendationRecord.id.desc()).all()
    seen=set();out=[]
    for row in rows:
        if row.pathway_id in seen:continue
        seen.add(row.pathway_id);p=db.get(Pathway,row.pathway_id)
        if p:
            saved=row.explanation.get("recommendation")
            if saved:out.append(saved)
            else:out.append({"pathway":pathway_view(p),"explanation":row.explanation,"already_has":[],"to_develop":p.skills or [],"centre":None,"distance_km":None,"demand":"Not available" if row.explanation.get("demand") is None else row.explanation.get("demand"),"eligibility":"Needs counsellor verification","within_travel_limit":True,"source_notice":"DEMO SAMPLE — verify details before use."})
    return {"recommendations":out}

@app.get("/api/v1/profile/{sid}")
def profile(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    return {"beneficiary_id":s.id,"session_id":s.id,"language":s.language,"consent_status":True,**(s.profile or {}),"evidence":evidence_views(db,sid)}

@app.patch("/api/v1/profile/{sid}/evidence/{evidence_id}")
def resolve_profile_evidence(sid:str,evidence_id:int,body:ProfileEvidenceUpdate,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    evidence=db.get(ProfileEvidence,evidence_id)
    if not evidence or evidence.session_id!=sid:raise HTTPException(404,"Profile evidence not found")
    try:updated=ProfileBuilderService().resolve(db,s,evidence,body.action,body.value)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    s.last_activity_at=datetime.now(timezone.utc);log(db,"profile_evidence_resolved","session",sid,f"field:{evidence.field}; action:{body.action}");db.commit()
    return {"session_id":sid,"profile":updated,"evidence":evidence_views(db,sid)}

@app.post("/api/v1/demo/profile")
def demo_profile(body:DemoProfile,db:Session=Depends(get_db)):
    sid=str(uuid.uuid4());p=body.model_dump();language=p.pop("language")
    s=InterviewSession(id=sid,language=language,state="RECOMMENDATION",profile=p,consent_at=datetime.now(timezone.utc),completed_at=datetime.now(timezone.utc))
    db.add(s);log(db,"demo_profile_loaded","session",sid,"synthetic persona; not a real beneficiary");db.commit()
    recs=make_recommendations(s,db)
    plan=action_plan(recs[0] if recs else None);case=BeneficiaryCase(session_id=sid,status="recommendation",action_plan=plan);db.add(case);db.add(FollowUp(session_id=sid,stage="recommendation_check_in",note="Synthetic demo follow-up."));db.commit()
    return {"session":session_view(s),"recommendations":recs,"action_plan":plan,"case":case_view(case),"demo_persona":True}

@app.post("/api/v1/recommendations/select")
def select_pathway(body:SelectPathway,db:Session=Depends(get_db)):
    s=session_or_404(db,body.session_id)
    row=db.query(RecommendationRecord).filter_by(session_id=body.session_id,pathway_id=body.pathway_id).order_by(RecommendationRecord.id.desc()).first()
    if not row:raise HTTPException(404,"Generate this session's recommendations first")
    row.selected=True
    case=db.query(BeneficiaryCase).filter_by(session_id=body.session_id).one_or_none()
    if not case:case=BeneficiaryCase(session_id=body.session_id,action_plan=action_plan(None))
    case.selected_pathway_id=body.pathway_id;case.status="counsellor_handoff";case.action_plan=action_plan({"selected":body.pathway_id});db.add(case)
    handoff=db.query(Handoff).filter_by(session_id=s.id).filter(Handoff.status!="resolved").first()
    if not handoff:
        handoff=Handoff(session_id=s.id,reason="Pathway selected; counsellor to verify availability and next steps.",priority="normal");db.add(handoff)
    if not db.query(FollowUp).filter_by(session_id=s.id).first():db.add(FollowUp(session_id=s.id,stage="pathway_selected",note="Counsellor to check selected pathway and next steps."))
    old=s.state;s.state="PATHWAY_SELECTED";log(db,"pathway_selected","recommendation",row.id,body.pathway_id)
    if old!=s.state:log(db,"state_transition","session",s.id,f"{old}->{s.state}")
    s.state="COUNSELLOR_HANDOFF";log(db,"state_transition","session",s.id,"PATHWAY_SELECTED->COUNSELLOR_HANDOFF")
    db.commit()
    return {"selected":True,"action_plan":case.action_plan,"case":case_view(case),"handoff_id":handoff.id,"session_state":s.state}

@app.get("/api/v1/case/{sid}")
def get_case(sid:str,db:Session=Depends(get_db)):
    session_or_404(db,sid)
    case=db.query(BeneficiaryCase).filter_by(session_id=sid).one_or_none()
    if not case:raise HTTPException(404,"Case is not available until the profile is completed")
    return {"case":case_view(case),"session":session_view(db.get(InterviewSession,sid)),"recommendations":get_recommendations(sid,db)["recommendations"],"handoffs":[{"id":h.id,"reason":h.reason,"priority":h.priority,"status":h.status} for h in db.query(Handoff).filter_by(session_id=sid).all()],"followups":[{"id":f.id,"stage":f.stage,"due_date":f.due_date,"note":f.note,"status":f.status} for f in db.query(FollowUp).filter_by(session_id=sid).all()]}

@app.get("/api/v1/staff/case/{sid}")
def get_staff_case(sid:str,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    return get_case(sid,db)

@app.get("/api/v1/staff/profile/{sid}")
def get_staff_profile(sid:str,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    return profile(sid,db)

@app.patch("/api/v1/case/{sid}/outcome")
def update_case_outcome(sid:str,body:OutcomeUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    session_or_404(db,sid);case=db.query(BeneficiaryCase).filter_by(session_id=sid).one_or_none()
    if not case:raise HTTPException(404,"Case not found")
    case.outcome=body.outcome;case.outcome_note=body.note;case.status="completed" if body.outcome in {"employed","self_employed"} else "follow_up" if body.outcome=="training" else body.outcome
    s=db.get(InterviewSession,sid);old=s.state
    if case.status=="completed":s.state="COMPLETED"
    elif case.status=="follow_up":s.state="FOLLOW_UP"
    if old!=s.state:log(db,"state_transition","session",sid,f"{old}->{s.state}")
    log(db,"case_outcome_updated","case",case.id,body.outcome);db.commit();return {"case":case_view(case)}

@app.post("/api/v1/speech/transcribe")
async def transcribe(file:UploadFile=File(...),language:str="en"):
    if language not in {"en","hi"}:raise HTTPException(400,"Language must be en or hi")
    if file.content_type not in {"audio/webm","audio/ogg","audio/wav","audio/mpeg","audio/mp4","application/octet-stream"}:raise HTTPException(415,"Upload a supported audio file")
    audio=await file.read(10*1024*1024+1)
    if len(audio)>10*1024*1024:raise HTTPException(413,"Audio upload exceeds 10 MB")
    if not audio:raise HTTPException(400,"Audio file is empty")
    provider=WhisperSpeechProvider();result=await provider.transcribe(audio,file.filename or "recording.webm",language)
    # Audio bytes are used only in memory and are never persisted.
    return {**result,"audio_retained":False}

@app.post("/api/v1/speech/synthesize")
def synthesize(text:str,language:str="en"):
    if len(text)>2000:raise HTTPException(413,"Speech text too long")
    return {"text":text,"provider":"browser-speech-synthesis","audio_url":None,"language":language}

@app.post("/api/v1/handoff")
def create_handoff(body:HandoffCreate,db:Session=Depends(get_db)):
    s=session_or_404(db,body.session_id);h=Handoff(session_id=s.id,reason=body.reason,priority=body.priority[:20]);db.add(h)
    case=db.query(BeneficiaryCase).filter_by(session_id=s.id).one_or_none()
    if case:case.status="counsellor_handoff"
    old=s.state;s.state="COUNSELLOR_HANDOFF";log(db,"handoff_created","session",s.id,body.reason)
    if old!=s.state:log(db,"state_transition","session",s.id,f"{old}->{s.state}")
    db.commit()
    return {"id":h.id,"status":h.status,"message":"Your request is in the demo counsellor queue."}
@app.get("/api/v1/handoff/queue")
def handoff_queue(db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    return [{"id":h.id,"session_id":h.session_id,"reason":h.reason,"priority":h.priority,"status":h.status,"language":db.get(InterviewSession,h.session_id).language,"district":(db.get(InterviewSession,h.session_id).profile or {}).get("district","—"),"created_at":h.created_at.isoformat()} for h in db.query(Handoff).order_by(Handoff.created_at.desc()).all()]
@app.patch("/api/v1/handoff/{handoff_id}")
def update_handoff(handoff_id:int,body:HandoffUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    h=db.get(Handoff,handoff_id)
    if not h:raise HTTPException(404,"Handoff not found")
    h.status=body.status;log(db,"handoff_status_updated","handoff",h.id,body.status);db.commit();return {"id":h.id,"status":h.status}

@app.post("/api/v1/followups")
def create_followup(body:FollowUpCreate,db:Session=Depends(get_db)):
    session_or_404(db,body.session_id);f=FollowUp(session_id=body.session_id,stage=body.stage[:40],due_date=body.due_date[:40],note=body.note[:500]);db.add(f);log(db,"followup_created","session",body.session_id,body.stage);db.commit()
    return {"id":f.id,"session_id":f.session_id,"stage":f.stage,"due_date":f.due_date,"status":f.status}
@app.patch("/api/v1/followups/{followup_id}")
def update_followup(followup_id:int,body:FollowUpUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    f=db.get(FollowUp,followup_id)
    if not f:raise HTTPException(404,"Follow-up not found")
    f.status=body.status;case=db.query(BeneficiaryCase).filter_by(session_id=f.session_id).one_or_none()
    if case and body.status=="complete":
        case.status="follow_up";s=db.get(InterviewSession,f.session_id);old=s.state;s.state="FOLLOW_UP"
        if old!=s.state:log(db,"state_transition","session",s.id,f"{old}->{s.state}")
    log(db,"followup_status_updated","followup",f.id,body.status);db.commit();return {"id":f.id,"status":f.status}
@app.get("/api/v1/followups")
def followups(session_id:str|None=None,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    q=db.query(FollowUp)
    if session_id:q=q.filter_by(session_id=session_id)
    return [{"id":f.id,"session_id":f.session_id,"stage":f.stage,"due_date":f.due_date,"note":f.note,"status":f.status} for f in q.order_by(FollowUp.created_at.desc()).all()]

@app.get("/api/v1/beneficiaries")
def beneficiaries(q:str|None=None,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).order_by(InterviewSession.created_at.desc()).limit(100).all()
    if q:sessions=[s for s in sessions if q.lower() in str(s.profile).lower() or q.lower() in s.id.lower()]
    return [{"id":s.id,"language":s.language,"state":s.state,"district":(s.profile or {}).get("district","—"),"interest":", ".join((s.profile or {}).get("interests",[])) if isinstance((s.profile or {}).get("interests"),list) else (s.profile or {}).get("interests","—"),"created_at":s.created_at.isoformat()} for s in sessions]

@app.get("/api/v1/admin/analytics")
def analytics(db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).all();total=len(sessions)
    language={};district={};interests={}
    for s in sessions:
        language[s.language]=language.get(s.language,0)+1;p=s.profile or {};d=p.get("district","Unknown");district[d]=district.get(d,0)+1
        vals=p.get("interests",[]);vals=vals if isinstance(vals,list) else [vals]
        for v in vals:interests[str(v)]=interests.get(str(v),0)+1
    rec_count=db.query(RecommendationRecord).count();selected=db.query(RecommendationRecord).filter_by(selected=True).count();enrolled=db.query(BeneficiaryCase).filter(BeneficiaryCase.outcome.in_(["enrolled","training"])).count();placed=db.query(BeneficiaryCase).filter(BeneficiaryCase.outcome.in_(["employed","self_employed"])).count()
    demand=db.query(DemandSignal).all()
    # Small groups are suppressed; no raw beneficiary-level records leave this endpoint.
    def suppress(d):return {k:(v if v>=5 else None) for k,v in d.items()}
    return {"counts":{"beneficiaries_reached":total if total>=5 else None,"profiles_completed":sum(s.completed_at is not None for s in sessions) if sum(s.completed_at is not None for s in sessions)>=5 else None,"recommendations_generated":rec_count if rec_count>=5 else None,"counsellor_handoffs":db.query(Handoff).count() if db.query(Handoff).count()>=5 else None},"languages":suppress(language),"districts":suppress(district),"interests":suppress(interests),"funnel":[{"stage":"profiles","count":total if total>=5 else None},{"stage":"recommendations","count":rec_count if rec_count>=5 else None},{"stage":"selected","count":selected if selected>=5 else None},{"stage":"enrolled / training","count":enrolled if enrolled>=5 else None},{"stage":"employed / self-employed","count":placed if placed>=5 else None}],"demand_capacity":[{"district":d.district,"sector":d.sector,"demand":d.demand_label,"sample_capacity":d.capacity,"source":d.source,"year":d.year} for d in demand],"data_notice":"Session analytics are suppressed below 5. Capacity/demand values are synthetic demo samples, not official statistics.","generated_at":datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/admin/skill-gaps")
def skill_gaps(db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    counts={}
    for r in db.query(RecommendationRecord).all():
        p=db.get(Pathway,r.pathway_id)
        if p:
            for skill in p.skills:counts[skill]=counts.get(skill,0)+1
    return {"skills":[{"skill":k,"count":v if v>=5 else None} for k,v in sorted(counts.items(),key=lambda x:-x[1])],"notice":"Counts below 5 suppressed. Gaps are counted from generated recommendations, not verified training assessments."}

@app.get("/api/v1/admin/demand")
def demand(db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    return [{"district":d.district,"sector":d.sector,"demand":d.demand_label,"sample_capacity":d.capacity,"source":d.source,"year":d.year} for d in db.query(DemandSignal).all()]

@app.delete("/api/v1/interview/session/{sid}")
def withdraw(sid:str,db:Session=Depends(get_db)):
    s=db.get(InterviewSession,sid)
    if s:
        db.query(ProfileEvidence).filter_by(session_id=sid).delete();db.query(InterviewAnswer).filter_by(session_id=sid).delete();db.query(BeneficiaryCase).filter_by(session_id=sid).delete();db.query(RecommendationRecord).filter_by(session_id=sid).delete();db.query(Handoff).filter_by(session_id=sid).delete();db.query(FollowUp).filter_by(session_id=sid).delete();db.delete(s);log(db,"session_deleted","session",sid);db.commit()
    return {"deleted":True}

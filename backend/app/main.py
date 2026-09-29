import uuid
from datetime import datetime,timezone
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from .db import Base,engine,SessionLocal
from .models import InterviewSession,Pathway,TrainingCentre,DemandSignal,RecommendationRecord,Handoff,FollowUp,AuditLog
from .schemas import StartSession,Message,SelectPathway,FollowUpCreate,FollowUpUpdate,HandoffCreate,HandoffUpdate,DemoProfile
from .dialogue import transition,first_slot,question
from .recommender import recommend
from .speech import WhisperSpeechProvider,BhashiniSpeechProvider
from .config import FRONTEND_ORIGIN,DEMO_MODE

Base.metadata.create_all(bind=engine)
app=FastAPI(title="Aajeevika Sathi API",version="0.1.0",description="Demo-mode voice livelihood pathway assistant. No government systems are connected.")
app.add_middleware(CORSMiddleware,allow_origins=[FRONTEND_ORIGIN,"http://localhost:3000"],allow_credentials=True,allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["*"])

def get_db():
    db=SessionLocal()
    try:yield db
    finally:db.close()
def log(db,action,kind,eid,detail=""):
    db.add(AuditLog(action=action,entity_type=kind,entity_id=str(eid),detail=detail))
def session_or_404(db,sid):
    s=db.get(InterviewSession,sid)
    if not s:raise HTTPException(404,"Session not found")
    return s
def session_view(s):
    return {"session_id":s.id,"language":s.language,"state":s.state,"profile":s.profile or {},"consent":bool(s.consent_at),"created_at":s.created_at.isoformat()}
def pathway_view(p):
    return {"id":p.id,"title":p.title,"sector":p.sector,"description":p.description,"skills":p.skills,"duration_hours":p.duration_hours,"source":p.source,"source_url":p.source_url,"self_employment":p.self_employment}

@app.get("/health")
def health():return {"status":"ok","mode":"demo" if DEMO_MODE else "configured"}
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
    if s.state=="CONSENT" and body.text.lower() in {"no","n","नहीं","नही"}:return {**session_view(s),"assistant_message":"No problem. This assessment will not continue.","ended":True}
    if s.state=="CONSENT":s.consent_at=datetime.now(timezone.utc)
    old=s.state;s.state,s.profile,prompt=transition(s,body.text)
    if old=="INTERVIEW" and s.state=="CONFIRMATION":log(db,"profile_completed","session",sid)
    log(db,"message_received","session",sid,f"state:{old}");db.commit()
    return {**session_view(s),"assistant_message":prompt,"next_slot":first_slot(s.profile or {}),"speech":{"provider":"browser","text":prompt}}

@app.post("/api/v1/interview/session/{sid}/complete")
def complete(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    if s.state!="RECOMMENDATION":raise HTTPException(409,"Confirm the profile before recommendations")
    recs=make_recommendations(s,db)
    return {"session":session_view(s),"recommendations":recs,"action_plan":action_plan(recs[0] if recs else None)}

def make_recommendations(s,db):
    options=recommend(s.profile or {},db.query(Pathway).filter_by(active=True).all(),db.query(TrainingCentre).all(),db.query(DemandSignal).all())
    records=[];views=[]
    for item in options:
        p=item.pop("pathway");records.append(RecommendationRecord(session_id=s.id,pathway_id=p.id,explanation=item["explanation"]))
        centre=item.pop("centre")
        item["pathway"]=pathway_view(p)
        item["centre"]={"id":centre.id,"name":centre.name,"district":centre.district,"block":centre.block,"latitude":centre.latitude,"longitude":centre.longitude,"address":centre.address,"contact":centre.contact,"source":centre.source} if centre else None
        item["source_notice"]="DEMO SAMPLE — verify course, eligibility, availability and local demand with an authorised counsellor."
        views.append(item)
    db.add_all(records);log(db,"recommendations_generated","session",s.id);db.commit();return views

def action_plan(rec):
    if not rec:return []
    return ["Discuss this demo pathway with a counsellor.","Confirm current course, entry requirements, fees and dates with the centre.","Ask whether prior skills can be assessed before training.","Agree on a training and livelihood plan that fits your time and travel needs.","Create a follow-up check-in with your counsellor."]

@app.post("/api/v1/recommendations/generate")
def generate(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    if s.state not in {"RECOMMENDATION","COMPLETE"}:raise HTTPException(409,"Finish and confirm interview first")
    return {"recommendations":make_recommendations(s,db)}

@app.get("/api/v1/recommendations/{sid}")
def get_recommendations(sid:str,db:Session=Depends(get_db)):
    session_or_404(db,sid)
    rows=db.query(RecommendationRecord).filter_by(session_id=sid).order_by(RecommendationRecord.id.desc()).all()
    seen=set();out=[]
    for row in rows:
        if row.pathway_id in seen:continue
        seen.add(row.pathway_id);p=db.get(Pathway,row.pathway_id)
        if p:out.append({"pathway":pathway_view(p),"explanation":row.explanation,"already_has":[],"to_develop":p.skills or [],"centre":None,"distance_km":None,"demand":"Not available" if row.explanation.get("demand") is None else row.explanation.get("demand"),"eligibility":"Needs counsellor verification","within_travel_limit":True,"source_notice":"DEMO SAMPLE — verify details before use."})
    return {"recommendations":out}

@app.get("/api/v1/profile/{sid}")
def profile(sid:str,db:Session=Depends(get_db)):
    s=session_or_404(db,sid)
    if not s.consent_at:raise HTTPException(403,"Consent is required")
    return {"beneficiary_id":s.id,"session_id":s.id,"language":s.language,"consent_status":True,**(s.profile or {})}

@app.post("/api/v1/demo/profile")
def demo_profile(body:DemoProfile,db:Session=Depends(get_db)):
    sid=str(uuid.uuid4());p=body.model_dump();language=p.pop("language")
    s=InterviewSession(id=sid,language=language,state="RECOMMENDATION",profile=p,consent_at=datetime.now(timezone.utc),completed_at=datetime.now(timezone.utc))
    db.add(s);log(db,"demo_profile_loaded","session",sid,"synthetic persona; not a real beneficiary");db.commit()
    recs=make_recommendations(s,db)
    return {"session":session_view(s),"recommendations":recs,"action_plan":action_plan(recs[0] if recs else None),"demo_persona":True}

@app.post("/api/v1/recommendations/select")
def select_pathway(body:SelectPathway,db:Session=Depends(get_db)):
    session_or_404(db,body.session_id)
    row=db.query(RecommendationRecord).filter_by(session_id=body.session_id,pathway_id=body.pathway_id).order_by(RecommendationRecord.id.desc()).first()
    if not row:raise HTTPException(404,"Generate this session's recommendations first")
    row.selected=True;log(db,"pathway_selected","recommendation",row.id,body.pathway_id);db.commit()
    return {"selected":True,"action_plan":action_plan({"selected":body.pathway_id})}

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
    s=session_or_404(db,body.session_id);h=Handoff(session_id=s.id,reason=body.reason,priority=body.priority[:20]);db.add(h);log(db,"handoff_created","session",s.id,body.reason);db.commit()
    return {"id":h.id,"status":h.status,"message":"Your request is in the demo counsellor queue."}
@app.get("/api/v1/handoff/queue")
def handoff_queue(db:Session=Depends(get_db)):
    return [{"id":h.id,"session_id":h.session_id,"reason":h.reason,"priority":h.priority,"status":h.status,"language":db.get(InterviewSession,h.session_id).language,"district":(db.get(InterviewSession,h.session_id).profile or {}).get("district","—"),"created_at":h.created_at.isoformat()} for h in db.query(Handoff).order_by(Handoff.created_at.desc()).all()]
@app.patch("/api/v1/handoff/{handoff_id}")
def update_handoff(handoff_id:int,body:HandoffUpdate,db:Session=Depends(get_db)):
    h=db.get(Handoff,handoff_id)
    if not h:raise HTTPException(404,"Handoff not found")
    h.status=body.status;db.commit();return {"id":h.id,"status":h.status}

@app.post("/api/v1/followups")
def create_followup(body:FollowUpCreate,db:Session=Depends(get_db)):
    session_or_404(db,body.session_id);f=FollowUp(session_id=body.session_id,stage=body.stage[:40],due_date=body.due_date[:40],note=body.note[:500]);db.add(f);log(db,"followup_created","session",body.session_id,body.stage);db.commit()
    return {"id":f.id,"session_id":f.session_id,"stage":f.stage,"due_date":f.due_date,"status":f.status}
@app.patch("/api/v1/followups/{followup_id}")
def update_followup(followup_id:int,body:FollowUpUpdate,db:Session=Depends(get_db)):
    f=db.get(FollowUp,followup_id)
    if not f:raise HTTPException(404,"Follow-up not found")
    f.status=body.status;db.commit();return {"id":f.id,"status":f.status}
@app.get("/api/v1/followups")
def followups(session_id:str|None=None,db:Session=Depends(get_db)):
    q=db.query(FollowUp)
    if session_id:q=q.filter_by(session_id=session_id)
    return [{"id":f.id,"session_id":f.session_id,"stage":f.stage,"due_date":f.due_date,"note":f.note,"status":f.status} for f in q.order_by(FollowUp.created_at.desc()).all()]

@app.get("/api/v1/beneficiaries")
def beneficiaries(q:str|None=None,db:Session=Depends(get_db)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).order_by(InterviewSession.created_at.desc()).limit(100).all()
    if q:sessions=[s for s in sessions if q.lower() in str(s.profile).lower() or q.lower() in s.id.lower()]
    return [{"id":s.id,"language":s.language,"state":s.state,"district":(s.profile or {}).get("district","—"),"interest":", ".join((s.profile or {}).get("interests",[])) if isinstance((s.profile or {}).get("interests"),list) else (s.profile or {}).get("interests","—"),"created_at":s.created_at.isoformat()} for s in sessions]

@app.get("/api/v1/admin/analytics")
def analytics(db:Session=Depends(get_db)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).all();total=len(sessions)
    language={};district={};interests={}
    for s in sessions:
        language[s.language]=language.get(s.language,0)+1;p=s.profile or {};d=p.get("district","Unknown");district[d]=district.get(d,0)+1
        vals=p.get("interests",[]);vals=vals if isinstance(vals,list) else [vals]
        for v in vals:interests[str(v)]=interests.get(str(v),0)+1
    rec_count=db.query(RecommendationRecord).count();selected=db.query(RecommendationRecord).filter_by(selected=True).count();enrolled=db.query(FollowUp).filter(FollowUp.stage.in_(["enrolled","training","completed"])).count();placed=db.query(FollowUp).filter(FollowUp.stage.in_(["placed","enterprise_started"])).count()
    demand=db.query(DemandSignal).all()
    # Small groups are suppressed; no raw beneficiary-level records leave this endpoint.
    def suppress(d):return {k:(v if v>=5 else None) for k,v in d.items()}
    return {"counts":{"beneficiaries_reached":total if total>=5 else None,"profiles_completed":sum(s.state in {"RECOMMENDATION","COMPLETE"} for s in sessions) if sum(s.state in {"RECOMMENDATION","COMPLETE"} for s in sessions)>=5 else None,"recommendations_generated":rec_count if rec_count>=5 else None,"counsellor_handoffs":db.query(Handoff).count() if db.query(Handoff).count()>=5 else None},"languages":suppress(language),"districts":suppress(district),"interests":suppress(interests),"funnel":[{"stage":"profiles","count":total if total>=5 else None},{"stage":"recommendations","count":rec_count if rec_count>=5 else None},{"stage":"selected","count":selected if selected>=5 else None},{"stage":"enrolled","count":enrolled if enrolled>=5 else None},{"stage":"placed / enterprise","count":placed if placed>=5 else None}],"demand_capacity":[{"district":d.district,"sector":d.sector,"demand":d.demand_label,"sample_capacity":d.capacity,"source":d.source,"year":d.year} for d in demand],"data_notice":"Session analytics are suppressed below 5. Capacity/demand values are synthetic demo samples, not official statistics.","generated_at":datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/admin/skill-gaps")
def skill_gaps(db:Session=Depends(get_db)):
    counts={}
    for r in db.query(RecommendationRecord).all():
        p=db.get(Pathway,r.pathway_id)
        if p:
            for skill in p.skills:counts[skill]=counts.get(skill,0)+1
    return {"skills":[{"skill":k,"count":v if v>=5 else None} for k,v in sorted(counts.items(),key=lambda x:-x[1])],"notice":"Counts below 5 suppressed. Gaps are counted from generated recommendations, not verified training assessments."}

@app.get("/api/v1/admin/demand")
def demand(db:Session=Depends(get_db)):
    return [{"district":d.district,"sector":d.sector,"demand":d.demand_label,"sample_capacity":d.capacity,"source":d.source,"year":d.year} for d in db.query(DemandSignal).all()]

@app.delete("/api/v1/interview/session/{sid}")
def withdraw(sid:str,db:Session=Depends(get_db)):
    s=db.get(InterviewSession,sid)
    if s:
        db.query(RecommendationRecord).filter_by(session_id=sid).delete();db.query(Handoff).filter_by(session_id=sid).delete();db.query(FollowUp).filter_by(session_id=sid).delete();db.delete(s);log(db,"session_deleted","session",sid);db.commit()
    return {"deleted":True}

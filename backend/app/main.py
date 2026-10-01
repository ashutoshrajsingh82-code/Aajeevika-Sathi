import uuid
import json
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone,date
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Form,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from .db import Base,engine,SessionLocal,get_db
from .models import InterviewSession,InterviewAnswer,ProfileEvidence,BeneficiaryCase,AuthUser,Pathway,TrainingCentre,DemandSignal,RecommendationRecord,Handoff,FollowUp,Outcome,AuditLog,KnowledgeDocument,KnowledgeChunk,LivelihoodAgentSession
from .schemas import StartSession,Message,SelectPathway,FollowUpCreate,FollowUpUpdate,OutcomeCreate,OutcomeVerification,HandoffCreate,HandoffUpdate,HandoffWorkflowUpdate,ActionPlanStepUpdate,DemoProfile,OutcomeUpdate,LoginBody,AIInterviewRequest,ProfileEvidenceUpdate
from .dialogue import transition,first_slot,question,SLOTS
from .recommender import recommend
from .planning import action_plan
from .casework import build_action_plan,build_handoff,handoff_view,can_access_case
from .followup import FOLLOWUP_INTERVAL_DAYS,LEGACY_OUTCOMES,due_date_for,parse_due_date,schedule_default_followups,refresh_followup_state,followup_questions,followup_view,outcome_view
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
from .knowledge.schemas import IngestDocument,KnowledgeQuestion,OfficialSourceImport,VerificationRequest
from .knowledge.service import KnowledgeService
from .knowledge.extractors import extract_document
from .knowledge.sources import registry as knowledge_source_registry,download_official
from .ai.agents.livelihood import LivelihoodAgentService
from .ai.agents.livelihood_schemas import AgentRunRequest

if AUTO_CREATE_SCHEMA:Base.metadata.create_all(bind=engine)
# Additive development upgrade for existing SQLite checkouts. Production deploys
# must run Alembic migrations before starting the API.
if AUTO_CREATE_SCHEMA and engine.dialect.name=="sqlite":
    with engine.begin() as conn:
        columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")}
        for name,definition in (("last_activity_at","DATETIME"),("completion_percentage","INTEGER NOT NULL DEFAULT 0"),("interview_version","VARCHAR NOT NULL DEFAULT '1'")):
            if name not in columns:conn.exec_driver_sql(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        case_columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(beneficiary_cases)")}
        if "structured_action_plan" not in case_columns:conn.exec_driver_sql("ALTER TABLE beneficiary_cases ADD COLUMN structured_action_plan JSON")
        handoff_columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(handoffs)")}
        handoff_additions={"assigned_to":"VARCHAR","case_state":"VARCHAR NOT NULL DEFAULT 'OPEN'","beneficiary_summary":"JSON NOT NULL DEFAULT '{}'","validated_profile":"JSON NOT NULL DEFAULT '{}'","recommendations":"JSON NOT NULL DEFAULT '[]'","selected_pathway":"JSON NOT NULL DEFAULT '{}'","supporting_evidence":"JSON NOT NULL DEFAULT '[]'","missing_information":"JSON NOT NULL DEFAULT '[]'","eligibility_uncertainty":"JSON NOT NULL DEFAULT '[]'","training_options":"JSON NOT NULL DEFAULT '[]'","counsellor_questions":"JSON NOT NULL DEFAULT '[]'","ai_brief":"JSON"}
        for name,definition in handoff_additions.items():
            if name not in handoff_columns:conn.exec_driver_sql(f"ALTER TABLE handoffs ADD COLUMN {name} {definition}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_handoffs_assigned_to ON handoffs (assigned_to)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_handoffs_case_state ON handoffs (case_state)")
        conn.exec_driver_sql("UPDATE handoffs SET case_state=CASE lower(status) WHEN 'accepted' THEN 'ASSIGNED' WHEN 'resolved' THEN 'CLOSED' ELSE 'OPEN' END WHERE case_state='OPEN'")
        followup_columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(followups)")}
        followup_additions={"schedule_offset_days":"INTEGER","rescheduled_from_id":"INTEGER REFERENCES followups(id)","contacted_at":"DATETIME","completed_at":"DATETIME","updated_at":"DATETIME"}
        for name,definition in followup_additions.items():
            if name not in followup_columns:conn.exec_driver_sql(f"ALTER TABLE followups ADD COLUMN {name} {definition}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_followups_status ON followups (status)")
        conn.exec_driver_sql("UPDATE followups SET status=CASE lower(status) WHEN 'pending' THEN 'SCHEDULED' WHEN 'complete' THEN 'COMPLETED' WHEN 'cancelled' THEN 'CANCELLED' ELSE upper(status) END")
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

def followup_question_client():
    try:
        settings=AISettings.from_env()
        return create_llm_client(settings) if settings.provider!="disabled" else None
    except (ValueError,AIUnavailable,AIProviderError):return None

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

@app.post("/api/v1/knowledge/documents")
def ingest_knowledge_document(body:IngestDocument,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    doc,chunks=KnowledgeService().ingest(db,body)
    log(db,"knowledge_document_ingested","knowledge_document",doc.id,f"category:{doc.category}; status:{doc.status}; chunks:{chunks}")
    db.commit()
    return {"document_id":doc.id,"title":doc.title,"category":doc.category,"status":doc.status,"verification_status":doc.verification_status,"chunk_count":chunks,"embedding_model":KnowledgeService().embedder.model_version}

@app.get("/api/v1/admin/knowledge/sources")
def knowledge_sources(staff:dict=Depends(admin_required)):
    return knowledge_source_registry()["sources"]

@app.get("/api/v1/admin/knowledge/documents")
def list_knowledge_documents(db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    rows=db.query(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc()).all()
    def state(doc):
        if doc.verification_status=="OFFICIAL_VERIFIED" and db.query(func.count(KnowledgeChunk.id)).filter_by(document_id=doc.id).scalar():return "verified_and_indexed"
        if doc.extraction_status in {"ocr_required","pdf_scanned_ocr_unavailable","ocr_language_unavailable","pdf_partial_text","pdf_partial_text_ocr_required"}:return "ocr_required"
        if doc.extraction_status in {"ocr_failed","ocr_partial_failure"}:return "ocr_failed"
        if doc.extraction_status in {"pdf_ocr_low_confidence"}:return "low_ocr_confidence"
        if doc.ocr_used:return "ocr_success_awaiting_verification"
        if doc.extraction_status in {"pdf_text","text","html","docx"}:return "text_extracted_awaiting_verification"
        return "awaiting_verification"
    return [{"document_id":doc.id,"title":doc.title,"source_url":doc.source_url,"authority":doc.authority,"ministry":doc.ministry,"department":doc.department,"scheme_name":doc.scheme_name,"category":doc.category,"status":doc.status,"verification_status":doc.verification_status,"source_type":doc.source_type,"version":doc.version,"publication_date":doc.publication_date,"effective_date":doc.effective_date,"last_verified":doc.last_verified,"ingestion_timestamp":doc.created_at.isoformat() if doc.created_at else None,"retrieved_at":doc.retrieved_at.isoformat() if doc.retrieved_at else None,"verified_by":doc.verified_by,"verification_note":doc.verification_note,"extraction_status":doc.extraction_status,"ingestion_status":state(doc),"extraction_message":doc.extraction_message,"ocr_used":doc.ocr_used,"ocr_reviewed":doc.ocr_reviewed,"ocr_engine":doc.ocr_engine,"ocr_language":doc.ocr_language,"ocr_confidence":doc.ocr_confidence,"ocr_available":doc.ocr_available,"chunk_count":db.query(func.count(KnowledgeChunk.id)).filter_by(document_id=doc.id).scalar()} for doc in rows]

@app.get("/api/v1/admin/knowledge/documents/{document_id}/chunks")
def knowledge_document_chunks(document_id:str,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    doc=db.get(KnowledgeDocument,document_id)
    if not doc:raise HTTPException(404,"Knowledge document not found")
    chunks=db.query(KnowledgeChunk).filter_by(document_id=document_id).order_by(KnowledgeChunk.ordinal).all()
    return {"document_id":doc.id,"title":doc.title,"verification_status":doc.verification_status,"ocr_used":doc.ocr_used,"ocr_engine":doc.ocr_engine,"ocr_language":doc.ocr_language,"ocr_confidence":doc.ocr_confidence,"verified":doc.verification_status=="OFFICIAL_VERIFIED","chunks":[{"chunk_id":c.id,"ordinal":c.ordinal,"page_number":c.page_number,"section":c.section,"text":c.text,"source_url":c.source_url,"source_identifier":doc.id,"source":doc.original_filename or doc.title,"ocr":doc.ocr_used,"ocr_status":doc.extraction_status,"verified":doc.verification_status=="OFFICIAL_VERIFIED","scheme_name":c.scheme_name,"issuing_authority":c.issuing_authority} for c in chunks]}

@app.get("/api/v1/admin/knowledge/documents/{document_id}/original")
def original_knowledge_document(document_id:str,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    doc=db.get(KnowledgeDocument,document_id)
    if not doc:raise HTTPException(404,"Knowledge document not found")
    if not doc.original_content:raise HTTPException(404,"Original document is unavailable")
    return Response(content=doc.original_content,media_type="application/octet-stream",headers={"Content-Disposition":f'attachment; filename="{Path(doc.original_filename or "source.bin").name}"'})

@app.post("/api/v1/admin/knowledge/documents/{document_id}/verify")
def verify_knowledge_document(document_id:str,body:VerificationRequest,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    try:doc=KnowledgeService().verify_document(db,document_id,body.decision,body.note,staff["username"],body.ocr_reviewed)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    log(db,"knowledge_document_reviewed","knowledge_document",doc.id,f"verification:{doc.verification_status}; reviewer:{staff['username']}");db.commit()
    return {"document_id":doc.id,"verification_status":doc.verification_status,"status":doc.status,"verified_by":doc.verified_by,"last_verified":doc.last_verified}

@app.post("/api/v1/admin/knowledge/documents/{document_id}/reindex")
def reindex_knowledge_document(document_id:str,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    try:doc,count=KnowledgeService().reindex(db,document_id)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    log(db,"knowledge_document_reindexed","knowledge_document",doc.id,f"chunks:{count}; reviewer:{staff['username']}");db.commit()
    return {"document_id":doc.id,"chunk_count":count,"extraction_status":doc.extraction_status}

@app.delete("/api/v1/admin/knowledge/documents/{document_id}")
def delete_knowledge_document(document_id:str,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    doc=db.get(KnowledgeDocument,document_id)
    if not doc:raise HTTPException(404,"Knowledge document not found")
    db.query(KnowledgeChunk).filter_by(document_id=doc.id).delete(synchronize_session=False)
    db.delete(doc);log(db,"knowledge_document_deleted","knowledge_document",document_id,f"reviewer:{staff['username']}");db.commit()
    return {"deleted":True,"document_id":document_id}

@app.post("/api/v1/admin/knowledge/documents/upload")
async def upload_knowledge_document(file:UploadFile=File(...),metadata:str=Form(...),db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    try:
        original=await file.read(20*1024*1024+1)
        pages,extraction=extract_document(original,file.filename or "upload.txt")
        extracted="\n\n".join(page.text for page in pages if page.text.strip())
        fields=json.loads(metadata);fields["content"]=extracted or "No text extracted; document requires OCR or manual review."
        document=IngestDocument.model_validate(fields)
        doc,count=KnowledgeService().ingest(db,document,original_content=original,filename=file.filename or "upload.txt",pages=pages,extraction_status=extraction)
    except (ValueError,TypeError,json.JSONDecodeError) as exc:raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc
    log(db,"knowledge_document_uploaded","knowledge_document",doc.id,f"category:{doc.category}; extraction:{doc.extraction_status}; chunks:{count}");db.commit()
    return {"document_id":doc.id,"title":doc.title,"status":doc.status,"verification_status":doc.verification_status,"extraction_status":doc.extraction_status,"extraction_message":doc.extraction_message,"ocr_used":doc.ocr_used,"ocr_engine":doc.ocr_engine,"ocr_language":doc.ocr_language,"ocr_confidence":doc.ocr_confidence,"ocr_available":doc.ocr_available,"chunk_count":count,"review_required":True}

@app.post("/api/v1/admin/knowledge/documents/import-url")
def import_official_knowledge_source(body:OfficialSourceImport,db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    url=str(body.url);entry=next((item for item in knowledge_source_registry()["sources"] if item["url"]==url),None)
    if not entry:raise HTTPException(422,"This URL is not in the configured official-source registry")
    try:
        original,content_type=download_official(url)
        filename=Path(urlparse(url).path).name or ("source.html" if "html" in content_type else "source.pdf")
        pages,extraction=extract_document(original,filename)
        extracted="\n\n".join(page.text for page in pages if page.text.strip())
        metadata={key:value for key,value in entry.items() if key!="verification_status"}
        metadata.update({"source":url,"source_url":url,"status":"UNKNOWN","version":entry.get("publication_date","1"),"language":"unknown","content":extracted or "No text extracted; document requires OCR or manual review."})
        document=IngestDocument.model_validate(metadata)
        doc,count=KnowledgeService().ingest(db,document,original_content=original,filename=filename,pages=pages,extraction_status=extraction)
    except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
    except Exception as exc:raise HTTPException(502,"Configured official source could not be fetched or extracted") from exc
    log(db,"official_knowledge_source_imported","knowledge_document",doc.id,f"source_host:{urlparse(url).hostname}; extraction:{extraction}; chunks:{count}");db.commit()
    return {"document_id":doc.id,"title":doc.title,"source_url":url,"verification_status":doc.verification_status,"status":doc.status,"extraction_status":doc.extraction_status,"extraction_message":doc.extraction_message,"ocr_used":doc.ocr_used,"ocr_engine":doc.ocr_engine,"ocr_language":doc.ocr_language,"ocr_confidence":doc.ocr_confidence,"ocr_available":doc.ocr_available,"chunk_count":count,"review_required":True}

@app.post("/api/v1/knowledge/search")
def search_knowledge(body:KnowledgeQuestion,db:Session=Depends(get_db)):
    service=KnowledgeService()
    hits=service.search_documents(db,body.question,category=body.category,district=body.district,state=body.state)
    return {"results":hits,"status":"UNKNOWN" if not hits else service._status(hits)}

@app.post("/api/v1/knowledge/ask")
def ask_knowledge(body:KnowledgeQuestion,db:Session=Depends(get_db)):
    client=None
    try:
        settings=AISettings.from_env()
        if settings.provider!="disabled":client=create_llm_client(settings)
    except (ValueError,AIUnavailable,AIProviderError):
        client=None
    result=KnowledgeService().answer(db,body.question,client,category=body.category,district=body.district,state=body.state)
    return result

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
        schedule_default_followups(db,s.id,"recommendation_check_in")
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
    return {"id":case.id,"session_id":case.session_id,"status":case.status,"selected_pathway_id":case.selected_pathway_id,"action_plan":case.action_plan or [],"structured_action_plan":case.structured_action_plan,"outcome":case.outcome,"outcome_note":case.outcome_note,"updated_at":case.updated_at.isoformat() if case.updated_at else None}

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
    plan=action_plan(recs[0] if recs else None);case=BeneficiaryCase(session_id=sid,status="recommendation",action_plan=plan);db.add(case);schedule_default_followups(db,sid,"recommendation_check_in");db.commit()
    return {"session":session_view(s),"recommendations":recs,"action_plan":plan,"case":case_view(case),"demo_persona":True}

@app.post("/api/v1/recommendations/select")
def select_pathway(body:SelectPathway,db:Session=Depends(get_db)):
    s=session_or_404(db,body.session_id)
    row=db.query(RecommendationRecord).filter_by(session_id=body.session_id,pathway_id=body.pathway_id).order_by(RecommendationRecord.id.desc()).first()
    if not row:raise HTTPException(404,"Generate this session's recommendations first")
    row.selected=True
    case=db.query(BeneficiaryCase).filter_by(session_id=body.session_id).one_or_none()
    if not case:case=BeneficiaryCase(session_id=body.session_id,action_plan=action_plan(None))
    p=db.get(Pathway,body.pathway_id)
    if not p:raise HTTPException(404,"Pathway not found")
    selected=row.explanation.get("recommendation") or {"pathway":pathway_view(p)}
    case.selected_pathway_id=body.pathway_id;case.status="counsellor_handoff";case.structured_action_plan=build_action_plan(s,selected,p);case.action_plan=action_plan(selected);db.add(case)
    handoff=db.query(Handoff).filter_by(session_id=s.id).filter(Handoff.case_state!="CLOSED").first()
    if not handoff:
        handoff=Handoff(session_id=s.id,reason="Pathway selected; counsellor to verify availability and next steps.",priority="normal",status="OPEN",case_state="OPEN");db.add(handoff)
    handoff_data=build_handoff(s,get_recommendations(s.id,db)["recommendations"],selected,db.query(ProfileEvidence).filter_by(session_id=s.id,status="accepted").all())
    for key,value in handoff_data.items():setattr(handoff,key,value)
    schedule_default_followups(db,s.id,"pathway_check_in")
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
    session=db.get(InterviewSession,sid);rows=db.query(FollowUp).filter_by(session_id=sid).all()
    changed=False
    for row in rows:changed=refresh_followup_state(row) or changed
    if changed:db.commit()
    latest=db.query(Outcome).filter_by(session_id=sid).order_by(Outcome.reported_at.desc(),Outcome.id.desc()).first()
    pathway=db.get(Pathway,case.selected_pathway_id) if case.selected_pathway_id else None
    questions=followup_questions(session,case,latest,pathway.title if pathway else None,followup_question_client(),sid)
    return {"case":case_view(case),"session":session_view(session),"recommendations":get_recommendations(sid,db)["recommendations"],"handoffs":[handoff_view(h) for h in db.query(Handoff).filter_by(session_id=sid).all()],"followups":[{"id":f.id,"stage":f.stage,"due_date":f.due_date,"note":f.note,"status":f.status.upper(),"schedule_offset_days":f.schedule_offset_days,"questions":questions} for f in rows],"outcomes":[outcome_view(o) for o in db.query(Outcome).filter_by(session_id=sid).order_by(Outcome.reported_at.desc(),Outcome.id.desc()).all()]}

@app.post("/api/v1/agent/livelihood/{sid}/run")
def run_livelihood_agent(sid:str,body:AgentRunRequest,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    session=session_or_404(db,sid)
    if not session.consent_at:raise HTTPException(403,"Beneficiary consent is required before agent planning")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=sid).all()):raise HTTPException(403,"Assign this case before accessing its details")
    try:
        result=LivelihoodAgentService().run(db,beneficiary_session_id=sid,goal=body.goal,actor=staff)
        db.commit()
        return result
    except PermissionError as exc:
        db.rollback();raise HTTPException(403,str(exc)) from exc
    except ValueError as exc:
        db.rollback();raise HTTPException(422,str(exc)) from exc

@app.get("/api/v1/agent/livelihood/session/{agent_session_id}")
def get_livelihood_agent_session(agent_session_id:str,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    run=db.get(LivelihoodAgentSession,agent_session_id)
    if not run:raise HTTPException(404,"Agent session not found")
    if staff.get("role")!="admin" and run.actor_username!=staff.get("username"):
        raise HTTPException(403,"This agent session belongs to another staff member")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=run.beneficiary_session_id).all()):raise HTTPException(403,"Assign this case before accessing its agent session")
    return {"agent_session_id":run.id,"beneficiary_session_id":run.beneficiary_session_id,"current_goal":run.current_goal,"tools_used":run.tools_used or [],"tool_results":run.tool_results or [],"final_action":run.final_action,"status":run.status,"created_at":run.created_at.isoformat() if run.created_at else None,"updated_at":run.updated_at.isoformat() if run.updated_at else None}

@app.get("/api/v1/staff/case/{sid}")
def get_staff_case(sid:str,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    handoffs=db.query(Handoff).filter_by(session_id=sid).all()
    if not can_access_case(staff,handoffs):raise HTTPException(403,"This case must be assigned to you before details are available")
    return get_case(sid,db)

@app.get("/api/v1/staff/profile/{sid}")
def get_staff_profile(sid:str,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    handoffs=db.query(Handoff).filter_by(session_id=sid).all()
    if not can_access_case(staff,handoffs):raise HTTPException(403,"This case must be assigned to you before details are available")
    return profile(sid,db)

@app.patch("/api/v1/case/{sid}/outcome")
def update_case_outcome(sid:str,body:OutcomeUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=sid).all()):raise HTTPException(403,"This case must be assigned to you before it can be updated")
    session_or_404(db,sid);case=db.query(BeneficiaryCase).filter_by(session_id=sid).one_or_none()
    if not case:raise HTTPException(404,"Case not found")
    category=LEGACY_OUTCOMES.get(body.outcome,body.outcome)
    outcome=Outcome(session_id=sid,category=category,source="counsellor",verification_status="VERIFIED",verification_note="Recorded by assigned counsellor.",verified_by=staff["username"],verified_at=datetime.now(timezone.utc),note=body.note)
    db.add(outcome);case.outcome=category;case.outcome_note=body.note
    completed=category in {"JOB_FOUND","SELF_EMPLOYED","BUSINESS_STARTED","TRAINING_COMPLETED"}
    case.status="completed" if completed else "follow_up"
    s=db.get(InterviewSession,sid);old=s.state
    if completed:s.state="COMPLETED"
    else:s.state="FOLLOW_UP"
    if old!=s.state:log(db,"state_transition","session",sid,f"{old}->{s.state}")
    log(db,"case_outcome_updated","case",case.id,f"{category}; source:counsellor; verification:VERIFIED");db.commit();return {"case":case_view(case),"outcome":outcome_view(outcome)}

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
    recs=get_recommendations(s.id,db)["recommendations"]
    selected=next((r for r in recs if (r.get("pathway") or {}).get("id")==((db.query(BeneficiaryCase).filter_by(session_id=s.id).one_or_none() or BeneficiaryCase(session_id=s.id)).selected_pathway_id)),recs[0] if recs else {})
    payload=build_handoff(s,recs,selected,db.query(ProfileEvidence).filter_by(session_id=s.id,status="accepted").all())
    for key,value in payload.items():setattr(h,key,value)
    case=db.query(BeneficiaryCase).filter_by(session_id=s.id).one_or_none()
    if case:case.status="counsellor_handoff"
    old=s.state;s.state="COUNSELLOR_HANDOFF";log(db,"handoff_created","session",s.id,body.reason)
    if old!=s.state:log(db,"state_transition","session",s.id,f"{old}->{s.state}")
    db.commit()
    return {"id":h.id,"status":h.status,"message":"Your request is in the demo counsellor queue."}
@app.get("/api/v1/handoff/queue")
def handoff_queue(db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    query=db.query(Handoff).order_by(Handoff.created_at.desc())
    if staff.get("role")!="admin":query=query.filter((Handoff.assigned_to.is_(None))|(Handoff.assigned_to==staff.get("username")))
    return [{"id":h.id,"session_id":h.session_id,"reason":h.reason if staff.get("role")=="admin" or h.assigned_to==staff.get("username") else "New counsellor review requested.","priority":h.priority,"status":h.status.upper(),"case_state":h.case_state,"assigned_to":h.assigned_to,"language":db.get(InterviewSession,h.session_id).language if staff.get("role")=="admin" or h.assigned_to==staff.get("username") else "—","district":(db.get(InterviewSession,h.session_id).profile or {}).get("district","—") if staff.get("role")=="admin" or h.assigned_to==staff.get("username") else "—","created_at":h.created_at.isoformat()} for h in query.all()]

@app.post("/api/v1/handoff/{handoff_id}/assign")
def assign_handoff(handoff_id:int,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    h=db.get(Handoff,handoff_id)
    if not h:raise HTTPException(404,"Handoff not found")
    if h.assigned_to and h.assigned_to!=staff.get("username") and staff.get("role")!="admin":raise HTTPException(403,"This handoff is assigned to another counsellor")
    h.assigned_to=staff.get("username");h.case_state="ASSIGNED" if h.case_state in {"OPEN","open"} else h.case_state;h.status=h.case_state.lower()
    log(db,"handoff_assigned","handoff",h.id,f"assigned_to:{h.assigned_to}");db.commit();return handoff_view(h)
@app.patch("/api/v1/handoff/{handoff_id}")
def update_handoff(handoff_id:int,body:HandoffUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    h=db.get(Handoff,handoff_id)
    if not h:raise HTTPException(404,"Handoff not found")
    if not can_access_case(staff,[h]):raise HTTPException(403,"Assign this handoff before updating it")
    h.case_state={"open":"OPEN","accepted":"ASSIGNED","resolved":"CLOSED"}[body.status];h.status=h.case_state.lower();log(db,"handoff_status_updated","handoff",h.id,h.case_state);db.commit();return {"id":h.id,"status":h.status,"case_state":h.case_state}

@app.patch("/api/v1/handoff/{handoff_id}/workflow")
def update_handoff_workflow(handoff_id:int,body:HandoffWorkflowUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    h=db.get(Handoff,handoff_id)
    if not h:raise HTTPException(404,"Handoff not found")
    if not can_access_case(staff,[h]):raise HTTPException(403,"Assign this handoff before updating it")
    transitions={"OPEN":{"ASSIGNED","CLOSED"},"ASSIGNED":{"IN_REVIEW","CLOSED"},"IN_REVIEW":{"CONTACTED","PATHWAY_VERIFIED","FOLLOW_UP","CLOSED"},"CONTACTED":{"PATHWAY_VERIFIED","REFERRED","FOLLOW_UP","CLOSED"},"PATHWAY_VERIFIED":{"REFERRED","ENROLLED","FOLLOW_UP","CLOSED"},"REFERRED":{"ENROLLED","FOLLOW_UP","CLOSED"},"ENROLLED":{"FOLLOW_UP","CLOSED"},"FOLLOW_UP":{"IN_REVIEW","CLOSED"},"CLOSED":set()}
    if body.status!=h.case_state and body.status not in transitions.get(h.case_state,set()):raise HTTPException(409,f"Cannot move handoff from {h.case_state} to {body.status}")
    h.case_state=body.status;h.status=body.status.lower()
    if body.note:log(db,"handoff_note_added","handoff",h.id,body.note)
    log(db,"handoff_workflow_updated","handoff",h.id,body.status);db.commit();return handoff_view(h)

@app.patch("/api/v1/staff/action-plans/{sid}/steps/{step_id}")
def update_action_plan_step(sid:str,step_id:str,body:ActionPlanStepUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    case=db.query(BeneficiaryCase).filter_by(session_id=sid).one_or_none()
    if not case or not case.structured_action_plan:raise HTTPException(404,"Action plan not found")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=sid).all()):raise HTTPException(403,"Assign this case before updating the plan")
    plan=case.structured_action_plan;step=next((x for x in plan.get("steps",[]) if x.get("id")==step_id),None)
    if not step:raise HTTPException(404,"Action plan step not found")
    dependencies=next((x.get("depends_on",[]) for x in plan.get("dependencies",[]) if x.get("step_id")==step_id),[])
    incomplete=[dep for dep in dependencies if not any(x.get("id")==dep and x.get("status")=="COMPLETED" for x in plan.get("steps",[]))]
    if body.status in {"IN_PROGRESS","COMPLETED"} and incomplete:raise HTTPException(409,{"message":"Complete the prerequisite steps first","incomplete_dependencies":incomplete})
    if body.status=="COMPLETED" and step.get("verification_required") and staff.get("role") not in {"admin","counsellor"}:raise HTTPException(403,"Counsellor verification is required")
    if body.status=="BLOCKED" and not body.note.strip():raise HTTPException(422,"A reason is required when blocking a step")
    step["status"]=body.status;step["blocked_reason"]=body.note.strip() if body.status=="BLOCKED" else None
    plan["status"]="COMPLETED" if all(x.get("status")=="COMPLETED" for x in plan.get("steps",[])) else "IN_PROGRESS"
    case.structured_action_plan=plan;case.action_plan=[x.get("title","") for x in plan.get("steps",[])];log(db,"action_plan_step_updated","case",case.id,f"step:{step_id}; status:{body.status}");db.commit()
    return {"action_plan":plan,"case":case_view(case)}

@app.post("/api/v1/followups")
def create_followup(body:FollowUpCreate,db:Session=Depends(get_db)):
    session=session_or_404(db,body.session_id)
    if not session.consent_at:raise HTTPException(403,"Consent is required before scheduling a follow-up")
    offset=body.schedule_offset_days or (None if body.due_date else FOLLOWUP_INTERVAL_DAYS[0])
    due=body.due_date or due_date_for(offset)
    try:parsed=parse_due_date(due)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if parsed<date.today():raise HTTPException(422,"Follow-up date cannot be in the past")
    f=FollowUp(session_id=body.session_id,stage=body.stage,due_date=due,note=body.note,schedule_offset_days=offset,status="DUE" if parsed==date.today() else "SCHEDULED");db.add(f);log(db,"followup_created","session",body.session_id,f"stage:{body.stage}; due:{due}; offset_days:{offset}");db.commit()
    return {"id":f.id,"session_id":f.session_id,"stage":f.stage,"due_date":f.due_date,"status":f.status,"schedule_offset_days":f.schedule_offset_days,"rescheduled_from_id":f.rescheduled_from_id}

@app.get("/api/v1/followups/schedule-options")
def followup_schedule_options():return {"interval_days":list(FOLLOWUP_INTERVAL_DAYS)}

@app.patch("/api/v1/followups/{followup_id}")
def update_followup(followup_id:int,body:FollowUpUpdate,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    f=db.get(FollowUp,followup_id)
    if not f:raise HTTPException(404,"Follow-up not found")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=f.session_id).all()):raise HTTPException(403,"Assign this case before updating follow-ups")
    aliases={"pending":"SCHEDULED","complete":"COMPLETED","cancelled":"CANCELLED"};new_status=aliases.get(body.status,body.status)
    refresh_followup_state(f)
    transitions={"SCHEDULED":{"DUE","CONTACTED","COMPLETED","MISSED","RESCHEDULED","CANCELLED"},"DUE":{"CONTACTED","COMPLETED","MISSED","RESCHEDULED","CANCELLED"},"CONTACTED":{"COMPLETED","MISSED","RESCHEDULED","CANCELLED"},"MISSED":{"CONTACTED","COMPLETED","RESCHEDULED","CANCELLED"},"RESCHEDULED":set(),"COMPLETED":set(),"CANCELLED":set()}
    if new_status=="RESCHEDULED":
        if not body.new_due_date:raise HTTPException(422,"Provide new_due_date to reschedule")
        try:new_day=parse_due_date(body.new_due_date)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        if new_day<=date.today():raise HTTPException(422,"Rescheduled date must be in the future")
        if "RESCHEDULED" not in transitions.get(f.status.upper(),set()):raise HTTPException(409,f"Cannot reschedule a {f.status} follow-up")
        f.status="RESCHEDULED"
        replacement=FollowUp(session_id=f.session_id,stage=f.stage,due_date=new_day.isoformat(),note=body.note or f.note,status="SCHEDULED",schedule_offset_days=f.schedule_offset_days,rescheduled_from_id=f.id)
        db.add(replacement);db.flush();log(db,"followup_rescheduled","followup",f.id,f"replacement:{replacement.id}; due:{replacement.due_date}");db.commit()
        return {"followup":followup_view(f),"replacement":followup_view(replacement)}
    current=f.status.upper()
    if new_status=="MISSED":
        if not f.due_date or parse_due_date(f.due_date)>=date.today():raise HTTPException(409,"A follow-up can be marked missed only after its due date")
    if new_status=="DUE":
        refresh_followup_state(f)
        if f.status!="DUE":raise HTTPException(409,"This follow-up is not due yet")
    if new_status!=current and new_status not in transitions.get(current,set()):raise HTTPException(409,f"Cannot move follow-up from {current} to {new_status}")
    f.status=new_status
    if new_status=="CONTACTED":f.contacted_at=datetime.now(timezone.utc)
    if new_status=="COMPLETED":f.completed_at=datetime.now(timezone.utc)
    case=db.query(BeneficiaryCase).filter_by(session_id=f.session_id).one_or_none()
    if case and new_status=="COMPLETED":
        case.status="follow_up";s=db.get(InterviewSession,f.session_id);old=s.state;s.state="FOLLOW_UP"
        if old!=s.state:log(db,"state_transition","session",s.id,f"{old}->{s.state}")
    if body.note:f.note=body.note
    log(db,"followup_status_updated","followup",f.id,new_status);db.commit();return followup_view(f)
@app.get("/api/v1/followups")
def followups(session_id:str|None=None,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    q=db.query(FollowUp)
    if session_id:q=q.filter_by(session_id=session_id)
    rows=q.order_by(FollowUp.due_date.asc(),FollowUp.created_at.desc()).all();visible=[];changed=False
    for f in rows:
        if not can_access_case(staff,db.query(Handoff).filter_by(session_id=f.session_id).all()):continue
        changed=refresh_followup_state(f) or changed;visible.append(f)
    if changed:db.commit()
    return [followup_view(f) for f in visible]

@app.get("/api/v1/followups/{followup_id}/questions")
def get_followup_questions(followup_id:int,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    f=db.get(FollowUp,followup_id)
    if not f:raise HTTPException(404,"Follow-up not found")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=f.session_id).all()):raise HTTPException(403,"Assign this case before accessing follow-up context")
    session=session_or_404(db,f.session_id);case=db.query(BeneficiaryCase).filter_by(session_id=f.session_id).one_or_none();pathway=db.get(Pathway,case.selected_pathway_id) if case and case.selected_pathway_id else None
    latest=db.query(Outcome).filter_by(session_id=f.session_id).order_by(Outcome.reported_at.desc(),Outcome.id.desc()).first()
    return {"followup_id":f.id,"stage":f.stage,**followup_questions(session,case,latest,pathway.title if pathway else None,followup_question_client(),f.session_id)}

def _apply_verified_outcome(db,session,case,outcome,verified_by,note=""):
    outcome.verification_status="VERIFIED";outcome.verified_by=verified_by;outcome.verified_at=datetime.now(timezone.utc);outcome.verification_note=note or "Verified by counsellor."
    case.outcome=outcome.category;case.outcome_note=outcome.note;case.status="completed" if outcome.category in {"JOB_FOUND","SELF_EMPLOYED","BUSINESS_STARTED","TRAINING_COMPLETED"} else "follow_up"
    old=session.state;session.state="COMPLETED" if case.status=="completed" else "FOLLOW_UP"
    if old!=session.state:log(db,"state_transition","session",session.id,f"{old}->{session.state}")
    log(db,"outcome_verified","outcome",outcome.id,f"category:{outcome.category}; source:{outcome.source}; verified_by:{verified_by}")

@app.post("/api/v1/outcomes")
def create_outcome(body:OutcomeCreate,db:Session=Depends(get_db)):
    session=session_or_404(db,body.session_id)
    if not session.consent_at:raise HTTPException(403,"Consent is required before recording an outcome")
    case=db.query(BeneficiaryCase).filter_by(session_id=session.id).one_or_none()
    if not case:raise HTTPException(409,"Complete the profile and recommendation flow before reporting an outcome")
    row=Outcome(session_id=session.id,category=body.outcome,source="beneficiary",verification_status="UNVERIFIED",note=body.note)
    db.add(row);log(db,"outcome_reported","outcome",session.id,f"category:{body.outcome}; source:beneficiary; verification:UNVERIFIED");db.commit()
    return outcome_view(row)

@app.get("/api/v1/outcomes")
def list_outcomes(session_id:str|None=None,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    query=db.query(Outcome).order_by(Outcome.reported_at.desc(),Outcome.id.desc())
    if session_id:query=query.filter_by(session_id=session_id)
    return [outcome_view(row) for row in query.all() if can_access_case(staff,db.query(Handoff).filter_by(session_id=row.session_id).all())]

@app.patch("/api/v1/outcomes/{outcome_id}/verify")
def verify_outcome(outcome_id:int,body:OutcomeVerification,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    row=db.get(Outcome,outcome_id)
    if not row:raise HTTPException(404,"Outcome report not found")
    if not can_access_case(staff,db.query(Handoff).filter_by(session_id=row.session_id).all()):raise HTTPException(403,"Assign this case before verifying outcomes")
    if row.verification_status!="UNVERIFIED":raise HTTPException(409,"This outcome has already been reviewed")
    if body.verification_status=="REJECTED":
        row.verification_status="REJECTED";row.verified_by=staff["username"];row.verified_at=datetime.now(timezone.utc);row.verification_note=body.note or "Not verified by counsellor."
        log(db,"outcome_rejected","outcome",row.id,f"source:{row.source}; verified_by:{staff['username']}")
    else:
        case=db.query(BeneficiaryCase).filter_by(session_id=row.session_id).one_or_none();session=session_or_404(db,row.session_id)
        if not case:raise HTTPException(404,"Case not found")
        _apply_verified_outcome(db,session,case,row,staff["username"],body.note)
    db.commit();return outcome_view(row)

@app.get("/api/v1/beneficiaries")
def beneficiaries(q:str|None=None,db:Session=Depends(get_db),staff:dict=Depends(staff_required)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).order_by(InterviewSession.created_at.desc()).limit(100).all()
    if staff.get("role")!="admin":sessions=[s for s in sessions if can_access_case(staff,db.query(Handoff).filter_by(session_id=s.id).all())]
    if q:
        sessions=[s for s in sessions if q.lower() in s.id.lower() or (can_access_case(staff,db.query(Handoff).filter_by(session_id=s.id).all()) and q.lower() in str(s.profile).lower())]
    def summary(s):
        allowed=can_access_case(staff,db.query(Handoff).filter_by(session_id=s.id).all())
        interests=(s.profile or {}).get("interests",[])
        return {"id":s.id,"language":s.language,"state":s.state,"district":(s.profile or {}).get("district","—") if allowed else "—","interest":(", ".join(interests) if isinstance(interests,list) else interests) if allowed else "—","assigned":allowed,"created_at":s.created_at.isoformat()}
    return [summary(s) for s in sessions]

@app.get("/api/v1/admin/analytics")
def analytics(db:Session=Depends(get_db),staff:dict=Depends(admin_required)):
    sessions=db.query(InterviewSession).filter(InterviewSession.consent_at.is_not(None)).all();total=len(sessions)
    language={};district={};interests={}
    for s in sessions:
        language[s.language]=language.get(s.language,0)+1;p=s.profile or {};d=p.get("district","Unknown");district[d]=district.get(d,0)+1
        vals=p.get("interests",[]);vals=vals if isinstance(vals,list) else [vals]
        for v in vals:interests[str(v)]=interests.get(str(v),0)+1
    rec_count=db.query(RecommendationRecord).count();selected=db.query(RecommendationRecord).filter_by(selected=True).count();verified_outcomes=db.query(Outcome).filter_by(verification_status="VERIFIED").all();enrolled=sum(x.category in {"TRAINING_STARTED","TRAINING_COMPLETED"} for x in verified_outcomes);placed=sum(x.category in {"JOB_FOUND","SELF_EMPLOYED","BUSINESS_STARTED"} for x in verified_outcomes)
    demand=db.query(DemandSignal).all()
    # Small groups are suppressed; no raw beneficiary-level records leave this endpoint.
    def suppress(d):return {k:(v if v>=5 else None) for k,v in d.items()}
    return {"counts":{"beneficiaries_reached":total if total>=5 else None,"profiles_completed":sum(s.completed_at is not None for s in sessions) if sum(s.completed_at is not None for s in sessions)>=5 else None,"recommendations_generated":rec_count if rec_count>=5 else None,"counsellor_handoffs":db.query(Handoff).count() if db.query(Handoff).count()>=5 else None},"languages":suppress(language),"districts":suppress(district),"interests":suppress(interests),"funnel":[{"stage":"profiles","count":total if total>=5 else None},{"stage":"recommendations","count":rec_count if rec_count>=5 else None},{"stage":"selected","count":selected if selected>=5 else None},{"stage":"verified training outcomes","count":enrolled if enrolled>=5 else None},{"stage":"verified livelihood outcomes","count":placed if placed>=5 else None}],"demand_capacity":[{"district":d.district,"sector":d.sector,"demand":d.demand_label,"sample_capacity":d.capacity,"source":d.source,"year":d.year} for d in demand],"data_notice":"Outcome analytics count counsellor-verified reports only. Session analytics are suppressed below 5. Capacity/demand values are synthetic demo samples, not official statistics.","generated_at":datetime.now(timezone.utc).isoformat()}

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
        db.query(ProfileEvidence).filter_by(session_id=sid).delete();db.query(InterviewAnswer).filter_by(session_id=sid).delete();db.query(Outcome).filter_by(session_id=sid).delete();db.query(BeneficiaryCase).filter_by(session_id=sid).delete();db.query(RecommendationRecord).filter_by(session_id=sid).delete();db.query(Handoff).filter_by(session_id=sid).delete();db.query(LivelihoodAgentSession).filter_by(beneficiary_session_id=sid).delete();db.query(FollowUp).filter_by(session_id=sid).update({FollowUp.rescheduled_from_id:None});db.query(FollowUp).filter_by(session_id=sid).delete();db.delete(s);log(db,"session_deleted","session",sid);db.commit()
    return {"deleted":True}

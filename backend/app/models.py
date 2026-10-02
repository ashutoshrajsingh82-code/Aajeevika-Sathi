from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, JSON, Integer, Index, Float, UniqueConstraint, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def utcnow(): return datetime.now(timezone.utc)

class InterviewSession(Base):
    __tablename__="sessions"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    language:Mapped[str]=mapped_column(String,default="en")
    state:Mapped[str]=mapped_column(String,default="CONSENT")
    profile:Mapped[dict]=mapped_column(JSON,default=dict)
    consent_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    last_activity_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=True)
    completion_percentage:Mapped[int]=mapped_column(Integer,default=0)
    interview_version:Mapped[str]=mapped_column(String,default="1")

class InterviewAnswer(Base):
    __tablename__="interview_answers"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id",ondelete="CASCADE"),index=True)
    slot:Mapped[str]=mapped_column(String)
    question:Mapped[str]=mapped_column(Text,default="")
    answer:Mapped[str]=mapped_column(Text)
    normalized_answer:Mapped[dict]=mapped_column(JSON,default=dict)
    input_method:Mapped[str]=mapped_column(String,default="text")
    language:Mapped[str]=mapped_column(String,default="en")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ProfileEvidence(Base):
    __tablename__="profile_evidence"
    __table_args__=(UniqueConstraint("session_id","source_answer_id","field",name="uq_profile_evidence_session_answer_field"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id",ondelete="CASCADE"),index=True)
    source_answer_id:Mapped[int]=mapped_column(ForeignKey("interview_answers.id",ondelete="CASCADE"),index=True)
    field:Mapped[str]=mapped_column(String,index=True)
    canonical_value:Mapped[object]=mapped_column(JSON)
    confidence:Mapped[float]=mapped_column(Float)
    status:Mapped[str]=mapped_column(String,default="accepted")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Pathway(Base):
    __tablename__="pathways"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    title:Mapped[str]=mapped_column(String,index=True)
    sector:Mapped[str]=mapped_column(String,index=True)
    description:Mapped[str]=mapped_column(Text)
    skills:Mapped[list]=mapped_column(JSON,default=list)
    prerequisites:Mapped[list]=mapped_column(JSON,default=list)
    min_education:Mapped[str]=mapped_column(String,default="verify")
    duration_hours:Mapped[int|None]=mapped_column(Integer,nullable=True)
    self_employment:Mapped[bool]=mapped_column(Boolean,default=False)
    source:Mapped[str]=mapped_column(String,default="SIMULATED DEMO PATHWAY")
    source_url:Mapped[str]=mapped_column(String,default="")
    active:Mapped[bool]=mapped_column(Boolean,default=True)

class TrainingCentre(Base):
    __tablename__="training_centres"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    name:Mapped[str]=mapped_column(String)
    district:Mapped[str]=mapped_column(String,index=True)
    block:Mapped[str]=mapped_column(String)
    latitude:Mapped[float]=mapped_column()
    longitude:Mapped[float]=mapped_column()
    address:Mapped[str]=mapped_column(String)
    contact:Mapped[str]=mapped_column(String,default="VERIFY")
    accessibility:Mapped[str]=mapped_column(String,default="VERIFY")
    source:Mapped[str]=mapped_column(String,default="SIMULATED SAMPLE")
    pathway_ids:Mapped[list]=mapped_column(JSON,default=list)

class DemandSignal(Base):
    __tablename__="demand_signals"
    id:Mapped[int]=mapped_column(primary_key=True)
    district:Mapped[str]=mapped_column(String,index=True)
    sector:Mapped[str]=mapped_column(String,index=True)
    demand_label:Mapped[str]=mapped_column(String)
    source:Mapped[str]=mapped_column(String,default="SIMULATED SAMPLE")
    year:Mapped[int]=mapped_column(Integer,default=2026)
    capacity:Mapped[int]=mapped_column(Integer,default=0)

class RecommendationRecord(Base):
    __tablename__="recommendations"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id"),index=True)
    pathway_id:Mapped[str]=mapped_column(ForeignKey("pathways.id"))
    selected:Mapped[bool]=mapped_column(Boolean,default=False)
    explanation:Mapped[dict]=mapped_column(JSON,default=dict)
    score:Mapped[float|None]=mapped_column(Float,nullable=True)
    component_scores:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    matched_skills:Mapped[list|None]=mapped_column(JSON,nullable=True)
    missing_skills:Mapped[list|None]=mapped_column(JSON,nullable=True)
    demand_signal:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    feasibility:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    data_sources:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    model_version:Mapped[str|None]=mapped_column(String,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Handoff(Base):
    __tablename__="handoffs"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id"),index=True)
    reason:Mapped[str]=mapped_column(String)
    priority:Mapped[str]=mapped_column(String,default="normal")
    status:Mapped[str]=mapped_column(String,default="OPEN")
    assigned_to:Mapped[str|None]=mapped_column(String,nullable=True,index=True)
    case_state:Mapped[str]=mapped_column(String,default="OPEN",index=True)
    beneficiary_summary:Mapped[dict]=mapped_column(JSON,default=dict)
    validated_profile:Mapped[dict]=mapped_column(JSON,default=dict)
    recommendations:Mapped[list]=mapped_column(JSON,default=list)
    selected_pathway:Mapped[dict]=mapped_column(JSON,default=dict)
    supporting_evidence:Mapped[list]=mapped_column(JSON,default=list)
    missing_information:Mapped[list]=mapped_column(JSON,default=list)
    eligibility_uncertainty:Mapped[list]=mapped_column(JSON,default=list)
    training_options:Mapped[list]=mapped_column(JSON,default=list)
    counsellor_questions:Mapped[list]=mapped_column(JSON,default=list)
    ai_brief:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class FollowUp(Base):
    __tablename__="followups"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id"),index=True)
    stage:Mapped[str]=mapped_column(String)
    due_date:Mapped[str]=mapped_column(String,default="")
    note:Mapped[str]=mapped_column(Text,default="")
    status:Mapped[str]=mapped_column(String,default="SCHEDULED",index=True)
    schedule_offset_days:Mapped[int|None]=mapped_column(Integer,nullable=True)
    rescheduled_from_id:Mapped[int|None]=mapped_column(ForeignKey("followups.id"),nullable=True)
    contacted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    updated_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Outcome(Base):
    __tablename__="outcomes"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id",ondelete="CASCADE"),index=True)
    category:Mapped[str]=mapped_column(String,index=True)
    source:Mapped[str]=mapped_column(String,index=True)
    reported_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    verification_status:Mapped[str]=mapped_column(String,default="UNVERIFIED",index=True)
    verification_note:Mapped[str]=mapped_column(Text,default="")
    verified_by:Mapped[str|None]=mapped_column(String,nullable=True)
    verified_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    note:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class LivelihoodAgentSession(Base):
    __tablename__="livelihood_agent_sessions"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    beneficiary_session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id",ondelete="CASCADE"),index=True)
    actor_username:Mapped[str]=mapped_column(String,index=True)
    current_goal:Mapped[str]=mapped_column(String)
    tools_used:Mapped[list]=mapped_column(JSON,default=list)
    tool_results:Mapped[list]=mapped_column(JSON,default=list)
    final_action:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    status:Mapped[str]=mapped_column(String,default="running",index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class BeneficiaryCase(Base):
    __tablename__="beneficiary_cases"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id",ondelete="CASCADE"),unique=True,index=True)
    status:Mapped[str]=mapped_column(String,default="profile_review")
    selected_pathway_id:Mapped[str|None]=mapped_column(ForeignKey("pathways.id"),nullable=True)
    action_plan:Mapped[list]=mapped_column(JSON,default=list)
    structured_action_plan:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    outcome:Mapped[str]=mapped_column(String,default="unknown")
    outcome_note:Mapped[str]=mapped_column(Text,default="")
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(primary_key=True)
    action:Mapped[str]=mapped_column(String)
    entity_type:Mapped[str]=mapped_column(String)
    entity_id:Mapped[str]=mapped_column(String)
    detail:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class AuthUser(Base):
    __tablename__="auth_users"
    id:Mapped[int]=mapped_column(primary_key=True)
    username:Mapped[str]=mapped_column(String,unique=True,index=True)
    password_hash:Mapped[str]=mapped_column(String)
    role:Mapped[str]=mapped_column(String,index=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    auth_version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_login_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class KnowledgeDocument(Base):
    __tablename__="knowledge_documents"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    title:Mapped[str]=mapped_column(String,index=True)
    source:Mapped[str]=mapped_column(String)
    authority:Mapped[str]=mapped_column(String,default="Unknown")
    category:Mapped[str]=mapped_column(String,index=True)
    district:Mapped[str|None]=mapped_column(String,index=True,nullable=True)
    state:Mapped[str|None]=mapped_column(String,index=True,nullable=True)
    effective_date:Mapped[str|None]=mapped_column(String,nullable=True)
    last_verified:Mapped[str|None]=mapped_column(String,nullable=True)
    version:Mapped[str]=mapped_column(String,default="1")
    status:Mapped[str]=mapped_column(String,index=True,default="UNKNOWN")
    source_url:Mapped[str|None]=mapped_column(String,nullable=True)
    ministry:Mapped[str|None]=mapped_column(String,nullable=True)
    department:Mapped[str|None]=mapped_column(String,nullable=True)
    scheme_name:Mapped[str|None]=mapped_column(String,nullable=True)
    document_type:Mapped[str|None]=mapped_column(String,nullable=True)
    publication_date:Mapped[str|None]=mapped_column(String,nullable=True)
    language:Mapped[str]=mapped_column(String,default="unknown")
    source_type:Mapped[str]=mapped_column(String,default="unknown")
    verification_status:Mapped[str]=mapped_column(String,index=True,default="UNKNOWN")
    retrieved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    supersedes_document_id:Mapped[str|None]=mapped_column(ForeignKey("knowledge_documents.id"),nullable=True)
    original_filename:Mapped[str|None]=mapped_column(String,nullable=True)
    original_content:Mapped[bytes|None]=mapped_column(LargeBinary,nullable=True)
    extraction_status:Mapped[str]=mapped_column(String,default="text_only")
    ocr_used:Mapped[bool]=mapped_column(Boolean,default=False)
    ocr_engine:Mapped[str|None]=mapped_column(String,nullable=True)
    ocr_language:Mapped[str|None]=mapped_column(String,nullable=True)
    ocr_confidence:Mapped[float|None]=mapped_column(Float,nullable=True)
    ocr_available:Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    ocr_reviewed:Mapped[bool]=mapped_column(Boolean,default=False)
    extraction_message:Mapped[str|None]=mapped_column(Text,nullable=True)
    verified_by:Mapped[str|None]=mapped_column(String,nullable=True)
    verification_note:Mapped[str|None]=mapped_column(Text,nullable=True)
    content_hash:Mapped[str]=mapped_column(String,index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class KnowledgeChunk(Base):
    __tablename__="knowledge_chunks"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    document_id:Mapped[str]=mapped_column(ForeignKey("knowledge_documents.id",ondelete="CASCADE"),index=True)
    ordinal:Mapped[int]=mapped_column(Integer)
    text:Mapped[str]=mapped_column(Text)
    embedding:Mapped[list]=mapped_column(JSON)
    embedding_model:Mapped[str]=mapped_column(String,default="local-feature-hash-v1")
    page_number:Mapped[int|None]=mapped_column(Integer,nullable=True)
    section:Mapped[str|None]=mapped_column(String,nullable=True)
    source_url:Mapped[str|None]=mapped_column(String,nullable=True)
    ocr_used:Mapped[bool]=mapped_column(Boolean,default=False)
    ocr_language:Mapped[str|None]=mapped_column(String,nullable=True)
    ocr_confidence:Mapped[float|None]=mapped_column(Float,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class AIOperationMetric(Base):
    __tablename__="ai_operation_metrics"
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[str]=mapped_column(String,index=True)
    session_id:Mapped[str|None]=mapped_column(String,index=True,nullable=True)
    operation:Mapped[str]=mapped_column(String,index=True)
    model:Mapped[str]=mapped_column(String,default="disabled")
    event_kind:Mapped[str]=mapped_column(String,index=True,default="operation")
    latency_ms:Mapped[float]=mapped_column(Float)
    outcome:Mapped[str]=mapped_column(String,index=True)
    validation_failure:Mapped[bool]=mapped_column(Boolean,default=False)
    prompt_tokens:Mapped[int|None]=mapped_column(Integer,nullable=True)
    completion_tokens:Mapped[int|None]=mapped_column(Integer,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,index=True)

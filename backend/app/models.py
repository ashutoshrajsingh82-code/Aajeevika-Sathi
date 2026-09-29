from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, JSON, Integer, Index
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
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Handoff(Base):
    __tablename__="handoffs"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id"),index=True)
    reason:Mapped[str]=mapped_column(String)
    priority:Mapped[str]=mapped_column(String,default="normal")
    status:Mapped[str]=mapped_column(String,default="open")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class FollowUp(Base):
    __tablename__="followups"
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[str]=mapped_column(ForeignKey("sessions.id"),index=True)
    stage:Mapped[str]=mapped_column(String)
    due_date:Mapped[str]=mapped_column(String,default="")
    note:Mapped[str]=mapped_column(Text,default="")
    status:Mapped[str]=mapped_column(String,default="pending")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(primary_key=True)
    action:Mapped[str]=mapped_column(String)
    entity_type:Mapped[str]=mapped_column(String)
    entity_id:Mapped[str]=mapped_column(String)
    detail:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

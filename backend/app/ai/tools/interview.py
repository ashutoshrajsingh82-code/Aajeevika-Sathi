"""Validated interview operations. These helpers only touch the current session and answer log."""
from datetime import datetime,timezone
from ...dialogue import SLOTS,first_slot,question
from ...models import InterviewAnswer,InterviewSession
from ..services.profile_builder import ProfileBuilderService

class InterviewTools:
    def __init__(self,db,session:InterviewSession):
        self.db=db;self.session=session

    def _check(self):
        if not self.session or self.db.get(InterviewSession,self.session.id) is None:
            raise ValueError("Interview session is no longer valid")
        if not self.session.consent_at or self.session.state!="INTERVIEW":
            raise ValueError("Interview is not authorized for AI processing")

    def get_interview_state(self):
        self._check()
        return {"session_id":self.session.id,"state":self.session.state,"language":self.session.language}

    def get_missing_profile_fields(self):
        self._check()
        profile=self.session.profile or {}
        return [slot for slot in SLOTS if slot not in profile and slot not in profile.get("skipped_slots",[])]

    def update_profile(self,extracted:dict,*,source_answer:InterviewAnswer,confidence:dict):
        self._check()
        return ProfileBuilderService().apply_candidate(self.db,self.session,source_answer,extracted,confidence)

    def save_answer(self,*,raw_answer:str,slot:str,input_method:str,normalized:dict):
        self._check()
        if slot not in SLOTS or slot!=first_slot(self.session.profile or {}) or not raw_answer.strip() or len(raw_answer)>2000:raise ValueError("Invalid answer or stale question")
        if input_method not in {"text","browser_voice","server_transcription"}:raise ValueError("Invalid input method")
        row=InterviewAnswer(session_id=self.session.id,slot=slot,question=question(slot,self.session.language),answer=raw_answer,normalized_answer=normalized,input_method=input_method,language=self.session.language)
        self.db.add(row);self.db.flush()
        return row

    def ask_next_question(self):
        self._check()
        return question(first_slot(self.session.profile or {}),self.session.language)

    def complete_interview(self):
        self._check()
        if self.get_missing_profile_fields():raise ValueError("Required interview fields remain")
        self.session.state="PROFILE_REVIEW"
        self.session.last_activity_at=datetime.now(timezone.utc)

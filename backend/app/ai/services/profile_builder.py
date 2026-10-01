"""Convert model candidates into validated values with answer-level provenance."""
from pydantic import ValidationError
from ...dialogue import SLOTS
from ...models import InterviewAnswer,InterviewSession,ProfileEvidence
from ..schemas import ExtractedProfile

CONFIDENCE_REVIEW_THRESHOLD=0.75
LIST_FIELDS={"skills","interests","tools","constraints"}
SKILL_ALIASES={
    "basic computer":"basic_computer","computer knowledge":"basic_computer",
    "computer use":"basic_computer","computer chalana":"basic_computer",
    "computer चलाना":"basic_computer","basic computer skills":"basic_computer",
    "excel":"basic_excel","basic excel":"basic_excel","ms excel":"basic_excel",
    "spreadsheet":"basic_excel","ms office":"ms_office","microsoft office":"ms_office",
}
INTEREST_ALIASES={"computer":"computer_work","computers":"computer_work","computer work":"computer_work"}

def _normalise_item(field,value):
    text=" ".join(value.strip().split())
    folded=text.casefold()
    if field=="skills":return SKILL_ALIASES.get(folded,text)
    if field=="interests":return INTEREST_ALIASES.get(folded,text)
    return text

def _canonical(field,value):
    if field in LIST_FIELDS:
        vals=value if isinstance(value,list) else [value]
        return list(dict.fromkeys(_normalise_item(field,item) for item in vals))
    if field in {"education_level","age_band","current_occupation","family_occupation","mobility_level","time_available","district","block","training_duration_preference"} and isinstance(value,str):
        return " ".join(value.strip().split())
    return value

class ProfileBuilderService:
    def apply_candidate(self,db,session:InterviewSession,answer:InterviewAnswer,candidate:dict,confidence:dict):
        if not session.consent_at or session.state!="INTERVIEW" or answer.session_id!=session.id:
            raise ValueError("Profile extraction is not authorized for this session")
        if not isinstance(candidate,dict) or set(candidate)-set(SLOTS):raise ValueError("Unsupported candidate fields")
        if set(confidence)-set(candidate):raise ValueError("Confidence references an absent field")
        profile=dict(session.profile or {})
        validated={}
        try:
            for field,value in candidate.items():
                if field not in SLOTS:raise ValueError("Unsupported profile field")
                one=ExtractedProfile.model_validate({field:value}).model_dump(exclude_unset=True)
                validated[field]=_canonical(field,one[field])
        except ValidationError as exc:raise ValueError("Candidate profile failed business validation") from exc

        for field,value in validated.items():
            score=confidence.get(field,0.5)
            if not isinstance(score,(int,float)) or not 0<=score<=1:raise ValueError("Invalid profile confidence")
            existing=profile.get(field)
            conflict=False
            if field in LIST_FIELDS:
                old=existing if isinstance(existing,list) else ([existing] if existing is not None else [])
                profile[field]=list(dict.fromkeys([*old,*value]))[:30]
            elif existing is None:
                profile[field]=value
            elif existing!=value:
                conflict=True
            status="pending" if conflict or score<CONFIDENCE_REVIEW_THRESHOLD else "accepted"
            db.add(ProfileEvidence(session_id=session.id,source_answer_id=answer.id,field=field,canonical_value=value,confidence=float(score),status=status))
        session.profile=profile
        return profile

    def resolve(self,db,session:InterviewSession,evidence:ProfileEvidence,action:str,value=None):
        if evidence.session_id!=session.id:raise ValueError("Profile evidence belongs to a different session")
        if evidence.status not in {"pending","accepted","confirmed","corrected"}:raise ValueError("This profile evidence is no longer editable")
        profile=dict(session.profile or {});field=evidence.field
        if field not in SLOTS:raise ValueError("Unsupported profile field")
        same=db.query(ProfileEvidence).filter_by(session_id=session.id,field=field).all()
        if action=="confirm":
            if field in LIST_FIELDS:
                old=profile.get(field,[]);old=old if isinstance(old,list) else [old]
                vals=evidence.canonical_value if isinstance(evidence.canonical_value,list) else [evidence.canonical_value]
                profile[field]=list(dict.fromkeys([*old,*vals]))[:30]
            else:profile[field]=evidence.canonical_value
            evidence.status="confirmed"
        elif action=="correct":
            if value is None:raise ValueError("A corrected value is required")
            try:corrected=ExtractedProfile.model_validate({field:value}).model_dump(exclude_unset=True)[field]
            except (ValidationError,TypeError) as exc:raise ValueError("Correction failed profile validation") from exc
            corrected=_canonical(field,corrected);profile[field]=corrected;evidence.canonical_value=corrected;evidence.status="corrected"
        elif action=="remove":
            profile.pop(field,None);evidence.status="removed"
            for row in same:
                if row.id!=evidence.id:row.status="removed"
        else:raise ValueError("Action must be confirm, correct, or remove")
        for row in same:
            if row.id!=evidence.id and row.status not in {"removed","superseded"}:row.status="superseded"
        session.profile=profile
        return profile

def evidence_views(db,session_id:str):
    rows=db.query(ProfileEvidence).filter_by(session_id=session_id).order_by(ProfileEvidence.id.asc()).all()
    result=[]
    for row in rows:
        answer=db.get(InterviewAnswer,row.source_answer_id)
        result.append({"id":row.id,"field":row.field,"canonical_value":row.canonical_value,"confidence":row.confidence,"status":row.status,"source_answer_id":row.source_answer_id,"raw_text":answer.answer if answer else None})
    return result

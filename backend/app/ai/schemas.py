"""Strict, bounded schemas for model-facing structured outputs."""
from __future__ import annotations
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,field_validator

ShortText=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=200)]

class StrictSchema(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)

class InterviewAnswer(StrictSchema):
    slot:str=Field(min_length=1,max_length=60)
    answer:str=Field(min_length=1,max_length=2000)
    normalized_answer:str|float|int|bool|list[str]|None
    language:Literal["en","hi"]
    input_method:Literal["text","browser_voice","server_transcription"]

class InterviewTurn(StrictSchema):
    """Bounded interpretation of one turn; it cannot select tables or state transitions."""
    extracted:ExtractedProfile
    needs_clarification:bool=False
    confidence:dict[str,float]=Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def confidence_is_bounded(cls,value):
        from ..dialogue import SLOTS
        if set(value)-set(SLOTS) or any(not 0<=score<=1 for score in value.values()):
            raise ValueError("Confidence must be between zero and one for known profile fields")
        return value

class ExtractedProfile(StrictSchema):
    education_level:ShortText|None=None
    age_band:ShortText|None=None
    current_occupation:ShortText|None=None
    family_occupation:ShortText|None=None
    skills:list[ShortText]=Field(default_factory=list,max_length=30)
    interests:list[ShortText]=Field(default_factory=list,max_length=30)
    tools:list[ShortText]=Field(default_factory=list,max_length=30)
    mobility_level:ShortText|None=None
    max_travel_distance:float|None=Field(default=None,ge=0,le=500)
    employment_preference:Literal["wage_employment","self_employment","either"]|None=None
    time_available:ShortText|None=None
    district:str|None=Field(default=None,max_length=120)
    block:ShortText|None=Field(default=None,max_length=120)
    constraints:list[ShortText]=Field(default_factory=list,max_length=30)
    training_duration_preference:ShortText|None=None

class RecommendationExplanation(StrictSchema):
    relevance:str=Field(min_length=1,max_length=500)
    matched_signals:list[str]=Field(default_factory=list,max_length=20)
    uncertainties:list[str]=Field(default_factory=list,max_length=20)
    verification_notice:str=Field(min_length=1,max_length=500)

class RecommendationContext(StrictSchema):
    pathway_id:str=Field(min_length=1,max_length=120)
    title:ShortText
    sector:ShortText
    description:str=Field(max_length=1000)
    deterministic_score:float=Field(ge=0,le=1)
    interest_score:float=Field(ge=0,le=1)
    skills_score:float=Field(ge=0,le=1)
    demand_score:float=Field(ge=0,le=1)
    feasibility_score:float=Field(ge=0,le=1)
    preference_score:float=Field(ge=0,le=1)
    semantic_interest_similarity:float=Field(ge=0,le=1)
    semantic_skill_similarity:float=Field(ge=0,le=1)
    stated_interests:list[ShortText]=Field(default_factory=list,max_length=20)
    matched_skills:list[ShortText]=Field(default_factory=list,max_length=30)
    missing_skills:list[ShortText]=Field(default_factory=list,max_length=30)
    duration_hours:int|None=Field(default=None,ge=0,le=10000)
    minimum_education:ShortText
    prerequisites:list[ShortText]=Field(default_factory=list,max_length=30)
    demand_label:ShortText
    demand_source:str|None=Field(default=None,max_length=200)
    centre_found:bool
    approximate_distance_km:float|None=Field(default=None,ge=0,le=21000)
    within_travel_limit:bool
    preference_fit:ShortText
    data_sources:list[str]=Field(default_factory=list,max_length=8)
    model_version:ShortText

class RecommendationExplanationChoice(StrictSchema):
    primary_reason:Literal["interest_alignment","skill_alignment","combined_alignment","exploration"]
    training_focus:Literal["build_missing_skills","verify_requirements"]
    next_step:Literal["counsellor_review","contact_listed_centre","review_travel"]

class ActionPlan(StrictSchema):
    steps:list[str]=Field(min_length=1,max_length=8)
    counsellor_review_required:bool=True

class CounsellorBrief(StrictSchema):
    summary:str=Field(min_length=1,max_length=1000)
    beneficiary_stated_goals:list[str]=Field(default_factory=list,max_length=12)
    constraints_to_discuss:list[str]=Field(default_factory=list,max_length=12)
    verification_questions:list[str]=Field(default_factory=list,max_length=12)
    human_review_required:bool=True

class FollowUpQuestionSelection(StrictSchema):
    question_ids:list[Literal["review_pathway","enrolment","barrier","complete_training","work_status","continue_work","verify_report","support"]]=Field(min_length=1,max_length=3)

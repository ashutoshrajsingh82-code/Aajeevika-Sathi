"""Strict schemas for bounded agent decisions and approved tool inputs."""
from datetime import date
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

ToolName=Literal[
    "get_beneficiary_profile","get_interview_status","search_pathways","get_pathway_details",
    "get_district_demand","search_training_centres","get_training_centre_details",
    "check_training_eligibility","search_government_schemes","generate_action_plan",
    "create_counsellor_handoff","schedule_followup",
]

class StrictInput(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)

class AgentDecision(StrictInput):
    action:Literal["call_tool","goal_achieved","human_verification_required","required_information_unavailable"]
    tool_name:ToolName|None=None
    arguments:dict=Field(default_factory=dict,max_length=12)

    @model_validator(mode="after")
    def tool_shape_is_consistent(self):
        if self.action=="call_tool" and self.tool_name is None:raise ValueError("Tool selection requires an approved tool name")
        if self.action!="call_tool" and (self.tool_name is not None or self.arguments):raise ValueError("Terminal decisions cannot include a tool call")
        return self

class AgentRunRequest(StrictInput):
    goal:str=Field(min_length=3,max_length=400)

class NoArguments(StrictInput):pass

class PathwaySearchInput(StrictInput):
    sector:str|None=Field(default=None,max_length=100)
    limit:int=Field(default=3,ge=1,le=5)

class PathwayDetailsInput(StrictInput):
    pathway_id:str=Field(min_length=1,max_length=80)

class CentreSearchInput(StrictInput):
    pathway_id:str|None=Field(default=None,max_length=80)
    limit:int=Field(default=5,ge=1,le=10)

class CentreDetailsInput(StrictInput):
    centre_id:str=Field(min_length=1,max_length=80)

class EligibilityInput(StrictInput):
    pathway_id:str=Field(min_length=1,max_length=80)

class SchemeSearchInput(StrictInput):
    query:str=Field(min_length=3,max_length=200)

class ActionPlanInput(StrictInput):
    pathway_id:str|None=Field(default=None,max_length=80)

class HandoffInput(StrictInput):
    reason_code:Literal["eligibility","pathway_availability","training_centre","profile_support","other"]

class FollowUpInput(StrictInput):
    stage:Literal["recommendation_check_in","pathway_selected","training_start","training_completion","employment_check_in"]
    due_date:date|None=None

    @model_validator(mode="after")
    def date_not_in_past(self):
        if self.due_date and self.due_date<date.today():raise ValueError("Follow-up date cannot be in the past")
        return self

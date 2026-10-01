from pydantic import BaseModel, Field
from typing import Any

class LoginBody(BaseModel): username:str=Field(min_length=1,max_length=120); password:str=Field(min_length=1,max_length=200)
class AIInterviewRequest(BaseModel): slot:str=Field(min_length=1,max_length=60); answer:str=Field(min_length=1,max_length=2000); input_method:str=Field(default="text",pattern="^(text|browser_voice|server_transcription)$")
class StartSession(BaseModel): language:str=Field(pattern="^(en|hi)$")
class Message(BaseModel): text:str=Field(min_length=1,max_length=2000); input_method:str=Field(default="text",pattern="^(text|browser_voice|server_transcription)$")
class ConsentWithdrawal(BaseModel): session_id:str
class SelectPathway(BaseModel): session_id:str; pathway_id:str
class FollowUpCreate(BaseModel): session_id:str; stage:str; due_date:str=""; note:str=""
class FollowUpUpdate(BaseModel): status:str=Field(pattern="^(pending|complete|cancelled)$")
class HandoffCreate(BaseModel): session_id:str; reason:str=Field(min_length=3,max_length=300); priority:str=Field(default="normal",pattern="^(normal|high|urgent)$")
class HandoffUpdate(BaseModel): status:str=Field(pattern="^(open|accepted|resolved)$")
class OutcomeUpdate(BaseModel): outcome:str=Field(pattern="^(unknown|enrolled|training|employed|self_employed|not_proceeding)$"); note:str=Field(default="",max_length=1000)
class DemoProfile(BaseModel):
    language:str=Field(default="en",pattern="^(en|hi)$"); district:str=Field(default="Nagpur",max_length=120); block:str=Field(default="Demo block",max_length=120); age_band:str="25-34"; education_level:str="10th"; current_occupation:str=Field(default="daily wage work",max_length=200); family_occupation:str=Field(default="garment work",max_length=200); skills:list[str]=["basic stitching","measurement"]; interests:list[str]=["tailoring","self employment"]; tools:list[str]=[]; employment_preference:str="self_employment"; time_available:str="weekends"; max_travel_distance:float=Field(default=15,ge=0,le=500); latitude:float=Field(default=21.1458,ge=-90,le=90); longitude:float=Field(default=79.0882,ge=-180,le=180); constraints:list[str]=[]

class ProfileOut(BaseModel):
    id:str; session_id:str; language:str; district:str|None=None; block:str|None=None; age_band:str|None=None; education_level:str|None=None; current_occupation:str|None=None; family_occupation:str|None=None; skills:list[str]=[]; interests:list[str]=[]; tools:list[str]=[]; mobility_level:str|None=None; max_travel_distance:float|None=None; employment_preference:str|None=None; time_available:str|None=None; training_duration_preference:str|None=None; constraints:list[str]=[]; consent_status:bool

class ProfileEvidenceUpdate(BaseModel):
    action:str=Field(pattern="^(confirm|correct|remove)$")
    value:Any=None

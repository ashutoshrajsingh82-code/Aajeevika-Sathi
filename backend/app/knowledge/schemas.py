from datetime import date
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,model_validator,HttpUrl
from typing import Annotated

CleanText=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=500)]

class IngestDocument(BaseModel):
    model_config=ConfigDict(extra="forbid")
    title:CleanText
    source:CleanText|None=None
    source_url:HttpUrl|None=None
    authority:CleanText="Unknown issuing authority"
    ministry:str|None=Field(default=None,max_length=200)
    department:str|None=Field(default=None,max_length=200)
    scheme_name:str|None=Field(default=None,max_length=240)
    document_type:str=Field(default="source_document",max_length=100)
    publication_date:date|None=None
    category:Literal["scheme","course","training_centre","eligibility","qualification","district_livelihood","general"]
    district:str|None=Field(default=None,max_length=120)
    state:str|None=Field(default=None,max_length=120)
    effective_date:date|None=None
    last_verified:date|None=None
    version:str=Field(default="1",max_length=80)
    language:str=Field(default="unknown",max_length=40)
    source_type:Literal["official_government","secondary_source","demo","unknown"]="unknown"
    supersedes_document_id:str|None=Field(default=None,max_length=120)
    status:Literal["VERIFIED","STALE","UNKNOWN","DEMO"]="UNKNOWN"
    content:str=Field(min_length=1,max_length=200000)

    @model_validator(mode="after")
    def verification_date_required(self):
        if self.status in {"VERIFIED","STALE"} and self.last_verified is None:
            raise ValueError("VERIFIED and STALE documents require last_verified")
        if not self.source and not self.source_url:
            raise ValueError("Provide a source label or source_url")
        return self

class KnowledgeQuestion(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question:str=Field(min_length=3,max_length=1000)
    category:Literal["scheme","course","training_centre","eligibility","qualification","district_livelihood","general"]|None=None
    district:str|None=Field(default=None,max_length=120)
    state:str|None=Field(default=None,max_length=120)

class OfficialSourceImport(BaseModel):
    model_config=ConfigDict(extra="forbid")
    url:HttpUrl

class VerificationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["OFFICIAL_VERIFIED","SECONDARY_SOURCE","REJECTED"]
    note:str=Field(min_length=10,max_length=1000)
    ocr_reviewed:bool=False

class GroundedClaim(BaseModel):
    model_config=ConfigDict(extra="forbid")
    text:str=Field(min_length=1,max_length=500)
    cited_chunk_ids:list[str]=Field(min_length=1,max_length=8)

class GroundedAnswer(BaseModel):
    model_config=ConfigDict(extra="forbid")
    answer:str=Field(min_length=1,max_length=1500)
    cited_chunk_ids:list[str]=Field(default_factory=list,max_length=8)
    claims:list[GroundedClaim]=Field(default_factory=list,max_length=20)
    requires_counsellor_verification:bool=False

"""Allowlisted, permission-checked livelihood planning tools."""
from datetime import date
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import func
from ...models import (
    AuditLog,BeneficiaryCase,DemandSignal,FollowUp,Handoff,InterviewSession,
    KnowledgeDocument,Pathway,RecommendationRecord,TrainingCentre,
)
from ...planning import action_plan
from ...recommender import recommend
from ...knowledge.service import KnowledgeService
from ..agents.livelihood_schemas import (
    ActionPlanInput,AgentDecision,CentreDetailsInput,CentreSearchInput,
    EligibilityInput,FollowUpInput,HandoffInput,NoArguments,PathwayDetailsInput,
    PathwaySearchInput,SchemeSearchInput,
)

HANDOFF_REASONS={
    "eligibility":"Counsellor verification needed for training eligibility.",
    "pathway_availability":"Counsellor to verify pathway availability and current details.",
    "training_centre":"Counsellor to verify training-centre location and availability.",
    "profile_support":"Beneficiary requested counsellor support with the livelihood plan.",
    "other":"Counsellor review requested by the livelihood planning workflow.",
}
TOOL_DESCRIPTIONS={
    "get_beneficiary_profile":"Read the minimal consented profile fields needed for planning.",
    "get_interview_status":"Read the consented interview workflow state and completion percentage.",
    "search_pathways":"Rank active catalogue pathways using the existing deterministic recommender; records may be samples.",
    "get_pathway_details":"Read one active pathway by its catalogue identifier.",
    "get_district_demand":"Read district demand signals from the existing catalogue and preserve their sample label.",
    "search_training_centres":"Search catalogue centres only in the beneficiary's profile district.",
    "get_training_centre_details":"Read one catalogue centre in the beneficiary's district; availability remains unverified.",
    "check_training_eligibility":"Return listed prerequisites for counsellor review; never approve eligibility.",
    "search_government_schemes":"Search indexed scheme passages and return only manually verified official sources.",
    "generate_action_plan":"Build the existing deterministic action plan for an active pathway.",
    "create_counsellor_handoff":"Create or reuse a normal-priority handoff with a fixed approved reason.",
    "schedule_followup":"Create or reuse a pending follow-up using a fixed stage note and optional future date.",
}
FOLLOWUP_NOTES={
    "recommendation_check_in":"Check whether the beneficiary wants to continue.",
    "pathway_selected":"Review the selected pathway and next steps.",
    "training_start":"Check training start and any support needs.",
    "training_completion":"Check training completion and next steps.",
    "employment_check_in":"Check livelihood progress and requested support.",
}

class ToolInputError(ValueError):pass

class LivelihoodTools:
    """Each operation is bounded to a consented session and known business records."""
    def __init__(self,db:Session,beneficiary_session_id:str,actor:dict):
        self.db=db;self.session_id=beneficiary_session_id;self.actor=actor
        self.schemas={
            "get_beneficiary_profile":NoArguments,"get_interview_status":NoArguments,
            "search_pathways":PathwaySearchInput,"get_pathway_details":PathwayDetailsInput,
            "get_district_demand":NoArguments,"search_training_centres":CentreSearchInput,
            "get_training_centre_details":CentreDetailsInput,"check_training_eligibility":EligibilityInput,
            "search_government_schemes":SchemeSearchInput,"generate_action_plan":ActionPlanInput,
            "create_counsellor_handoff":HandoffInput,"schedule_followup":FollowUpInput,
        }

    def descriptions(self):
        return [{"name":name,"description":TOOL_DESCRIPTIONS[name],"input_schema":schema.model_json_schema()} for name,schema in self.schemas.items()]

    def _session(self):
        if self.actor.get("role") not in {"admin","counsellor"} or not self.actor.get("username"):
            raise PermissionError("An authenticated counsellor or administrator is required")
        session=self.db.get(InterviewSession,self.session_id)
        if not session:raise ValueError("Beneficiary session not found")
        if not session.consent_at:raise PermissionError("Beneficiary consent is required")
        return session

    def execute(self,name:str,arguments:dict)->dict:
        session=self._session()
        if name not in self.schemas:
            self._audit(str(name)[:80],"rejected",{"reason":"tool_not_allowlisted"})
            raise ToolInputError("Tool is not in the approved registry")
        try:parsed=self.schemas[name].model_validate(arguments)
        except ValidationError as exc:
            self._audit(name,"rejected",{"reason":"invalid_arguments"})
            raise ToolInputError("Tool arguments are invalid") from exc
        method=getattr(self,"_"+name)
        try:
            result=method(session,parsed)
        except Exception as exc:
            self._audit(name,"failed",{"error_type":type(exc).__name__})
            raise
        self._audit(name,"success",self._summary(result))
        return result

    def _audit(self,name,outcome,summary):
        # Log tool names and bounded result metadata only; never log profile values or prompts.
        self.db.add(AuditLog(action="livelihood_agent_tool",entity_type="interview_session",entity_id=self.session_id,
            detail=f"tool:{name}; outcome:{outcome}; result:{summary}"[:1000]))

    @staticmethod
    def _summary(result):
        if not isinstance(result,dict):return {"type":type(result).__name__}
        safe={key:result[key] for key in ("status","count","result_count","reason","handoff_id","followup_id","recommendation_count") if key in result}
        if "items" in result:safe["result_count"]=len(result["items"])
        if "recommendations" in result:safe["recommendation_count"]=len(result["recommendations"])
        return safe

    def _get_beneficiary_profile(self,session,args):
        profile=session.profile or {}
        fields=("district","block","education_level","skills","interests","employment_preference","time_available","training_duration_preference","mobility_level","max_travel_distance","constraints")
        return {"status":"available","profile":{key:profile[key] for key in fields if key in profile}}

    def _get_interview_status(self,session,args):
        return {"status":"available","state":session.state,"completion_percentage":session.completion_percentage,"completed":session.completed_at is not None}

    def _recommendations(self,session):
        return recommend(session.profile or {},self.db.query(Pathway).filter_by(active=True).all(),self.db.query(TrainingCentre).all(),self.db.query(DemandSignal).all())

    @staticmethod
    def _pathway_view(item):
        pathway=item["pathway"]
        centre=item.get("centre")
        return {"pathway_id":pathway.id,"title":pathway.title,"sector":pathway.sector,"description":pathway.description[:500],"skills":list(pathway.skills or []),"prerequisites":list(pathway.prerequisites or []),"minimum_education":pathway.min_education,"duration_hours":pathway.duration_hours,"recommendation_score":item["score"],"matched_skills":item["matched_skills"],"missing_skills":item["missing_skills"],"source":pathway.source,"source_url":pathway.source_url,"centre":LivelihoodTools._centre_view(centre) if centre else None,"data_status":"demo_or_unverified"}

    def _search_pathways(self,session,args):
        rows=self._recommendations(session)
        if args.sector:rows=[item for item in rows if args.sector.casefold() in item["pathway"].sector.casefold() or args.sector.casefold() in item["pathway"].title.casefold()]
        items=[self._pathway_view(item) for item in rows[:args.limit]]
        return {"status":"available" if items else "unavailable","items":items,"message":"Catalogue pathways are sample records; verify availability and eligibility with a counsellor." if items else "No matching pathway is listed in the current catalogue."}

    def _get_pathway_details(self,session,args):
        row=self.db.get(Pathway,args.pathway_id)
        if not row or not row.active:return {"status":"unavailable","message":"Pathway is not in the active catalogue."}
        item=next((x for x in self._recommendations(session) if x["pathway"].id==row.id),None)
        if item:return {"status":"available","pathway":self._pathway_view(item),"eligibility_status":"requires_counsellor_verification"}
        return {"status":"available","pathway":{"pathway_id":row.id,"title":row.title,"sector":row.sector,"description":row.description[:500],"skills":list(row.skills or []),"prerequisites":list(row.prerequisites or []),"minimum_education":row.min_education,"duration_hours":row.duration_hours,"source":row.source,"source_url":row.source_url,"data_status":"demo_or_unverified"},"eligibility_status":"requires_counsellor_verification"}

    def _get_district_demand(self,session,args):
        district=(session.profile or {}).get("district")
        if not district:return {"status":"unavailable","message":"District is missing from the validated beneficiary profile."}
        rows=self.db.query(DemandSignal).filter(func.lower(DemandSignal.district)==str(district).casefold()).all()
        return {"status":"available" if rows else "unavailable","district":district,"items":[{"sector":row.sector,"label":row.demand_label,"source":row.source,"year":row.year,"sample_only":True,"measured_demand":False} for row in rows],"message":"District records are synthetic samples, not measured demand." if rows else "No district demand record is indexed."}

    def _search_training_centres(self,session,args):
        district=(session.profile or {}).get("district")
        if not district:return {"status":"unavailable","message":"District is missing from the validated beneficiary profile."}
        query=self.db.query(TrainingCentre).filter(func.lower(TrainingCentre.district)==str(district).casefold())
        if args.pathway_id:
            pathway=self.db.get(Pathway,args.pathway_id)
            if not pathway or not pathway.active:raise ToolInputError("Pathway is not active")
            query=query.filter(TrainingCentre.pathway_ids.contains([args.pathway_id]))
        rows=query.limit(args.limit).all()
        return {"status":"available" if rows else "unavailable","items":[self._centre_view(row) for row in rows],"message":"Catalogue centre records are not verified for current operation; call to confirm before travel." if rows else "No training centre is listed for this district and pathway."}

    @staticmethod
    def _centre_view(row):
        return {"centre_id":row.id,"name":row.name,"district":row.district,"block":row.block,"address":row.address,"contact":row.contact,"accessibility":row.accessibility,"pathway_ids":list(row.pathway_ids or []),"source":row.source,"verification_status":"unverified_demo_or_catalogue"}

    def _get_training_centre_details(self,session,args):
        row=self.db.get(TrainingCentre,args.centre_id)
        if not row:return {"status":"unavailable","message":"Training centre is not in the catalogue."}
        district=(session.profile or {}).get("district")
        if district and row.district.casefold()!=str(district).casefold():raise ToolInputError("Centre is outside the beneficiary district; use the district-scoped centre search")
        return {"status":"available","centre":self._centre_view(row),"message":"Verify centre existence, contact, accessibility, schedule, and fees before travel."}

    def _check_training_eligibility(self,session,args):
        pathway=self.db.get(Pathway,args.pathway_id)
        if not pathway or not pathway.active:return {"status":"unavailable","message":"Pathway is not in the active catalogue."}
        return {"status":"human_verification_required","eligibility_approved":False,"pathway_id":pathway.id,"listed_minimum_education":pathway.min_education,"listed_prerequisites":list(pathway.prerequisites or []),"beneficiary_education":(session.profile or {}).get("education_level"),"source":pathway.source,"message":"This tool cannot approve eligibility. A counsellor must verify current official criteria and the beneficiary's documents."}

    def _search_government_schemes(self,session,args):
        hits=KnowledgeService().search_schemes(self.db,args.query,limit=5)
        official=[hit for hit in hits if hit["document"].get("verification_status")=="OFFICIAL_VERIFIED"]
        if not official:return {"status":"unavailable","items":[],"message":"No verified official scheme source is indexed for this query. Do not infer scheme details."}
        return {"status":"available","items":[{"title":hit["document"]["title"],"source_url":hit["document"]["source_url"],"authority":hit["document"]["authority"],"page_number":hit.get("page_number"),"section":hit.get("section"),"passage":hit["text"],"source_identifier":hit["document"]["document_id"],"verified":True} for hit in official]}

    def _generate_action_plan(self,session,args):
        pathway_id=args.pathway_id
        if pathway_id:
            pathway=self.db.get(Pathway,pathway_id)
            if not pathway or not pathway.active:raise ToolInputError("Pathway is not active")
            recommendation={"selected":pathway.id}
        else:
            options=self._recommendations(session)
            recommendation=options[0] if options else None
            pathway_id=recommendation["pathway"].id if recommendation else None
        if not pathway_id:return {"status":"unavailable","items":[],"message":"A pathway must be selected before a plan can be generated."}
        return {"status":"available","pathway_id":pathway_id,"items":action_plan(recommendation),"requires_counsellor_review":True}

    def _create_counsellor_handoff(self,session,args):
        existing=self.db.query(Handoff).filter_by(session_id=session.id).filter(Handoff.status!="resolved").first()
        if existing:return {"status":"available","handoff_id":existing.id,"created":False,"reason":existing.reason}
        reason=HANDOFF_REASONS[args.reason_code]
        handoff=Handoff(session_id=session.id,reason=reason,priority="normal");self.db.add(handoff)
        case=self.db.query(BeneficiaryCase).filter_by(session_id=session.id).one_or_none()
        if case:case.status="counsellor_handoff"
        previous=session.state;session.state="COUNSELLOR_HANDOFF"
        self.db.add(AuditLog(action="handoff_created",entity_type="interview_session",entity_id=session.id,detail="Created by controlled livelihood planning agent."))
        self.db.flush()
        return {"status":"available","handoff_id":handoff.id,"created":True,"reason_code":args.reason_code,"priority":"normal","state_transition":f"{previous}->COUNSELLOR_HANDOFF"}

    def _schedule_followup(self,session,args):
        due=args.due_date.isoformat() if args.due_date else ""
        existing=self.db.query(FollowUp).filter_by(session_id=session.id,stage=args.stage,due_date=due,status="pending").first()
        if existing:return {"status":"available","followup_id":existing.id,"created":False,"stage":existing.stage,"due_date":existing.due_date}
        row=FollowUp(session_id=session.id,stage=args.stage,due_date=due,note=FOLLOWUP_NOTES[args.stage],status="pending");self.db.add(row);self.db.flush()
        return {"status":"available","followup_id":row.id,"created":True,"stage":row.stage,"due_date":row.due_date}

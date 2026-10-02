from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class AIInterviewRequest(BaseModel):
    slot: str = Field(min_length=1, max_length=60)
    answer: str = Field(min_length=1, max_length=2000)
    input_method: str = Field(
        default="text",
        pattern="^(text|browser_voice|server_transcription)$",
    )


class StartSession(BaseModel):
    language: str = Field(pattern="^(en|hi)$")


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    input_method: str = Field(
        default="text",
        pattern="^(text|browser_voice|server_transcription)$",
    )


class ConsentWithdrawal(BaseModel):
    session_id: str


class SelectPathway(BaseModel):
    session_id: str
    pathway_id: str


class RecommendationEvaluationCreate(BaseModel):
    pathway_completed: bool = False
    counsellor_corrected: bool = False
    pathway_mismatch: bool = False
    corrected_pathway_id: str | None = None
    note: str = Field(default="", max_length=1000)


class FollowUpCreate(BaseModel):
    session_id: str
    stage: str = Field(min_length=1, max_length=80)
    due_date: str = Field(default="", max_length=10)
    note: str = Field(default="", max_length=500)
    schedule_offset_days: int | None = Field(
        default=None,
        ge=1,
        le=730,
    )


class FollowUpUpdate(BaseModel):
    status: str = Field(
        pattern="^(SCHEDULED|DUE|CONTACTED|COMPLETED|MISSED|RESCHEDULED|CANCELLED|pending|complete|cancelled)$"
    )
    new_due_date: str = Field(default="", max_length=10)
    note: str = Field(default="", max_length=500)


class OutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str

    outcome: str = Field(
        pattern="^(TRAINING_STARTED|TRAINING_COMPLETED|JOB_FOUND|SELF_EMPLOYED|BUSINESS_STARTED|APPLICATION_SUBMITTED|APPLICATION_REJECTED|DROPPED_OUT|NO_OUTCOME_REPORTED)$"
    )

    note: str = Field(default="", max_length=1000)


class OutcomeVerification(BaseModel):
    verification_status: Literal["VERIFIED", "REJECTED"]
    note: str = Field(min_length=3, max_length=1000)


class HandoffCreate(BaseModel):
    session_id: str
    reason: str = Field(min_length=3, max_length=300)
    priority: str = Field(
        default="normal",
        pattern="^(normal|high|urgent)$",
    )


class HandoffUpdate(BaseModel):
    status: str = Field(
        pattern="^(open|accepted|resolved)$"
    )


class HandoffWorkflowUpdate(BaseModel):
    status: str = Field(
        pattern="^(OPEN|ASSIGNED|IN_REVIEW|CONTACTED|PATHWAY_VERIFIED|REFERRED|ENROLLED|FOLLOW_UP|CLOSED)$"
    )
    note: str = Field(default="", max_length=1000)


class ActionPlanStepUpdate(BaseModel):
    status: str = Field(
        pattern="^(PENDING|IN_PROGRESS|COMPLETED|BLOCKED|VERIFICATION_REQUIRED)$"
    )
    note: str = Field(default="", max_length=500)


class ActionPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    status: Literal[
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "BLOCKED",
        "VERIFICATION_REQUIRED",
    ]
    verification_required: bool
    blocked_reason: str | None = None
    source_ids: list[str] = Field(
        default_factory=list,
        max_length=40,
    )
    details: str = Field(min_length=1, max_length=1000)


class ActionPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1"
    goal: dict[str, Any]
    pathway: dict[str, Any]

    steps: list[ActionPlanStep] = Field(
        min_length=1,
        max_length=20,
    )

    required_documents: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=50,
    )

    training: dict[str, Any]
    training_centre: dict[str, Any] | None = None
    scheme: dict[str, Any]

    dependencies: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=40,
    )

    estimated_timeline: str | None = None
    timeline_note: str = Field(max_length=500)
    verification_required: bool

    missing_information: list[str] = Field(
        default_factory=list,
        max_length=40,
    )

    status: Literal[
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "BLOCKED",
        "VERIFICATION_REQUIRED",
    ]

    created_at: str


class OutcomeUpdate(BaseModel):
    outcome: str = Field(
        pattern="^(unknown|enrolled|training|employed|self_employed|not_proceeding|TRAINING_STARTED|TRAINING_COMPLETED|JOB_FOUND|SELF_EMPLOYED|BUSINESS_STARTED|APPLICATION_SUBMITTED|APPLICATION_REJECTED|DROPPED_OUT|NO_OUTCOME_REPORTED)$"
    )
    note: str = Field(min_length=3, max_length=1000)


class DemoProfile(BaseModel):
    language: str = Field(
        default="en",
        pattern="^(en|hi)$",
    )

    district: str = Field(
        default="Nagpur",
        max_length=120,
    )

    block: str = Field(
        default="Demo block",
        max_length=120,
    )

    age_band: str = "25-34"
    education_level: str = "10th"

    current_occupation: str = Field(
        default="daily wage work",
        max_length=200,
    )

    family_occupation: str = Field(
        default="garment work",
        max_length=200,
    )

    skills: list[str] = [
        "basic stitching",
        "measurement",
    ]

    interests: list[str] = [
        "tailoring",
        "self employment",
    ]

    tools: list[str] = []

    employment_preference: str = "self_employment"
    time_available: str = "weekends"

    max_travel_distance: float = Field(
        default=15,
        ge=0,
        le=500,
    )

    latitude: float = Field(
        default=21.1458,
        ge=-90,
        le=90,
    )

    longitude: float = Field(
        default=79.0882,
        ge=-180,
        le=180,
    )

    constraints: list[str] = []


class ProfileOut(BaseModel):
    id: str
    session_id: str
    language: str
    district: str | None = None
    block: str | None = None
    age_band: str | None = None
    education_level: str | None = None
    current_occupation: str | None = None
    family_occupation: str | None = None
    skills: list[str] = []
    interests: list[str] = []
    tools: list[str] = []
    mobility_level: str | None = None
    max_travel_distance: float | None = None
    employment_preference: str | None = None
    time_available: str | None = None
    training_duration_preference: str | None = None
    constraints: list[str] = []
    consent_status: bool


class ProfileEvidenceUpdate(BaseModel):
    action: str = Field(
        pattern="^(confirm|correct|remove)$"
    )
    value: Any = None


class RAGEvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    category: Literal[
        "eligibility",
        "courses",
        "centres",
        "districts",
        "unknown",
        "outdated_documents",
    ]
    expected_behavior: str = Field(min_length=1, max_length=120)
    retrieved_count: int = Field(default=0, ge=0, le=1000)
    retrieval_success: bool = False
    answer_supported: bool = False
    unknown_handled: bool = False
    outdated_document_detected: bool = False
    note: str = Field(default="", max_length=1000)

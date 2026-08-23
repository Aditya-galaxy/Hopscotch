"""Contracts between agents.

The supervisor validates every worker return against one of these models. A
worker that hallucinates a shape rather than a value fails here, loudly and
cheaply, before anything downstream acts on it.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CaseStage(str, Enum):
    REFERRED = "referred"
    CONSENT_RECEIVED = "consent_received"
    EVALUATING = "evaluating"
    REPORT_DRAFTED = "report_drafted"
    MEETING_SCHEDULED = "meeting_scheduled"
    CLOSED = "closed"


class Sensitivity(str, Enum):
    """Drives which agent identity may read a field."""
    DIRECTORY = "directory"       # name, school, grade
    ADMINISTRATIVE = "administrative"
    CLINICAL = "clinical"         # psychological findings -- narrowest access


class ConsentEvent(BaseModel):
    """What intake-agent extracts from a signed consent form."""
    student_ref: str = Field(description="Opaque student id, never a name")
    school_code: str
    jurisdiction: str = Field(description="Key into JURISDICTIONS")
    consent_signed_on: date | None = Field(
        default=None,
        description="None when the signature date is illegible. The clock does "
                    "NOT start on an unknown date -- that case goes to a human.")
    received_on: date | None = None
    referral_reason: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    source_document: str


class DeadlineComputation(BaseModel):
    """What clock-agent produces. Pure function of the case + calendar."""
    student_ref: str
    jurisdiction: str
    rule_label: str
    clock_started_on: date
    due_on: date
    days_remaining: int
    excluded_days: int = Field(description="Days the rule did not count")
    explanation: str = Field(description="Human-readable, for the audit log")


class DraftedNotice(BaseModel):
    """What casework-agent produces. Never leaves the district unredacted."""
    student_ref: str
    notice_type: Literal["prior_written_notice", "evaluation_plan", "meeting_agenda"]
    body: str
    statutory_citations: list[str] = Field(default_factory=list)
    contains_clinical: bool = True


class FamilyPacket(BaseModel):
    """What family-agent produces. Clinical content is stripped upstream."""
    student_ref: str
    language: str
    letter_text: str
    audio_uri: str | None = None
    explainer_uri: str | None = None
    redaction_applied: bool


class Correction(BaseModel):
    """A human overriding the fleet, on the record.

    Corrections are additive and never destructive: the computed value stays
    visible beside the override, because a coordinator who cannot see what the
    system thought has no way to judge whether it is improving.
    """
    field: Literal["consent_signed_on", "due_on"]
    value: date
    reason: str = Field(description="Why. Required — an unexplained override is "
                                    "indistinguishable from a mistake.")
    by: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    computed_was: str = Field(default="", description="What the fleet had")


class Case(BaseModel):
    student_ref: str
    school_code: str
    jurisdiction: str
    stage: CaseStage = CaseStage.REFERRED
    consent: ConsentEvent | None = None
    deadline: DeadlineComputation | None = None
    escalations_sent: list[int] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DailyBrief(BaseModel):
    """What the coordinator reads before anything else.

    Deliberately shaped rather than free prose. A brief that rambles gets
    skimmed; a brief with a single headline and three short lists gets acted
    on. `headline` is the one thing they would want to know if they read
    nothing else.
    """
    brief_date: str
    headline: str = Field(description="One sentence. The single most important thing.")
    needs_you_today: list[str] = Field(
        default_factory=list, description="Cases a human must touch today")
    moved_overnight: list[str] = Field(
        default_factory=list, description="What the fleet did while nobody watched")
    watch: list[str] = Field(
        default_factory=list, description="Not urgent yet, but heading that way")
    cases_open: int = 0
    generated_by: str = "coordinator"


# --- Medicaid claiming ------------------------------------------------------

class IEPService(BaseModel):
    """A service the IEP authorizes. The claim is measured against this."""
    goal_ref: str
    service: str = Field(description="e.g. 'speech-language therapy, individual'")
    minutes_per_session: int
    sessions_per_week: int
    provider_type: str = Field(description="Approved provider type required")
    starts_on: date
    ends_on: date


class ServiceDelivery(BaseModel):
    """One session actually delivered. What a provider logs."""
    student_ref: str
    goal_ref: str
    service_date: date
    minutes: int = Field(description="Documented duration")
    units_billed: int = Field(description="Units submitted on the claim")
    note: str = Field(description="The provider's session note, free text")
    provider_npi: str = ""
    provider_type: str = ""
    provider_license_expires: date | None = None


class ClaimCheck(BaseModel):
    requirement: str
    passed: bool
    blocking: bool = Field(
        default=True,
        description="A failed blocking check makes the claim unbillable; a "
                    "failed non-blocking one is an audit risk worth fixing.")
    detail: str = ""


class ClaimReadiness(BaseModel):
    """Whether this session could be billed, and if not, precisely why."""
    student_ref: str
    goal_ref: str
    service_date: date
    billable: bool
    checks: list[ClaimCheck] = Field(default_factory=list)
    reviewed_semantically: bool = Field(
        default=False,
        description="False when the narrative check could not run. The claim "
                    "is then NOT marked billable -- unchecked is not clean.")

    @property
    def blocking_failures(self) -> list[ClaimCheck]:
        return [c for c in self.checks if not c.passed and c.blocking]

    @property
    def audit_risks(self) -> list[ClaimCheck]:
        return [c for c in self.checks if not c.passed and not c.blocking]


class WorkerResult(BaseModel):
    """Envelope every worker returns through. The supervisor reads this first."""
    agent: str
    ok: bool
    attempt: int = 1
    payload: dict | None = None
    error: str | None = None
    trace_id: str | None = None

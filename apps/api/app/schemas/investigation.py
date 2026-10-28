"""Investigation review contract (NVIDIA Nemotron + Tavily).

Mirrored in apps/web/src/types/triage.ts and documented in docs/api-contract.md.
Must not import app.schemas.triage (it imports this module).
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class IntegrationStepName(StrEnum):
    IMAGE_ANALYSIS = "image_analysis"
    WEATHER = "weather"
    SATELLITE = "satellite"
    REFERENCE_PHOTOS = "reference_photos"
    DETERMINISTIC_SCORING = "deterministic_scoring"
    AGRONOMY_RESEARCH = "agronomy_research"
    NEMOTRON_REVIEW = "nemotron_review"
    TRANSLATION = "translation"


class IntegrationStatus(StrEnum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    NOT_REQUESTED = "not_requested"
    NOT_CONFIGURED = "not_configured"
    DISABLED = "disabled"


class UsageInfo(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    credits: float | None = Field(default=None, description="Tavily API credits, when reported.")


class IntegrationStep(BaseModel):
    """One step of the investigation as it actually ran. Never a planned or assumed state."""

    step: IntegrationStepName
    provider: str
    model: str | None = None
    status: IntegrationStatus
    duration_ms: int | None = Field(default=None, description="Measured wall time, when timed.")
    detail: str | None = Field(default=None, description="Short, non-sensitive explanation.")
    usage: UsageInfo | None = None


class AgronomySource(BaseModel):
    """A page from an approved agricultural domain, validated by the backend. Retrieval alone
    does not verify the advice on the page."""

    id: str = Field(description="Backend-issued id (S1, S2...). Models may only cite these ids.")
    title: str
    url: str
    publisher: str = Field(description="Organisation that runs the approved domain.")
    domain: str
    region: str = Field(description="Where the publisher's guidance mainly applies.")
    retrieved_at: datetime
    published_at: str | None = Field(
        default=None, description="ISO date reported by the search provider; never inferred."
    )
    excerpt: str = Field(description="Trimmed text from the page; dose instructions removed.")
    crop_relevance: bool
    condition_relevance: bool
    condition_keys: list[str] = Field(default_factory=list)
    validation_status: Literal["validated"] = "validated"


class ReviewStatus(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    DISABLED = "disabled"
    SKIPPED = "skipped"


class EvidenceConsistency(StrEnum):
    CONSISTENT = "consistent"
    MIXED = "mixed"
    INCONSISTENT = "inconsistent"
    INSUFFICIENT = "insufficient"


class SupportStatus(StrEnum):
    SOURCE_BACKED = "source_backed"
    UNVERIFIED = "unverified"
    MODEL_SUGGESTION = "model_suggestion"
    SAFETY_REFERRAL = "safety_referral"


class StepPriority(StrEnum):
    IMMEDIATE = "immediate"
    WITHIN_DAYS = "within_days"
    MONITOR = "monitor"


class FollowUpCategory(StrEnum):
    SYMPTOM_DISTRIBUTION = "symptom_distribution"
    VISIBLE_PATTERN = "visible_pattern"
    DURATION = "duration"
    FIELD_CONDITIONS = "field_conditions"
    PLANT_PART = "plant_part"


class FollowUpAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    NOT_SURE = "not_sure"


class ReviewedObservation(BaseModel):
    text: str
    evidence_ids: list[str] = Field(description="Ids of items in the response's evidence list.")
    condition_key: str | None = None


class KnowledgeFinding(BaseModel):
    claim: str
    source_ids: list[str]
    applicability: str
    support_status: SupportStatus
    verified: bool = Field(description="True only when a cited excerpt shares the claim's terms.")


class SafeNextStep(BaseModel):
    action: str
    rationale: str
    priority: StepPriority
    source_ids: list[str] = Field(default_factory=list)
    requires_expert_review: bool
    support_status: SupportStatus


class FollowUpQuestion(BaseModel):
    id: str
    text: str
    category: FollowUpCategory
    discriminates: list[str] = Field(description="Condition keys the answer helps tell apart.")
    why: str
    options: list[FollowUpAnswer] = Field(
        default_factory=lambda: [FollowUpAnswer.YES, FollowUpAnswer.NO, FollowUpAnswer.NOT_SURE]
    )
    answer: FollowUpAnswer | None = None


class InvestigationReview(BaseModel):
    """Second-stage review of the evidence ledger. Never changes scores, ranking or urgency."""

    status: ReviewStatus
    provider: str
    model: str
    detail: str | None = Field(default=None, description="Why the review is not completed.")
    generated_at: datetime | None = None
    duration_ms: int | None = None
    usage: UsageInfo | None = None
    language: str = Field(default="en", description="Language of the review text.")
    round: int = Field(default=1, ge=1, le=2)
    grounding: Literal["sources_and_evidence", "internal_evidence_only"] | None = None
    leading_condition_key: str | None = None
    reasoning_summary: str = ""
    evidence_consistent: EvidenceConsistency | None = None
    supporting_observations: list[ReviewedObservation] = Field(default_factory=list)
    contradictions: list[ReviewedObservation] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    follow_up_question: FollowUpQuestion | None = None
    knowledge_findings: list[KnowledgeFinding] = Field(default_factory=list)
    safe_next_steps: list[SafeNextStep] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    guardrail_notes: list[str] = Field(
        default_factory=list, description="What the backend removed or changed, and why."
    )
    previous_summary: str | None = None
    what_changed: list[str] = Field(default_factory=list)

"""Deterministic enforcement of the review rules after Nemotron answers.

The prompt asks for safe behaviour; this module makes sure of it. The model can only cite
evidence and source ids the backend issued, only talk about causes already in the ranked list,
never lower an expert-review flag, and never pass chemical instructions or overconfident claims
to the farmer. Every removal is counted in `guardrail_notes`.
"""

import secrets
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.schemas.investigation import (
    AgronomySource,
    EvidenceConsistency,
    FollowUpCategory,
    FollowUpQuestion,
    KnowledgeFinding,
    ReviewedObservation,
    SafeNextStep,
    StepPriority,
    SupportStatus,
)
from app.services.knowledge.safety import (
    is_chemical_instruction,
    looks_like_instructions,
    mentions_chemical_product,
    overstates_certainty,
    supported_by,
)

SUMMARY_LIMIT = 700
ITEM_LIMIT = 320
MAX_OBSERVATIONS = 5
MAX_QUESTIONS = 4
MAX_FINDINGS = 5
MAX_STEPS = 4
MAX_LIMITATIONS = 4

WITHHELD_SUMMARY = (
    "The review summary was withheld by RootCause safety checks. The observations and "
    "contradictions below were still checked against the evidence."
)
REFERRAL_ACTION = (
    "Ask your local agricultural extension office or KVK whether any treatment is needed and "
    "which products are approved for this crop and problem in your area."
)
REFERRAL_RATIONALE = (
    "RootCause does not recommend chemical products, doses or spray schedules; approval and "
    "safe use differ by country and crop."
)

_NOTES = {
    "chemical": "Removed {n} item(s) that mentioned chemical products, doses or spray schedules.",
    "certainty": "Removed {n} item(s) that sounded more certain than the evidence allows.",
    "uncited": "Removed {n} observation(s) that did not cite the supplied evidence.",
    "missing_as_evidence": "Removed {n} item(s) that treated missing data as evidence.",
    "unknown_condition": "Removed {n} item(s) about causes that are not in the ranked list.",
    "fabricated_source": "Removed {n} citation(s) to sources that were not retrieved.",
    "uncited_finding": "Removed {n} guidance claim(s) without a retrieved source.",
    "instructions": "Removed {n} item(s) that looked like instructions rather than evidence.",
    "summary": "The review summary was withheld by safety checks.",
    "question": "The follow-up question was removed: it did not target a listed cause or failed "
    "safety checks.",
}


class ModelObservation(BaseModel):
    text: str = Field(description="One short sentence about what the evidence shows.")
    evidence_ids: list[str] = Field(description="Ids from `evidence` (E1, E2...) it relies on.")
    condition_key: str = Field(description="A condition_key from `causes`, or 'none'.")


class ModelFollowUp(BaseModel):
    text: str = Field(description="One yes/no question the farmer can answer by looking.")
    category: FollowUpCategory
    discriminates: list[str] = Field(description="condition_key values the answer separates.")
    why: str = Field(description="How each answer would change the picture.")


class ModelFinding(BaseModel):
    claim: str = Field(description="What a supplied source excerpt says. No outside knowledge.")
    source_ids: list[str] = Field(description="Ids from `sources` (S1, S2...).")
    applicability: str = Field(description="Limits: region, crop stage, date, uncertainty.")


class ModelStep(BaseModel):
    action: str = Field(description="An observational or non-chemical next step.")
    rationale: str
    priority: StepPriority
    source_ids: list[str] = Field(description="Supporting source ids, or an empty list.")
    requires_expert_review: bool


class ReviewModelOutput(BaseModel):
    reasoning_summary: str = Field(description="2-4 plain sentences; no hidden reasoning.")
    evidence_consistent: EvidenceConsistency
    supporting_observations: list[ModelObservation]
    contradictions: list[ModelObservation]
    unresolved_questions: list[str]
    follow_up_questions: list[ModelFollowUp] = Field(description="At most one question.")
    knowledge_findings: list[ModelFinding]
    safe_next_steps: list[ModelStep]
    limitations: list[str]
    what_changed: list[str] = Field(description="Empty unless a previous review is supplied.")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    original_id: str
    available: bool


@dataclass(frozen=True, slots=True)
class ReviewContext:
    evidence: dict[str, EvidenceRef]
    sources: dict[str, AgronomySource]
    condition_keys: tuple[str, ...]
    requires_expert_review: bool
    round: int = 1


@dataclass(slots=True)
class GuardedReview:
    reasoning_summary: str
    evidence_consistent: EvidenceConsistency
    supporting_observations: list[ReviewedObservation]
    contradictions: list[ReviewedObservation]
    unresolved_questions: list[str]
    follow_up_question: FollowUpQuestion | None
    knowledge_findings: list[KnowledgeFinding]
    safe_next_steps: list[SafeNextStep]
    limitations: list[str]
    what_changed: list[str]
    guardrail_notes: list[str] = field(default_factory=list)

    @property
    def cited_source_ids(self) -> list[str]:
        ids = [i for f in self.knowledge_findings for i in f.source_ids]
        ids += [i for s in self.safe_next_steps for i in s.source_ids]
        return list(dict.fromkeys(ids))


def new_question_id() -> str:
    return f"fq_{secrets.token_hex(6)}"


def clip(text: str, limit: int = ITEM_LIMIT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _problem(text: str, *, strict: bool = False) -> str | None:
    if (mentions_chemical_product if strict else is_chemical_instruction)(text):
        return "chemical"
    if overstates_certainty(text):
        return "certainty"
    if looks_like_instructions(text):
        return "instructions"
    return None


def enforce(
    output: ReviewModelOutput,
    ctx: ReviewContext,
    *,
    question_id: Callable[[], str] = new_question_id,
) -> GuardedReview:
    removed: Counter[str] = Counter()

    summary = clip(output.reasoning_summary, SUMMARY_LIMIT)
    if not summary or _problem(summary):
        removed["summary"] = 1
        summary = WITHHELD_SUMMARY

    def observations(items: list[ModelObservation]) -> list[ReviewedObservation]:
        kept: list[ReviewedObservation] = []
        for item in items:
            refs = [ctx.evidence[e] for e in dict.fromkeys(item.evidence_ids) if e in ctx.evidence]
            available = [ref for ref in refs if ref.available]
            if not refs:
                removed["uncited"] += 1
                continue
            if not available:
                removed["missing_as_evidence"] += 1
                continue
            key = item.condition_key.strip()
            if key and key.lower() != "none" and key not in ctx.condition_keys:
                removed["unknown_condition"] += 1
                continue
            text = clip(item.text)
            problem = _problem(text)
            if problem or not text:
                removed[problem or "uncited"] += 1
                continue
            kept.append(
                ReviewedObservation(
                    text=text,
                    evidence_ids=[ref.original_id for ref in available],
                    condition_key=key if key in ctx.condition_keys else None,
                )
            )
        return kept[:MAX_OBSERVATIONS]

    def strings(items: list[str], limit: int) -> list[str]:
        kept: list[str] = []
        for raw in items:
            text = clip(raw)
            problem = _problem(text)
            if problem:
                removed[problem] += 1
            elif text:
                kept.append(text)
        return kept[:limit]

    question: FollowUpQuestion | None = None
    if output.follow_up_questions and ctx.round == 1:
        q = output.follow_up_questions[0]
        targets = [k for k in dict.fromkeys(q.discriminates) if k in ctx.condition_keys]
        text, why = clip(q.text, 200), clip(q.why)
        if targets and text and not _problem(text, strict=True) and not _problem(why):
            question = FollowUpQuestion(
                id=question_id(), text=text, category=q.category, discriminates=targets, why=why
            )
        else:
            removed["question"] = 1

    findings: list[KnowledgeFinding] = []
    for finding in output.knowledge_findings:
        ids = [s for s in dict.fromkeys(finding.source_ids) if s in ctx.sources]
        removed["fabricated_source"] += len(set(finding.source_ids) - set(ids))
        if not ids:
            removed["uncited_finding"] += 1
            continue
        claim, applicability = clip(finding.claim), clip(finding.applicability)
        problem = _problem(claim, strict=True) or _problem(applicability, strict=True)
        if problem:
            removed[problem] += 1
            continue
        verified = any(supported_by(claim, ctx.sources[s].excerpt) for s in ids)
        findings.append(
            KnowledgeFinding(
                claim=claim,
                source_ids=ids,
                applicability=applicability,
                support_status=SupportStatus.SOURCE_BACKED
                if verified
                else SupportStatus.UNVERIFIED,
                verified=verified,
            )
        )

    steps: list[SafeNextStep] = []
    needs_referral = False
    for step in output.safe_next_steps:
        action, rationale = clip(step.action), clip(step.rationale)
        if mentions_chemical_product(action) or mentions_chemical_product(rationale):
            removed["chemical"] += 1
            needs_referral = True
            continue
        problem = _problem(action) or _problem(rationale)
        if problem or not action:
            removed[problem or "uncited"] += 1
            continue
        ids = [s for s in dict.fromkeys(step.source_ids) if s in ctx.sources]
        removed["fabricated_source"] += len(set(step.source_ids) - set(ids))
        backed = any(supported_by(f"{action} {rationale}", ctx.sources[s].excerpt) for s in ids)
        support = (
            SupportStatus.SOURCE_BACKED
            if backed
            else SupportStatus.UNVERIFIED
            if ids
            else SupportStatus.MODEL_SUGGESTION
        )
        steps.append(
            SafeNextStep(
                action=action,
                rationale=rationale,
                priority=step.priority,
                source_ids=ids,
                requires_expert_review=step.requires_expert_review or ctx.requires_expert_review,
                support_status=support,
            )
        )
    steps = steps[:MAX_STEPS]
    if needs_referral:
        steps.append(
            SafeNextStep(
                action=REFERRAL_ACTION,
                rationale=REFERRAL_RATIONALE,
                priority=StepPriority.WITHIN_DAYS,
                requires_expert_review=True,
                support_status=SupportStatus.SAFETY_REFERRAL,
            )
        )

    return GuardedReview(
        reasoning_summary=summary,
        evidence_consistent=output.evidence_consistent,
        supporting_observations=observations(output.supporting_observations),
        contradictions=observations(output.contradictions),
        unresolved_questions=strings(output.unresolved_questions, MAX_QUESTIONS),
        follow_up_question=question,
        knowledge_findings=findings[:MAX_FINDINGS],
        safe_next_steps=steps,
        limitations=strings(output.limitations, MAX_LIMITATIONS),
        what_changed=strings(output.what_changed, MAX_LIMITATIONS) if ctx.round > 1 else [],
        guardrail_notes=[_NOTES[key].format(n=n) for key, n in removed.items() if n],
    )

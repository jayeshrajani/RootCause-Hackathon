from datetime import UTC, datetime
from typing import Any

import pytest

from app.schemas.investigation import AgronomySource, SupportStatus
from app.services.investigation.guardrails import (
    REFERRAL_ACTION,
    WITHHELD_SUMMARY,
    EvidenceRef,
    ReviewContext,
    ReviewModelOutput,
    enforce,
)
from app.services.knowledge.safety import (
    is_chemical_instruction,
    mentions_chemical_product,
    overstates_certainty,
    safe_excerpt,
    supported_by,
)
from tests.investigation_helpers import S1_EXCERPT, review_output

SOURCE = AgronomySource(
    id="S1",
    title="Early blight of tomato",
    url="https://agritech.tnau.ac.in/x",
    publisher="Tamil Nadu Agricultural University",
    domain="agritech.tnau.ac.in",
    region="India",
    retrieved_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
    excerpt=S1_EXCERPT,
    crop_relevance=True,
    condition_relevance=True,
    condition_keys=["early_blight"],
)


def context(**overrides: Any) -> ReviewContext:
    options: dict[str, Any] = {
        "evidence": {
            "E1": EvidenceRef("ev_farmer_report", True),
            "E2": EvidenceRef("ev_photo_1", True),
            "E4": EvidenceRef("ev_satellite", False),
        },
        "sources": {"S1": SOURCE},
        "condition_keys": ("early_blight", "late_blight"),
        "requires_expert_review": False,
    }
    return ReviewContext(**(options | overrides))


def run(ctx: ReviewContext | None = None, **output: Any) -> Any:
    return enforce(
        ReviewModelOutput.model_validate(review_output(**output)),
        ctx or context(),
        question_id=lambda: "fq_000000000001",
    )


def test_valid_review_passes_with_backend_ids_and_support_status() -> None:
    guarded = run()

    assert guarded.guardrail_notes == []
    assert guarded.supporting_observations[0].evidence_ids == ["ev_photo_1"]
    assert guarded.contradictions[0].condition_key == "late_blight"
    finding = guarded.knowledge_findings[0]
    assert finding.verified and finding.support_status == SupportStatus.SOURCE_BACKED
    assert guarded.safe_next_steps[0].support_status == SupportStatus.SOURCE_BACKED
    question = guarded.follow_up_question
    assert question is not None and question.id == "fq_000000000001"
    assert question.discriminates == ["early_blight", "late_blight"]
    assert guarded.cited_source_ids == ["S1"]
    assert guarded.what_changed == []


def test_invented_evidence_and_missing_data_are_not_evidence() -> None:
    guarded = run(
        supporting_observations=[
            {"text": "Spots seen.", "evidence_ids": ["E9"], "condition_key": "early_blight"},
            {"text": "Canopy is healthy.", "evidence_ids": ["E4"], "condition_key": "none"},
        ]
    )

    assert guarded.supporting_observations == []
    assert any("did not cite" in note for note in guarded.guardrail_notes)
    assert any("missing data" in note for note in guarded.guardrail_notes)


def test_causes_outside_the_ranked_list_cannot_be_promoted() -> None:
    guarded = run(
        supporting_observations=[
            {"text": "This fits leaf mold.", "evidence_ids": ["E2"], "condition_key": "leaf_mold"}
        ],
        follow_up_questions=[
            {
                "text": "Is there olive mould?",
                "category": "visible_pattern",
                "discriminates": ["leaf_mold"],
                "why": "Leaf mold.",
            }
        ],
    )

    assert guarded.supporting_observations == []
    assert guarded.follow_up_question is None
    assert any("not in the ranked list" in note for note in guarded.guardrail_notes)


def test_fabricated_sources_are_rejected() -> None:
    guarded = run(
        knowledge_findings=[
            {"claim": "Copper always cures blight.", "source_ids": ["S7"], "applicability": "x"}
        ],
        safe_next_steps=[
            {
                "action": "Check leaf undersides for white mould.",
                "rationale": "Separates late blight.",
                "priority": "immediate",
                "source_ids": ["S1", "S9"],
                "requires_expert_review": False,
            }
        ],
    )

    assert guarded.knowledge_findings == []
    assert guarded.safe_next_steps[0].source_ids == ["S1"]
    assert any("not retrieved" in note for note in guarded.guardrail_notes)
    assert any("without a retrieved source" in note for note in guarded.guardrail_notes)


def test_weak_source_overlap_is_marked_unverified_not_backed() -> None:
    guarded = run(
        knowledge_findings=[
            {
                "claim": "Mulching paddy straw conserves moisture.",
                "source_ids": ["S1"],
                "applicability": "General.",
            }
        ]
    )

    finding = guarded.knowledge_findings[0]
    assert not finding.verified and finding.support_status == SupportStatus.UNVERIFIED


def test_chemical_steps_are_replaced_by_an_extension_referral() -> None:
    guarded = run(
        safe_next_steps=[
            {
                "action": "Spray a copper fungicide every 7 days.",
                "rationale": "Protects new leaves.",
                "priority": "immediate",
                "source_ids": [],
                "requires_expert_review": False,
            }
        ],
        knowledge_findings=[
            {
                "claim": "Apply mancozeb at 2 g per litre.",
                "source_ids": ["S1"],
                "applicability": "India.",
            }
        ],
    )

    assert [s.action for s in guarded.safe_next_steps] == [REFERRAL_ACTION]
    referral = guarded.safe_next_steps[0]
    assert referral.support_status == SupportStatus.SAFETY_REFERRAL
    assert referral.requires_expert_review
    assert guarded.knowledge_findings == []
    assert any("chemical" in note for note in guarded.guardrail_notes)


def test_overconfident_summary_is_withheld_and_items_dropped() -> None:
    guarded = run(
        reasoning_summary="This is definitely early blight.",
        unresolved_questions=["The disease is confirmed as early blight.", "Is it spreading?"],
    )

    assert guarded.reasoning_summary == WITHHELD_SUMMARY
    assert guarded.unresolved_questions == ["Is it spreading?"]


def test_hedged_confirmation_language_is_allowed() -> None:
    guarded = run(reasoning_summary="A lab test would confirm it; the photos cannot confirm it.")

    assert guarded.reasoning_summary.startswith("A lab test would confirm")


def test_expert_review_is_never_lowered() -> None:
    guarded = run(context(requires_expert_review=True))

    assert all(step.requires_expert_review for step in guarded.safe_next_steps)


def test_second_round_keeps_what_changed_and_drops_new_questions() -> None:
    guarded = run(context(round=2), what_changed=["Rings make early blight more likely."])

    assert guarded.what_changed == ["Rings make early blight more likely."]
    assert guarded.follow_up_question is None


def test_long_text_is_clipped() -> None:
    guarded = run(limitations=["word " * 200])

    assert len(guarded.limitations[0]) <= 320


@pytest.mark.parametrize(
    "text",
    [
        "Spray mancozeb on the plants.",
        "Use 2.5 g per litre of water.",
        "Mix 0.2% WP formulation.",
        "Apply fungicide every 7-10 days.",
        "Use BrandX® for control.",
    ],
)
def test_chemical_instructions_are_detected(text: str) -> None:
    assert is_chemical_instruction(text)


@pytest.mark.parametrize(
    "text",
    [
        "Remove 2 or 3 lower leaves per plant.",
        "About 50% of the leaves have spots.",
        "Check the field every 3 days.",
        "The farmer said no fungicide was used.",
    ],
)
def test_ordinary_text_is_not_a_chemical_instruction(text: str) -> None:
    assert not is_chemical_instruction(text)


def test_any_product_class_counts_for_model_written_actions() -> None:
    assert mentions_chemical_product("Ask which fungicide is approved.")
    assert not mentions_chemical_product("Remove infected leaves.")


def test_certainty_and_support_helpers() -> None:
    assert overstates_certainty("The test confirms blight.")
    assert not overstates_certainty("We cannot confirm this from photos.")
    assert supported_by("Early blight causes ringed brown spots", S1_EXCERPT)
    assert not supported_by("Potassium deficiency yellows leaf edges", S1_EXCERPT)


def test_safe_excerpt_strips_markup_and_trims_at_a_sentence() -> None:
    text = "# Title\n**Early** [blight](https://x.y) spots. " + "More detail here. " * 60
    excerpt = safe_excerpt(text, limit=120)

    assert "https://" not in excerpt and "**" not in excerpt and "#" not in excerpt
    assert len(excerpt) <= 120 and excerpt.endswith(".")

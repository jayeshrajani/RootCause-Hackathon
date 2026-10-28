"""Live smoke test for the Nemotron (Nebius Token Factory) and Tavily integrations.

Makes real, billed API calls with the keys in .env / the environment. Never prints keys.

Usage (from apps/api, venv active):

    python scripts/smoke_live.py tavily     # one guidance search (about 2-3 Tavily credits)
    python scripts/smoke_live.py nebius     # catalog check + one Nemotron review, no sources
    python scripts/smoke_live.py all        # search, then a review grounded in the results

Exit code 0 means every requested check passed.
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime

from app.core.config import Settings
from app.integrations.nebius import NebiusClient, NebiusError
from app.main import build_investigation_runtime
from app.schemas.investigation import AgronomySource
from app.schemas.triage import (
    AnalysisMode,
    ConfidenceLevel,
    Crop,
    Evidence,
    EvidenceAvailability,
    MissingInformation,
    PossibleCause,
    SourceKind,
    TriageResponse,
    TriageStatus,
    UrgencyLevel,
)
from app.services.investigation.nemotron_review import ReviewInputs
from app.services.knowledge.agronomy import ResearchStatus


def sample_triage() -> TriageResponse:
    """A fixed tomato report shaped like real first-stage output (no photos, no location)."""
    return TriageResponse(
        report_id="rpt_5a3b1e0c9d2f4a61",
        status=TriageStatus.COMPLETED,
        analysis_mode=AnalysisMode.AI,
        crop=Crop.TOMATO,
        detected_crop="tomato",
        summary="Brown spots on the lower leaves may be early blight; late blight is less likely.",
        urgency=UrgencyLevel.MODERATE,
        urgency_reason="Spots are spreading upwards over a week.",
        possible_causes=[
            PossibleCause(
                name="Early blight",
                condition_key="early_blight",
                explanation="Brown spots with rings on older leaves fit early blight.",
                supporting_evidence=["Ringed brown spots on lower leaves"],
                contradictory_evidence=[],
                confidence=ConfidenceLevel.MEDIUM,
                uncertainty_note="Rings and yellow halos would make it more likely.",
                analysis_score=72,
                evidence_fit_score=75,
            ),
            PossibleCause(
                name="Late blight",
                condition_key="late_blight",
                explanation="Dark patches can be late blight in humid weather.",
                supporting_evidence=["Dark patches on two leaves"],
                contradictory_evidence=["No white growth reported"],
                confidence=ConfidenceLevel.LOW,
                uncertainty_note="White growth under leaves would point to late blight.",
                analysis_score=40,
                evidence_fit_score=38,
            ),
        ],
        evidence=[
            Evidence(
                id="ev_farmer_report",
                source=SourceKind.FARMER_REPORT,
                availability=EvidenceAvailability.AVAILABLE,
                observation="Farmer's description: \u201cBrown spots on lower leaves for a "
                "week.\u201d (Crop: tomato, duration: 3 to 7 days).",
            ),
            Evidence(
                id="ev_photo_1",
                source=SourceKind.PHOTO,
                availability=EvidenceAvailability.AVAILABLE,
                observation="Brown spots with faint rings on lower leaves",
            ),
            Evidence(
                id="ev_weather",
                source=SourceKind.WEATHER,
                availability=EvidenceAvailability.AVAILABLE,
                observation="Open-Meteo estimates: 7 days, 19-29 C, 5 humid days, 12 mm rain.",
            ),
            Evidence(
                id="ev_satellite",
                source=SourceKind.SATELLITE,
                availability=EvidenceAvailability.UNAVAILABLE,
                observation="Clouds hid the field in recent Sentinel-2 scenes.",
            ),
        ],
        missing_information=[
            MissingInformation(item="Leaf underside photo", reason="White growth = late blight.")
        ],
        recommended_actions=[],
        requires_expert_review=False,
        generated_at=datetime.now(UTC),
        data_sources=[],
        disclaimer="Smoke test sample.",
    )


def heading(text: str) -> None:
    print(f"\n== {text}")


async def run_tavily(settings: Settings) -> tuple[bool, tuple[AgronomySource, ...]]:
    heading("Tavily guidance search")
    if not settings.tavily_configured:
        print("TAVILY_API_KEY is not set (or ROOTCAUSE_TAVILY_ENABLED=false).")
        return False, ()
    research = build_investigation_runtime(settings).research
    result = await research.research(
        crop="tomato", condition_keys=["early_blight", "late_blight"], country="India"
    )
    print(f"status={result.status.value} credits={result.credits} ms={result.duration_ms}")
    for query in result.queries:
        print(f"query: {query}")
    if result.detail:
        print(f"detail: {result.detail}")
    for source in result.sources:
        print(f"[{source.id}] {source.publisher} ({source.region}) {source.published_at or ''}")
        print(f"     {source.url}")
        print(f"     {source.excerpt[:160]}…")
    ok = result.status in (ResearchStatus.AVAILABLE, ResearchStatus.NO_MATCHING_SOURCES)
    return ok, result.sources


async def run_nebius(settings: Settings, sources: tuple[AgronomySource, ...]) -> bool:
    heading("Nemotron on Nebius Token Factory")
    if settings.nebius_api_key is None or not settings.nebius_enabled:
        print("NEBIUS_API_KEY is not set (or ROOTCAUSE_NEBIUS_ENABLED=false).")
        return False
    client = NebiusClient(
        api_key=settings.nebius_api_key.get_secret_value(),
        model=settings.nebius_model,
        base_url=settings.nebius_base_url,
        timeout_seconds=settings.nebius_timeout_seconds,
    )
    try:
        models = await client.available_models()
        listed = settings.nebius_model in models
        nemotron = sorted(m for m in models if "nemotron" in m.lower())
        print(f"model {settings.nebius_model!r} in catalog: {listed}")
        print(f"Nemotron models available: {', '.join(nemotron) or 'none'}")
    except NebiusError as exc:
        print(f"catalog check failed ({exc.kind.value}): {exc}")

    reviewer = build_investigation_runtime(settings).reviewer
    assert reviewer is not None
    started = time.monotonic()
    try:
        review = await reviewer.review(
            ReviewInputs(triage=sample_triage(), sources=sources, region="India"),
            deadline=time.monotonic() + settings.investigation_timeout_seconds,
        )
    except NebiusError as exc:
        print(f"review FAILED ({exc.kind.value}): {exc}")
        return False
    print(
        f"status={review.status.value} model={review.model} grounding={review.grounding} "
        f"ms={round((time.monotonic() - started) * 1000)} "
        f"tokens={review.usage.prompt_tokens if review.usage else None}/"
        f"{review.usage.completion_tokens if review.usage else None}"
    )
    print(f"summary: {review.reasoning_summary}")
    print(
        f"observations={len(review.supporting_observations)} "
        f"contradictions={len(review.contradictions)} findings={len(review.knowledge_findings)} "
        f"steps={len(review.safe_next_steps)}"
    )
    if review.follow_up_question:
        print(f"follow-up: {review.follow_up_question.text}")
    for step in review.safe_next_steps:
        print(f"step [{step.support_status.value}] {step.action}")
    for note in review.guardrail_notes:
        print(f"guardrail: {note}")
    return True


async def main(target: str) -> int:
    settings = Settings()
    ok = True
    sources: tuple[AgronomySource, ...] = ()
    if target in ("tavily", "all"):
        tavily_ok, sources = await run_tavily(settings)
        ok &= tavily_ok
    if target in ("nebius", "all"):
        ok &= await run_nebius(settings, sources if target == "all" else ())
    heading("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("target", choices=["tavily", "nebius", "all"])
    sys.exit(asyncio.run(main(parser.parse_args().target)))

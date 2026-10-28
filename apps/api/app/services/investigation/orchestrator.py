"""Investigation workflow wrapped around the existing triage.

Order: existing triage (photos, weather, satellite, references, rule-based scores) -> guidance
search (Tavily) -> evidence review (Nemotron) -> deterministic guardrails -> optional review
translation. Scores, ranking, urgency and actions from the first stage are never changed; any
failure after the first stage returns the original triage with an explicit status.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.integrations.nebius import NebiusError, NebiusErrorKind
from app.models.report import FarmerReport
from app.models.weather import GeocodedLocation
from app.schemas.investigation import (
    AgronomySource,
    IntegrationStatus,
    IntegrationStep,
    IntegrationStepName,
    InvestigationReview,
    ReviewStatus,
    UsageInfo,
)
from app.schemas.satellite import SatelliteStatus
from app.schemas.triage import (
    AnalysisMode,
    DataSource,
    DataSourceStatus,
    Evidence,
    EvidenceAvailability,
    ResponseLanguage,
    SourceKind,
    TriageResponse,
    TriageStatus,
)
from app.services.investigation.nemotron_review import NemotronReviewer, ReviewInputs
from app.services.investigation.state import (
    InvestigationContext,
    InvestigationStore,
    InvestigationTracker,
)
from app.services.knowledge.agronomy import (
    AgronomyResearch,
    AgronomyResearchService,
    ResearchStatus,
)
from app.services.triage.ai import AI_DISCLAIMER
from app.services.triage.base import TriageService

logger = logging.getLogger(__name__)

REVIEW_PROVIDER = "Nebius Token Factory"
RESEARCH_PROVIDER = "Tavily"
_MIN_TRANSLATION_SECONDS = 3.0
_REGION_LOOKUP_SECONDS = 3.0

ReviewState = Literal["disabled", "not_configured", "misconfigured", "configured"]

INVESTIGATED_DISCLAIMER = (
    "AI-generated triage based on your photos, description and available report evidence. "
    "These are possibilities, not a diagnosis. Recent model-based weather estimates, satellite "
    "vegetation indices and agricultural guidance from approved publishers may have been "
    "checked; published guidance may not apply to your region, variety or crop stage. "
    "Confirm with a local agricultural expert before treating your crop."
)

REVIEW_ERROR_DETAILS = {
    NebiusErrorKind.AUTH: "The NVIDIA review service rejected this server's credentials.",
    NebiusErrorKind.RATE_LIMITED: "The NVIDIA review service is busy. Please try again later.",
    NebiusErrorKind.TIMEOUT: "The NVIDIA review took too long and was skipped.",
    NebiusErrorKind.UNAVAILABLE: "The NVIDIA review service is unavailable right now.",
    NebiusErrorKind.BAD_REQUEST: "The NVIDIA review request was rejected; the server "
    "configuration needs checking.",
    NebiusErrorKind.INVALID_OUTPUT: "The NVIDIA review returned an unusable answer, so it is "
    "not shown.",
}


class Geocoder(Protocol):
    async def geocode(self, location: str) -> GeocodedLocation | None: ...


class ReviewTranslator(Protocol):
    async def translate_review(
        self, review: InvestigationReview, language: ResponseLanguage
    ) -> InvestigationReview: ...


@dataclass(frozen=True, slots=True)
class InvestigationConfig:
    review_enabled: bool
    strict: bool
    model: str
    timeout_seconds: float = 55


@dataclass(slots=True)
class InvestigationRuntime:
    """Per-process collaborators shared by every request."""

    config: InvestigationConfig
    research: AgronomyResearchService
    reviewer: NemotronReviewer | None
    store: InvestigationStore
    tracker: InvestigationTracker

    @property
    def review_state(self) -> ReviewState:
        if not self.config.review_enabled:
            return "disabled"
        if self.reviewer is None:
            return "misconfigured" if self.config.strict else "not_configured"
        return "configured"


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _source(result: TriageResponse, source_id: str) -> DataSource | None:
    return next((s for s in result.data_sources if s.id == source_id), None)


def first_stage_steps(
    result: TriageResponse, duration_ms: int, image_provider: str, image_model: str | None
) -> list[IntegrationStep]:
    """Trace for the existing triage, derived from what it actually returned."""
    ai = result.analysis_mode == AnalysisMode.AI
    engine = _source(result, "src_ai_engine")
    if engine is not None and " via " in engine.name:
        image_model, _, image_provider = engine.name.partition(" via ")
    steps = [
        IntegrationStep(
            step=IntegrationStepName.IMAGE_ANALYSIS,
            provider=image_provider,
            model=image_model,
            status=IntegrationStatus.SUCCESS,
            duration_ms=duration_ms,
            detail="Whole first stage: photos, weather and satellite lookups run together.",
        )
        if ai
        else IntegrationStep(
            step=IntegrationStepName.IMAGE_ANALYSIS,
            provider="RootCause sample engine",
            status=IntegrationStatus.SKIPPED,
            detail="No model was called; this is a labelled sample result.",
        )
    ]

    weather = _source(result, "src_weather")
    if result.weather_facts is not None:
        steps.append(_step(IntegrationStepName.WEATHER, "Open-Meteo", IntegrationStatus.SUCCESS))
    else:
        not_used = weather is None or weather.status == DataSourceStatus.NOT_INTEGRATED
        steps.append(
            _step(
                IntegrationStepName.WEATHER,
                "Open-Meteo",
                IntegrationStatus.SKIPPED if not_used else IntegrationStatus.UNAVAILABLE,
                weather.description if weather else "Weather was not looked up.",
            )
        )

    sat = result.satellite
    if sat is None:
        source = _source(result, "src_satellite")
        steps.append(
            _step(
                IntegrationStepName.SATELLITE,
                "Google Earth Engine (Sentinel-2)",
                IntegrationStatus.NOT_CONFIGURED if ai else IntegrationStatus.SKIPPED,
                source.description if source else "Satellite evidence is not configured.",
            )
        )
    else:
        status = {
            SatelliteStatus.AVAILABLE: IntegrationStatus.SUCCESS,
            SatelliteStatus.NOT_REQUESTED: IntegrationStatus.NOT_REQUESTED,
            SatelliteStatus.NOT_CONFIGURED: IntegrationStatus.NOT_CONFIGURED,
            SatelliteStatus.INSUFFICIENT_DATA: IntegrationStatus.NO_RESULTS,
            SatelliteStatus.UNAVAILABLE: IntegrationStatus.UNAVAILABLE,
        }[sat.status]
        detail = sat.message
        if sat.status == SatelliteStatus.AVAILABLE and not sat.interpretable:
            detail = "Measured, but not reliable enough to change any score."
        steps.append(
            _step(IntegrationStepName.SATELLITE, "Google Earth Engine (Sentinel-2)", status, detail)
        )

    references = _source(result, "src_references")
    ref_status = (
        IntegrationStatus.DISABLED
        if references is None or references.status == DataSourceStatus.NOT_INTEGRATED
        else IntegrationStatus.SUCCESS
        if references.status == DataSourceStatus.USED
        else IntegrationStatus.UNAVAILABLE
    )
    steps.append(
        _step(
            IntegrationStepName.REFERENCE_PHOTOS,
            "DINOv2 + FAISS reference photos",
            ref_status,
            None
            if ref_status == IntegrationStatus.SUCCESS or references is None
            else references.description,
        )
    )

    scored = ai and bool(result.possible_causes)
    steps.append(
        _step(
            IntegrationStepName.DETERMINISTIC_SCORING,
            "RootCause evidence rules",
            IntegrationStatus.SUCCESS if scored else IntegrationStatus.SKIPPED,
            f"{len(result.possible_causes)} possible causes scored; weather can move a score by "
            "at most 10 points and satellite by 6."
            if scored
            else "Nothing to score.",
        )
    )
    return steps


def _step(
    name: IntegrationStepName,
    provider: str,
    status: IntegrationStatus,
    detail: str | None = None,
    *,
    model: str | None = None,
    duration_ms: int | None = None,
    usage: UsageInfo | None = None,
) -> IntegrationStep:
    return IntegrationStep(
        step=name,
        provider=provider,
        model=model,
        status=status,
        duration_ms=duration_ms,
        detail=detail,
        usage=usage,
    )


_RESEARCH_STEP_STATUS = {
    ResearchStatus.AVAILABLE: IntegrationStatus.SUCCESS,
    ResearchStatus.NO_MATCHING_SOURCES: IntegrationStatus.NO_RESULTS,
    ResearchStatus.UNAVAILABLE: IntegrationStatus.UNAVAILABLE,
    ResearchStatus.TIMEOUT: IntegrationStatus.TIMEOUT,
    ResearchStatus.DISABLED: IntegrationStatus.DISABLED,
    ResearchStatus.NOT_CONFIGURED: IntegrationStatus.NOT_CONFIGURED,
    ResearchStatus.SKIPPED: IntegrationStatus.SKIPPED,
}
# The search never ran, so existing "not integrated" evidence stays exactly as it was.
_SEARCH_NOT_RUN = (ResearchStatus.DISABLED, ResearchStatus.NOT_CONFIGURED, ResearchStatus.SKIPPED)


def research_step(research: AgronomyResearch) -> IntegrationStep:
    detail = research.detail
    if research.status == ResearchStatus.AVAILABLE:
        detail = f"{len(research.sources)} validated source(s) from approved publishers" + (
            " (cached)" if research.cached else ""
        )
    return _step(
        IntegrationStepName.AGRONOMY_RESEARCH,
        RESEARCH_PROVIDER,
        _RESEARCH_STEP_STATUS[research.status],
        detail,
        duration_ms=research.duration_ms,
        usage=UsageInfo(credits=research.credits) if research.credits is not None else None,
    )


def review_step(review: InvestigationReview, timed_out: bool = False) -> IntegrationStep:
    status = {
        ReviewStatus.COMPLETED: IntegrationStatus.SUCCESS,
        ReviewStatus.UNAVAILABLE: IntegrationStatus.TIMEOUT
        if timed_out
        else IntegrationStatus.FAILED,
        ReviewStatus.NOT_CONFIGURED: IntegrationStatus.NOT_CONFIGURED,
        ReviewStatus.DISABLED: IntegrationStatus.DISABLED,
        ReviewStatus.SKIPPED: IntegrationStatus.SKIPPED,
    }[review.status]
    detail = review.detail
    if review.status == ReviewStatus.COMPLETED:
        detail = (
            "Reviewed the evidence ledger and retrieved guidance"
            if review.grounding == "sources_and_evidence"
            else "Reviewed the evidence ledger only (no guidance sources)"
        ) + (f", round {review.round}" if review.round > 1 else "")
    return _step(
        IntegrationStepName.NEMOTRON_REVIEW,
        review.provider,
        status,
        detail,
        model=review.model,
        duration_ms=review.duration_ms,
        usage=review.usage,
    )


def _with_knowledge(
    evidence: list[Evidence], research: AgronomyResearch, now: datetime
) -> list[Evidence]:
    if research.status in _SEARCH_NOT_RUN:
        return evidence
    if research.status == ResearchStatus.AVAILABLE:
        publishers = ", ".join(dict.fromkeys(s.publisher for s in research.sources))
        item = Evidence(
            id="ev_knowledge",
            source=SourceKind.KNOWLEDGE_BASE,
            availability=EvidenceAvailability.AVAILABLE,
            observation=f"{len(research.sources)} guidance page(s) from approved agricultural "
            f"publishers were retrieved ({publishers}). Retrieval alone does not verify that "
            "the advice fits this field.",
            observed_at=now,
        )
    else:
        item = Evidence(
            id="ev_knowledge",
            source=SourceKind.KNOWLEDGE_BASE,
            availability=EvidenceAvailability.UNAVAILABLE,
            observation=(research.detail or "Agricultural guidance search was unavailable.")
            + " No sources are cited.",
        )
    replaced = [item if e.id == "ev_knowledge" else e for e in evidence]
    return replaced if any(e.id == "ev_knowledge" for e in evidence) else [*evidence, item]


def _with_sources(
    sources: list[DataSource],
    research: AgronomyResearch,
    review: InvestigationReview,
    now: datetime,
) -> list[DataSource]:
    updated = list(sources)
    if research.status not in _SEARCH_NOT_RUN:
        used = research.status == ResearchStatus.AVAILABLE
        knowledge = DataSource(
            id="src_knowledge",
            name="Agricultural guidance (Tavily search of approved publishers)",
            kind=SourceKind.KNOWLEDGE_BASE,
            status=DataSourceStatus.USED if used else DataSourceStatus.UNAVAILABLE,
            description="Search limited to an allowlist of research and extension sites; each "
            "page is re-checked for crop and condition relevance."
            if used
            else research.detail or "Guidance search was unavailable.",
            retrieved_at=now if used else None,
        )
        if any(s.id == "src_knowledge" for s in updated):
            updated = [knowledge if s.id == "src_knowledge" else s for s in updated]
        else:
            updated.append(knowledge)
    if review.status != ReviewStatus.SKIPPED:
        status = {
            ReviewStatus.COMPLETED: DataSourceStatus.USED,
            ReviewStatus.UNAVAILABLE: DataSourceStatus.UNAVAILABLE,
        }.get(review.status, DataSourceStatus.NOT_INTEGRATED)
        updated.append(
            DataSource(
                id="src_investigation_review",
                name=f"NVIDIA Nemotron ({review.model}) via {review.provider}",
                kind=SourceKind.INVESTIGATION_REVIEW,
                status=status,
                description="Cross-checks the evidence ledger and cited guidance; cannot change "
                "scores, ranking or urgency."
                if status == DataSourceStatus.USED
                else review.detail or "The evidence review did not run.",
                retrieved_at=review.generated_at,
            )
        )
    return updated


class InvestigatingTriageService:
    """TriageService decorator that adds the guidance search and Nemotron review."""

    def __init__(
        self,
        inner: TriageService,
        runtime: InvestigationRuntime,
        *,
        image_provider: str = "Cerebras",
        image_model: str | None = None,
        translator: ReviewTranslator | None = None,
        translator_label: tuple[str, str | None] = ("Cerebras", None),
        geocoder: Geocoder | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inner = inner
        self._runtime = runtime
        self._image_provider = image_provider
        self._image_model = image_model
        self._translator = translator
        self._translator_label = translator_label
        self._geocoder = geocoder
        self._clock = clock

    def _not_run(self, status: ReviewStatus, detail: str) -> InvestigationReview:
        return InvestigationReview(
            status=status,
            provider=REVIEW_PROVIDER,
            model=self._runtime.config.model,
            detail=detail,
        )

    async def assess(self, report: FarmerReport) -> TriageResponse:
        started = time.monotonic()
        base = await self._inner.assess(report)
        steps = first_stage_steps(base, _ms(started), self._image_provider, self._image_model)
        runtime = self._runtime

        skip_reason = None
        if base.analysis_mode != AnalysisMode.AI:
            skip_reason = "Sample result: the NVIDIA review only runs on real AI triage."
        elif base.status == TriageStatus.INSUFFICIENT_INFORMATION or not base.possible_causes:
            skip_reason = "There was not enough usable evidence to review."
        if skip_reason is not None:
            review = self._not_run(ReviewStatus.SKIPPED, skip_reason)
            research = AgronomyResearch(ResearchStatus.SKIPPED, detail=skip_reason)
            return self._finish(
                base, research, review, [*steps, research_step(research), review_step(review)]
            )

        deadline = time.monotonic() + runtime.config.timeout_seconds
        if runtime.reviewer is not None and not runtime.tracker.try_acquire():
            detail = "The daily review limit for this server was reached; try again tomorrow."
            review = self._not_run(ReviewStatus.UNAVAILABLE, detail)
            research = AgronomyResearch(ResearchStatus.SKIPPED, detail=detail)
            return self._finish(
                base, research, review, [*steps, research_step(research), review_step(review)]
            )

        region = await self._region(report)
        research = await self._research(base, region, deadline)
        steps.append(research_step(research))

        review_en, timed_out = await self._review(base, research.sources, region, deadline)
        steps.append(review_step(review_en, timed_out))
        review = review_en
        if (
            review_en.status == ReviewStatus.COMPLETED
            and base.response_language != ResponseLanguage.ENGLISH
        ):
            review, translation = await self._translate(review_en, base.response_language, deadline)
            steps.append(translation)

        result = self._finish(base, research, review, steps)
        if review_en.status == ReviewStatus.COMPLETED and review_en.follow_up_question:
            runtime.store.put(
                result.report_id,
                InvestigationContext(
                    response=result,
                    review_en=review_en,
                    sources=research.sources,
                    region=region,
                ),
            )
        return result

    def _finish(
        self,
        base: TriageResponse,
        research: AgronomyResearch,
        review: InvestigationReview,
        steps: list[IntegrationStep],
    ) -> TriageResponse:
        now = self._clock()
        disclaimer = (
            INVESTIGATED_DISCLAIMER
            if research.sources and base.disclaimer == AI_DISCLAIMER
            else base.disclaimer
        )
        return base.model_copy(
            update={
                "investigation_review": review,
                "agronomy_sources": list(research.sources),
                "integration_status": steps,
                "evidence": _with_knowledge(base.evidence, research, now),
                "data_sources": _with_sources(base.data_sources, research, review, now),
                "disclaimer": disclaimer,
            }
        )

    async def _region(self, report: FarmerReport) -> str | None:
        """Country name only (for search boosting and source applicability)."""
        if self._geocoder is None or not report.location_label:
            return None
        try:
            async with asyncio.timeout(_REGION_LOOKUP_SECONDS):
                place = await self._geocoder.geocode(report.location_label)
        except Exception:
            logger.info("Region lookup skipped")
            return None
        return place.country if place and place.country else None

    async def _research(
        self, base: TriageResponse, region: str | None, deadline: float
    ) -> AgronomyResearch:
        keys = [
            c.condition_key
            for c in base.possible_causes
            if c.condition_key and c.condition_key != "other"
        ]
        crop = base.crop.value if base.crop else None
        started = time.monotonic()
        try:
            async with asyncio.timeout(max(0.1, deadline - time.monotonic())):
                research = await self._runtime.research.research(
                    crop=crop, condition_keys=keys, country=region
                )
        except TimeoutError:
            return AgronomyResearch(
                ResearchStatus.TIMEOUT,
                detail="Guidance search ran out of time.",
                duration_ms=_ms(started),
            )
        except Exception:
            logger.exception("Guidance search failed unexpectedly")
            return AgronomyResearch(
                ResearchStatus.UNAVAILABLE,
                detail="Guidance search failed unexpectedly.",
                duration_ms=_ms(started),
            )
        if research.status == ResearchStatus.AVAILABLE and not research.cached:
            self._runtime.tracker.research_succeeded()
        return research

    async def _review(
        self,
        base: TriageResponse,
        sources: tuple[AgronomySource, ...],
        region: str | None,
        deadline: float,
    ) -> tuple[InvestigationReview, bool]:
        runtime = self._runtime
        if not runtime.config.review_enabled:
            return self._not_run(ReviewStatus.DISABLED, "The NVIDIA review is turned off."), False
        if runtime.reviewer is None:
            if runtime.config.strict:
                detail = (
                    "This deployment requires the NVIDIA Nemotron review, but it is not "
                    "configured. The triage above is unchanged."
                )
                return self._not_run(ReviewStatus.UNAVAILABLE, detail), False
            detail = "The NVIDIA review is not set up on this server."
            return self._not_run(ReviewStatus.NOT_CONFIGURED, detail), False
        started = time.monotonic()
        try:
            async with asyncio.timeout(max(0.1, deadline - time.monotonic())):
                review = await runtime.reviewer.review(
                    ReviewInputs(triage=base, sources=sources, region=region), deadline=deadline
                )
        except TimeoutError:
            runtime.tracker.review_failed(NebiusErrorKind.TIMEOUT.value)
            review = self._not_run(
                ReviewStatus.UNAVAILABLE, REVIEW_ERROR_DETAILS[NebiusErrorKind.TIMEOUT]
            )
            return review.model_copy(update={"duration_ms": _ms(started)}), True
        except NebiusError as exc:
            runtime.tracker.review_failed(exc.kind.value)
            logger.warning("Nemotron review unavailable: %s", exc.kind.value)
            review = self._not_run(ReviewStatus.UNAVAILABLE, REVIEW_ERROR_DETAILS[exc.kind])
            timed_out = exc.kind == NebiusErrorKind.TIMEOUT
            return review.model_copy(update={"duration_ms": _ms(started)}), timed_out
        runtime.tracker.review_succeeded()
        return review, False

    async def _translate(
        self, review: InvestigationReview, language: ResponseLanguage, deadline: float
    ) -> tuple[InvestigationReview, IntegrationStep]:
        provider, model = self._translator_label
        remaining = deadline - time.monotonic()
        if self._translator is None or remaining < _MIN_TRANSLATION_SECONDS:
            reason = (
                "No translation model is configured"
                if self._translator is None
                else "No time left to translate"
            )
            return review, _step(
                IntegrationStepName.TRANSLATION,
                provider,
                IntegrationStatus.SKIPPED,
                f"{reason}; the review is shown in English.",
                model=model,
            )
        started = time.monotonic()
        try:
            async with asyncio.timeout(remaining):
                translated = await self._translator.translate_review(review, language)
        except Exception:
            logger.warning("Review translation failed; showing English")
            return review, _step(
                IntegrationStepName.TRANSLATION,
                provider,
                IntegrationStatus.FAILED,
                "Translation failed; the review is shown in English.",
                model=model,
                duration_ms=_ms(started),
            )
        return translated, _step(
            IntegrationStepName.TRANSLATION,
            provider,
            IntegrationStatus.SUCCESS,
            f"Review translated to {language.value}.",
            model=model,
            duration_ms=_ms(started),
        )

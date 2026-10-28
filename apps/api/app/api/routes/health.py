from fastapi import APIRouter

from app import __version__
from app.api.deps import InvestigationRuntimeDep, ReferenceProviderDep, SettingsDep
from app.schemas.health import HealthResponse
from app.schemas.triage import AnalysisMode
from app.services.investigation.orchestrator import REVIEW_PROVIDER

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    settings: SettingsDep, references: ReferenceProviderDep, runtime: InvestigationRuntimeDep
) -> HealthResponse:
    tracker = runtime.tracker if runtime else None
    research = runtime.research if runtime else None
    return HealthResponse(
        status="ok",
        service="rootcause-api",
        version=__version__,
        analysis_mode=AnalysisMode.AI
        if settings.use_gemini or settings.use_cerebras
        else AnalysisMode.MOCK,
        model=(
            settings.gemini_model
            if settings.use_gemini
            else settings.cerebras_model
            if settings.use_cerebras
            else None
        ),
        reference_photos=references.status if references else "disabled",
        satellite_imagery="configured" if settings.satellite_configured else "disabled",
        investigation_review=runtime.review_state if runtime else "disabled",
        investigation_provider=REVIEW_PROVIDER if settings.nebius_enabled else None,
        investigation_model=settings.nebius_model if settings.nebius_enabled else None,
        investigation_strict=settings.hackathon_require_live_nebius,
        investigation_last_success_at=tracker.review_last_success_at if tracker else None,
        investigation_last_error=tracker.review_last_error if tracker else None,
        agronomy_search="disabled"
        if not settings.tavily_enabled
        else "configured"
        if research is not None and research.configured
        else "not_configured",
        agronomy_last_success_at=tracker.research_last_success_at if tracker else None,
    )

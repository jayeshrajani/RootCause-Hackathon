import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestSizeLimitMiddleware
from app.core.rate_limit import RateLimiter
from app.integrations.earth_engine import EarthEngineClient
from app.integrations.nebius import NebiusClient
from app.integrations.open_meteo import OpenMeteoClient
from app.integrations.tavily import TavilyClient
from app.services.investigation.nemotron_review import NemotronReviewer
from app.services.investigation.orchestrator import InvestigationConfig, InvestigationRuntime
from app.services.investigation.state import InvestigationStore, InvestigationTracker
from app.services.knowledge.agronomy import AgronomyResearchService
from app.services.knowledge.sources import approved_sources
from app.services.satellite import SatelliteService
from app.services.triage.references import RetrievalReferenceProvider
from app.services.weather import CachedWeatherClient

logger = logging.getLogger(__name__)


def build_satellite_service(settings: Settings) -> SatelliteService:
    source = (
        EarthEngineClient(
            project_id=settings.google_cloud_project_id or "",
            timeout_seconds=settings.satellite_timeout_seconds,
        )
        if settings.satellite_configured
        else None
    )
    return SatelliteService(
        source,
        window_days=settings.satellite_window_days,
        buffer_m=settings.satellite_buffer_m,
        timeout_seconds=settings.satellite_timeout_seconds,
        min_clear_coverage=settings.satellite_min_clear_coverage,
        stale_days=settings.satellite_stale_days,
        cache_ttl_seconds=settings.satellite_cache_ttl_seconds,
    )


def build_investigation_runtime(settings: Settings) -> InvestigationRuntime:
    tavily = (
        TavilyClient(
            api_key=settings.tavily_api_key.get_secret_value(),
            timeout_seconds=settings.tavily_timeout_seconds,
        )
        if settings.tavily_configured and settings.tavily_api_key is not None
        else None
    )
    reviewer = (
        NemotronReviewer(
            NebiusClient(
                api_key=settings.nebius_api_key.get_secret_value(),
                model=settings.nebius_model,
                base_url=settings.nebius_base_url,
                timeout_seconds=settings.nebius_timeout_seconds,
                max_retries=settings.nebius_max_retries,
                reasoning=settings.nebius_reasoning,
                structured_output=settings.nebius_structured_output,
                max_tokens=settings.nebius_max_tokens,
            )
        )
        if settings.nebius_configured and settings.nebius_api_key is not None
        else None
    )
    if settings.hackathon_require_live_nebius and reviewer is None:
        logger.error(
            "Strict mode is on but the Nemotron review is not configured (NEBIUS_API_KEY); "
            "every review will be reported as unavailable."
        )
    return InvestigationRuntime(
        config=InvestigationConfig(
            review_enabled=settings.nebius_enabled,
            strict=settings.hackathon_require_live_nebius,
            model=settings.nebius_model,
            timeout_seconds=settings.investigation_timeout_seconds,
        ),
        research=AgronomyResearchService(
            tavily,
            enabled=settings.tavily_enabled,
            sources=approved_sources(settings.tavily_allowed_domains),
            max_results=settings.tavily_max_results,
            timeout_seconds=settings.tavily_timeout_seconds,
            search_depth=settings.tavily_search_depth,
            extract_enabled=settings.tavily_extract_enabled,
            cache_ttl_seconds=settings.tavily_cache_ttl_seconds,
        ),
        reviewer=reviewer,
        store=InvestigationStore(
            ttl_seconds=settings.follow_up_ttl_seconds,
            max_entries=settings.follow_up_max_reports,
        ),
        tracker=InvestigationTracker(daily_limit=settings.investigation_daily_limit),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    references = RetrievalReferenceProvider(settings) if settings.retrieval_index_version else None
    # One instance per process so the satellite cache and EE initialisation are shared.
    satellite = build_satellite_service(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Loading takes ~30 s; triage runs without references until it is ready.
        if references is not None:
            references.start_loading()
        # Earth Engine initialisation takes several seconds; keep it off the first request.
        satellite.start_warmup()
        yield

    app = FastAPI(
        title="RootCause API",
        version=__version__,
        description="Crop distress triage and early-warning API.",
        lifespan=lifespan,
    )
    app.state.reference_provider = references
    app.state.satellite_service = satellite
    # Shared so crop identification can warm the weather cache for the following triage.
    app.state.weather_client = CachedWeatherClient(OpenMeteoClient())
    app.state.investigation = build_investigation_runtime(settings)
    app.state.rate_limiter = (
        RateLimiter(
            limit_per_hour=settings.rate_limit_per_hour,
            trusted_hops=settings.trusted_proxy_hops,
        )
        if settings.rate_limit_enabled
        else None
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    # Added last so it is outermost and error responses still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

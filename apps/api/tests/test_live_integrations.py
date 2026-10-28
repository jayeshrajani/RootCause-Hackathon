"""Opt-in live checks against the real Nebius and Tavily APIs (billed).

Run from apps/api with keys in .env:  ROOTCAUSE_RUN_LIVE_TESTS=1 pytest -m live
"""

import os
import time

import pytest

from app.core.config import Settings
from app.main import build_investigation_runtime
from app.services.investigation.nemotron_review import ReviewInputs
from app.services.knowledge.agronomy import ResearchStatus, safe_url
from app.services.knowledge.sources import APPROVED_SOURCES
from tests.investigation_helpers import base_triage

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(
        os.environ.get("ROOTCAUSE_RUN_LIVE_TESTS") != "1",
        reason="set ROOTCAUSE_RUN_LIVE_TESTS=1 to call the real Nebius and Tavily APIs",
    ),
]


@pytest.fixture
def live_settings() -> Settings:
    return Settings()


async def test_live_tavily_returns_only_validated_approved_sources(
    live_settings: Settings,
) -> None:
    if not live_settings.tavily_configured:
        pytest.skip("TAVILY_API_KEY is not set")
    research = build_investigation_runtime(live_settings).research

    result = await research.research(
        crop="tomato", condition_keys=["early_blight"], country="India"
    )

    assert result.status in (ResearchStatus.AVAILABLE, ResearchStatus.NO_MATCHING_SOURCES)
    for source in result.sources:
        assert safe_url(source.url, APPROVED_SOURCES) is not None
        assert source.crop_relevance and source.condition_relevance


async def test_live_nemotron_review_is_schema_valid(live_settings: Settings) -> None:
    reviewer = build_investigation_runtime(live_settings).reviewer
    if reviewer is None:
        pytest.skip("NEBIUS_API_KEY is not set")

    review = await reviewer.review(
        ReviewInputs(triage=base_triage()),
        deadline=time.monotonic() + live_settings.investigation_timeout_seconds,
    )

    assert review.status == "completed"
    assert "nemotron" in review.model.lower()
    assert review.grounding == "internal_evidence_only"
    assert review.reasoning_summary

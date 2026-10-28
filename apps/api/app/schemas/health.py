from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.triage import AnalysisMode


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    analysis_mode: AnalysisMode
    model: str | None = None
    reference_photos: Literal["disabled", "loading", "ready", "failed"] = "disabled"
    satellite_imagery: Literal["disabled", "configured"] = "disabled"
    investigation_review: Literal["disabled", "not_configured", "misconfigured", "configured"] = (
        "disabled"
    )
    investigation_provider: str | None = None
    investigation_model: str | None = None
    investigation_strict: bool = False
    investigation_last_success_at: datetime | None = None
    investigation_last_error: str | None = None
    agronomy_search: Literal["disabled", "not_configured", "configured"] = "disabled"
    agronomy_last_success_at: datetime | None = None

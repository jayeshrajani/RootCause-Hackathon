import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.api.deps import (
    ClientIpDep,
    InvestigationLimiterDep,
    SatelliteServiceDep,
    SettingsDep,
    WeatherClientDep,
    get_crop_identifier,
    get_follow_up_service,
    get_investigating_triage_service,
    get_triage_translator,
)
from app.core.errors import AppError
from app.core.rate_limit import enforce_rate_limit
from app.models.report import FarmerReport
from app.schemas.errors import ErrorDetail, ErrorResponse
from app.schemas.triage import (
    Crop,
    CropIdentification,
    FollowUpRequest,
    ResponseLanguage,
    SymptomDuration,
    TranslateTriageRequest,
    TriageResponse,
)
from app.services.image_validation import read_validated_images
from app.services.investigation.followup import FollowUpService
from app.services.satellite import coordinates_look_rounded
from app.services.triage import TriageService
from app.services.triage.identify import CropIdentifier
from app.services.triage.translate import TriageTranslator
from app.services.usage import SESSION_HEADER

logger = logging.getLogger(__name__)

router = APIRouter(tags=["triage"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "Upload too large"},
    415: {"model": ErrorResponse, "description": "Unsupported image type"},
    422: {"model": ErrorResponse, "description": "Invalid or missing fields"},
    429: {"model": ErrorResponse, "description": "Too many requests from this client"},
    502: {"model": ErrorResponse, "description": "Analysis provider unavailable"},
}

_TRIAGE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ERROR_RESPONSES,
    429: {"model": ErrorResponse, "description": "Investigation limit reached for this visit"},
}

_TRANSLATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "Result too long to translate"},
    422: {"model": ErrorResponse, "description": "Invalid result or language"},
    429: {"model": ErrorResponse, "description": "Too many requests from this client"},
    502: {"model": ErrorResponse, "description": "Translation provider unavailable"},
    503: {"model": ErrorResponse, "description": "Translation is not configured"},
}

_FOLLOW_UP_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Question already answered"},
    410: {"model": ErrorResponse, "description": "Result expired or held by another instance"},
    422: {"model": ErrorResponse, "description": "Unknown question or invalid answer"},
    429: {"model": ErrorResponse, "description": "Rate or daily review limit reached"},
    502: {"model": ErrorResponse, "description": "Review provider unavailable"},
    503: {"model": ErrorResponse, "description": "Review not configured"},
}


def _require_coordinate_pair(latitude: float | None, longitude: float | None) -> None:
    if (latitude is None) != (longitude is None):
        missing = "longitude" if longitude is None else "latitude"
        message = "Add both latitude and longitude, or leave both empty."
        raise AppError(
            422,
            "validation_error",
            "Some fields are missing or invalid.",
            [ErrorDetail(field=missing, message=message)],
        )


@router.post(
    "/triage/identify",
    responses=_ERROR_RESPONSES,
    dependencies=[Depends(enforce_rate_limit)],
)
async def identify_crop(
    settings: SettingsDep,
    identifier: Annotated[CropIdentifier, Depends(get_crop_identifier)],
    satellite: SatelliteServiceDep,
    weather: WeatherClientDep,
    images: Annotated[list[UploadFile] | None, File(description="1-3 JPEG/PNG/WebP photos")] = None,
    latitude: Annotated[float | None, Form(ge=-90, le=90, allow_inf_nan=False)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180, allow_inf_nan=False)] = None,
) -> CropIdentification:
    """Stage 1: identify the crop. Coordinates, if sent, warm weather and satellite caches."""
    _require_coordinate_pair(latitude, longitude)
    validated_images = await read_validated_images(
        images or [],
        max_images=settings.max_images,
        max_image_bytes=settings.max_image_bytes,
    )
    if latitude is not None and longitude is not None:
        weather.prefetch(latitude, longitude)
        if not coordinates_look_rounded(latitude, longitude):
            satellite.prefetch(latitude, longitude)
    return await identifier.identify(validated_images)


@router.post("/triage", responses=_TRIAGE_ERROR_RESPONSES)
async def create_triage(
    request: Request,
    settings: SettingsDep,
    limiter: InvestigationLimiterDep,
    ip: ClientIpDep,
    service: Annotated[TriageService, Depends(get_investigating_triage_service)],
    images: Annotated[list[UploadFile] | None, File(description="1-3 JPEG/PNG/WebP photos")] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
    crop: Annotated[Crop | None, Form()] = None,
    symptom_duration: Annotated[SymptomDuration | None, Form()] = None,
    latitude: Annotated[float | None, Form(ge=-90, le=90, allow_inf_nan=False)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180, allow_inf_nan=False)] = None,
    location_label: Annotated[str | None, Form(max_length=120)] = None,
    response_language: Annotated[ResponseLanguage, Form()] = ResponseLanguage.ENGLISH,
) -> TriageResponse:
    with limiter.reserve(session_id=request.headers.get(SESSION_HEADER), ip=ip):
        _require_coordinate_pair(latitude, longitude)
        validated_images = await read_validated_images(
            images or [],
            max_images=settings.max_images,
            max_image_bytes=settings.max_image_bytes,
        )
        report = FarmerReport(
            images=validated_images,
            received_at=datetime.now(UTC),
            crop=crop,
            description=(description or "").strip() or None,
            latitude=latitude,
            longitude=longitude,
            location_label=(location_label or "").strip() or None,
            symptom_duration=symptom_duration,
            response_language=response_language,
        )
        result = await service.assess(report)
    review = result.investigation_review
    logger.info(
        "Triage completed report_id=%s crop=%s images=%d mode=%s status=%s review=%s sources=%d",
        result.report_id,
        report.crop.value if report.crop else "unspecified",
        len(validated_images),
        result.analysis_mode.value,
        result.status.value,
        review.status.value if review else "none",
        len(result.agronomy_sources),
    )
    return result


@router.post(
    "/triage/translate",
    responses=_TRANSLATE_ERROR_RESPONSES,
    dependencies=[Depends(enforce_rate_limit)],
)
async def translate_triage(
    request: TranslateTriageRequest,
    translator: Annotated[TriageTranslator | None, Depends(get_triage_translator)],
) -> TriageResponse:
    if translator is None:
        raise AppError(
            503,
            "translation_unavailable",
            "Translation needs the AI analysis service, which isn't available right now.",
        )
    return await translator.translate(request.result, request.target_language)


@router.post(
    "/triage/follow-up",
    responses=_FOLLOW_UP_ERROR_RESPONSES,
    dependencies=[Depends(enforce_rate_limit)],
)
async def answer_follow_up(
    request: FollowUpRequest,
    service: Annotated[FollowUpService | None, Depends(get_follow_up_service)],
) -> TriageResponse:
    """Record the farmer's answer to the review's question and redo the review once."""
    if service is None:
        raise AppError(
            503, "review_unavailable", "Follow-up questions are not available on this server."
        )
    return await service.answer(request)

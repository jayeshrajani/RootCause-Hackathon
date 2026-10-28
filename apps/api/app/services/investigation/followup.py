"""One round of follow-up: the farmer answers Nemotron's question and the review is redone.

The answer is recorded as farmer-reported evidence. No existing scoring rule covers these
answers, so evidence-fit scores, ranking and urgency stay exactly as they were.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.errors import AppError
from app.integrations.nebius import NebiusError
from app.schemas.investigation import (
    FollowUpAnswer,
    FollowUpQuestion,
    IntegrationStepName,
    InvestigationReview,
)
from app.schemas.triage import (
    Evidence,
    EvidenceAvailability,
    FollowUpRequest,
    ResponseLanguage,
    SourceKind,
    TriageResponse,
)
from app.services.investigation.nemotron_review import ReviewInputs
from app.services.investigation.orchestrator import (
    InvestigationRuntime,
    ReviewTranslator,
    review_step,
)
from app.services.investigation.state import InvestigationContext

logger = logging.getLogger(__name__)

ANSWER_LABELS = {
    FollowUpAnswer.YES: "yes",
    FollowUpAnswer.NO: "no",
    FollowUpAnswer.NOT_SURE: "not sure",
}


class FollowUpService:
    def __init__(
        self,
        runtime: InvestigationRuntime,
        *,
        translator: ReviewTranslator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._runtime = runtime
        self._translator = translator
        self._clock = clock

    async def answer(self, request: FollowUpRequest) -> TriageResponse:
        context = self._runtime.store.get(request.report_id)
        if context is None:
            raise AppError(
                410,
                "follow_up_expired",
                "This result has expired. Start a new report to answer follow-up questions.",
            )
        question = context.review_en.follow_up_question
        if question is None or question.id != request.question_id:
            raise AppError(
                422,
                "invalid_follow_up_question",
                "That follow-up question does not belong to this result.",
            )
        if context.answered or context.in_progress:
            raise AppError(
                409, "follow_up_already_answered", "This follow-up question was already answered."
            )

        context.in_progress = True
        try:
            response = context.response
            evidence = Evidence(
                id="ev_follow_up_1",
                source=SourceKind.FARMER_REPORT,
                availability=EvidenceAvailability.AVAILABLE,
                observation="Farmer's answer to the follow-up question "
                f"\u201c{question.text}\u201d: {ANSWER_LABELS[request.answer]}.",
                observed_at=self._clock(),
            )
            with_answer = response.model_copy(update={"evidence": [*response.evidence, evidence]})
            answered = question.model_copy(update={"answer": request.answer})
            shown = response.investigation_review or context.review_en
            shown_question = (shown.follow_up_question or question).model_copy(
                update={"answer": request.answer}
            )

            if request.answer == FollowUpAnswer.NOT_SURE:
                review_en = context.review_en.model_copy(update={"follow_up_question": answered})
                display = shown.model_copy(update={"follow_up_question": shown_question})
                steps = response.integration_status
            else:
                review_en = await self._rereview(with_answer, context.review_en, answered, context)
                review_en = review_en.model_copy(update={"follow_up_question": answered})
                display = await self._display(review_en, response.response_language)
                display = display.model_copy(update={"follow_up_question": shown_question})
                steps = [
                    review_step(review_en) if s.step == IntegrationStepName.NEMOTRON_REVIEW else s
                    for s in response.integration_status
                    if s.step != IntegrationStepName.TRANSLATION
                ]

            updated = with_answer.model_copy(
                update={"investigation_review": display, "integration_status": steps}
            )
            context.response = updated
            context.review_en = review_en
            context.answered = True
            logger.info(
                "Follow-up answered report_id=%s answer=%s",
                request.report_id,
                request.answer.value,
            )
            return updated
        finally:
            context.in_progress = False

    async def _rereview(
        self,
        triage: TriageResponse,
        previous: InvestigationReview,
        question_answered: FollowUpQuestion,
        context: InvestigationContext,
    ) -> InvestigationReview:
        runtime = self._runtime
        reviewer = runtime.follow_up_reviewer or runtime.reviewer
        if reviewer is None:
            raise AppError(
                503, "review_unavailable", "The NVIDIA review is not available on this server."
            )
        if not runtime.tracker.try_acquire():
            raise AppError(
                429,
                "review_limit_reached",
                "The daily review limit for this server was reached; try again tomorrow.",
            )
        deadline = time.monotonic() + runtime.config.timeout_seconds
        assert question_answered.answer is not None
        try:
            async with asyncio.timeout(runtime.config.timeout_seconds):
                review = await reviewer.review(
                    ReviewInputs(
                        triage=triage,
                        sources=context.sources,
                        region=context.region,
                        previous=previous,
                        follow_up=(question_answered, question_answered.answer),
                    ),
                    deadline=deadline,
                )
        except (NebiusError, TimeoutError) as exc:
            kind = exc.kind.value if isinstance(exc, NebiusError) else "timeout"
            runtime.tracker.review_failed(kind)
            raise AppError(
                502,
                "review_unavailable",
                "The NVIDIA review could not be updated right now. Please try again.",
            ) from exc
        runtime.tracker.review_succeeded()
        return review

    async def _display(
        self, review: InvestigationReview, language: ResponseLanguage
    ) -> InvestigationReview:
        if language == ResponseLanguage.ENGLISH or self._translator is None:
            return review
        try:
            async with asyncio.timeout(20):
                return await self._translator.translate_review(review, language)
        except Exception:
            logger.warning("Follow-up review translation failed; showing English")
            return review

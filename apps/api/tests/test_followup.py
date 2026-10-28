import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_triage_service
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas.investigation import FollowUpAnswer
from app.schemas.triage import FollowUpRequest
from app.services.investigation.followup import FollowUpService
from app.services.investigation.orchestrator import InvestigatingTriageService
from tests.conftest import jpeg
from tests.investigation_helpers import (
    REPORT,
    FakeSearcher,
    StubTriage,
    base_triage,
    nebius_client,
    nebius_completion,
    review_output,
    tavily_result,
)
from tests.test_investigation import TNAU, runtime

pytestmark = pytest.mark.anyio

QUESTION_ID = "fq_000000000001"
SECOND_ROUND = review_output(
    reasoning_summary="Target-like rings make early blight more likely than late blight.",
    follow_up_questions=[],
    what_changed=["The farmer saw target-like rings, which fits early blight."],
)


async def investigated(*responses: httpx.Response, sent: list[dict[str, Any]] | None = None) -> Any:
    client = nebius_client(nebius_completion(json.dumps(review_output())), *responses, sent=sent)
    rt = runtime(client, FakeSearcher([tavily_result(TNAU)]))
    result = await InvestigatingTriageService(StubTriage(base_triage()), rt).assess(REPORT)
    return rt, result


def request(answer: FollowUpAnswer, question_id: str = QUESTION_ID) -> FollowUpRequest:
    return FollowUpRequest(report_id="rpt_0123456789abcdef", question_id=question_id, answer=answer)


async def test_yes_answer_redoes_the_review_and_keeps_scores() -> None:
    sent: list[dict[str, Any]] = []
    rt, first = await investigated(nebius_completion(json.dumps(SECOND_ROUND)), sent=sent)

    updated = await FollowUpService(rt).answer(request(FollowUpAnswer.YES))

    review = updated.investigation_review
    assert review is not None and review.round == 2
    assert review.what_changed == ["The farmer saw target-like rings, which fits early blight."]
    assert review.previous_summary == first.investigation_review.reasoning_summary
    assert review.follow_up_question is not None
    assert review.follow_up_question.answer == "yes"
    assert updated.possible_causes == first.possible_causes
    assert updated.urgency == first.urgency
    assert updated.recommended_actions == first.recommended_actions
    answer = updated.evidence[-1]
    assert answer.id == "ev_follow_up_1" and answer.source == "farmer_report"
    assert "Do the spots have rings like a target?" in answer.observation
    second_prompt = sent[1]["body"]["messages"][1]["content"]
    assert '"farmer_follow_up_answer": {"question"' in second_prompt
    assert '"previous_review": {' in second_prompt


async def test_not_sure_records_the_answer_without_a_model_call() -> None:
    sent: list[dict[str, Any]] = []
    rt, first = await investigated(sent=sent)

    updated = await FollowUpService(rt).answer(request(FollowUpAnswer.NOT_SURE))

    assert len(sent) == 1
    review = updated.investigation_review
    assert review is not None and review.round == 1
    assert review.follow_up_question is not None
    assert review.follow_up_question.answer == "not_sure"
    assert updated.possible_causes == first.possible_causes


async def test_repeat_and_foreign_questions_are_rejected() -> None:
    rt, _ = await investigated()
    service = FollowUpService(rt)

    with pytest.raises(AppError) as wrong:
        await service.answer(request(FollowUpAnswer.NO, question_id="fq_ffffffffffff"))
    assert wrong.value.status_code == 422

    await service.answer(request(FollowUpAnswer.NOT_SURE))
    with pytest.raises(AppError) as repeat:
        await service.answer(request(FollowUpAnswer.NO))
    assert repeat.value.status_code == 409


async def test_expired_context_is_reported() -> None:
    rt = runtime(nebius_client())

    with pytest.raises(AppError) as exc:
        await FollowUpService(rt).answer(request(FollowUpAnswer.YES))

    assert exc.value.status_code == 410
    assert exc.value.code == "follow_up_expired"


async def test_failed_re_review_can_be_retried() -> None:
    rt, _ = await investigated(httpx.Response(500), httpx.Response(500))
    service = FollowUpService(rt)

    with pytest.raises(AppError) as exc:
        await service.answer(request(FollowUpAnswer.NO))
    assert exc.value.status_code == 502

    context = rt.store.get("rpt_0123456789abcdef")
    assert context is not None and not context.answered and not context.in_progress


def test_follow_up_route_validates_input_and_answers() -> None:
    settings = Settings(analysis_provider="mock", _env_file=None)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_triage_service] = lambda: StubTriage(base_triage())
    client = nebius_client(
        nebius_completion(json.dumps(review_output())),
        nebius_completion(json.dumps(SECOND_ROUND)),
    )
    app.state.investigation = runtime(client, FakeSearcher([tavily_result(TNAU)]))

    with TestClient(app) as http:
        first = http.post("/api/v1/triage", files=[jpeg()]).json()
        question = first["investigation_review"]["follow_up_question"]
        bad = http.post(
            "/api/v1/triage/follow-up",
            json={
                "report_id": first["report_id"],
                "question_id": question["id"],
                "answer": "maybe",
            },
        )
        ok = http.post(
            "/api/v1/triage/follow-up",
            json={"report_id": first["report_id"], "question_id": question["id"], "answer": "no"},
        )
        again = http.post(
            "/api/v1/triage/follow-up",
            json={"report_id": first["report_id"], "question_id": question["id"], "answer": "no"},
        )

    assert bad.status_code == 422
    assert ok.status_code == 200, ok.text
    assert ok.json()["investigation_review"]["round"] == 2
    assert again.status_code == 409


def test_follow_up_route_rejects_malformed_ids() -> None:
    app = create_app(Settings(analysis_provider="mock", _env_file=None))

    with TestClient(app) as http:
        response = http.post(
            "/api/v1/triage/follow-up",
            json={"report_id": "../../etc", "question_id": "x", "answer": "yes"},
        )

    assert response.status_code == 422

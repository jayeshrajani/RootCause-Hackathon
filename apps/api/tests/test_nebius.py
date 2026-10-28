import json
import time
from typing import Any

import httpx
import pytest

from app.integrations.nebius import NebiusError, NebiusErrorKind, extract_json_text
from tests.investigation_helpers import nebius_client, nebius_completion

pytestmark = pytest.mark.anyio

SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}


async def call(client: Any, deadline: float | None = None) -> Any:
    return await client.structured_completion(
        system="sys", user="user", schema_name="review", schema=SCHEMA, deadline=deadline
    )


async def test_success_sends_schema_reasoning_switch_and_bearer_key() -> None:
    sent: list[dict[str, Any]] = []
    client = nebius_client(nebius_completion('{"ok": true}'), sent=sent)

    result = await call(client)

    assert json.loads(result.content) == {"ok": True}
    assert result.model == "nvidia/nemotron-test"
    assert (result.prompt_tokens, result.completion_tokens, result.attempts) == (1200, 400, 1)
    body = sent[0]["body"]
    assert body["model"] == "nvidia/nemotron-test"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": True, "low_effort": True}
    assert sent[0]["headers"]["authorization"] == "Bearer nebius-secret-key"


async def test_default_reasoning_and_json_object_mode_send_no_extras() -> None:
    sent: list[dict[str, Any]] = []
    client = nebius_client(
        nebius_completion("{}"), sent=sent, reasoning="default", structured_output="json_object"
    )

    await call(client)

    assert "chat_template_kwargs" not in sent[0]["body"]
    assert sent[0]["body"]["response_format"] == {"type": "json_object"}


def test_reasoning_blocks_and_fences_are_removed() -> None:
    assert extract_json_text('<think>weigh options {x}</think>\n{"a": 1}') == '{"a": 1}'
    assert extract_json_text('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json_text('stray reasoning </think> {"a": 1}') == '{"a": 1}'


async def test_auth_failure_is_distinct_and_never_retried_or_leaks_key() -> None:
    client = nebius_client(httpx.Response(401, json={"detail": "bad key"}))

    with pytest.raises(NebiusError) as exc:
        await call(client)

    assert exc.value.kind == NebiusErrorKind.AUTH
    assert "nebius-secret-key" not in str(exc.value)


async def test_rate_limit_is_retried_once_then_succeeds() -> None:
    client = nebius_client(
        httpx.Response(429, headers={"retry-after": "1"}), nebius_completion("{}")
    )

    result = await call(client)

    assert result.attempts == 2


async def test_retry_exhaustion_reports_the_last_kind() -> None:
    client = nebius_client(httpx.Response(503), httpx.Response(502))

    with pytest.raises(NebiusError) as exc:
        await call(client)

    assert exc.value.kind == NebiusErrorKind.UNAVAILABLE


async def test_long_retry_after_is_not_waited_for() -> None:
    client = nebius_client(httpx.Response(429, headers={"retry-after": "60"}))

    with pytest.raises(NebiusError) as exc:
        await call(client)

    assert exc.value.kind == NebiusErrorKind.RATE_LIMITED


async def test_timeout_is_not_retried() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = nebius_client(slow)

    with pytest.raises(NebiusError) as exc:
        await call(client)

    assert exc.value.kind == NebiusErrorKind.TIMEOUT


async def test_spent_deadline_fails_without_a_request() -> None:
    sent: list[dict[str, Any]] = []
    client = nebius_client(sent=sent)

    with pytest.raises(NebiusError) as exc:
        await call(client, deadline=time.monotonic() - 1)

    assert exc.value.kind == NebiusErrorKind.TIMEOUT
    assert sent == []


async def test_retry_is_skipped_when_the_deadline_is_near() -> None:
    client = nebius_client(httpx.Response(503), nebius_completion("{}"))

    with pytest.raises(NebiusError):
        await call(client, deadline=time.monotonic() + 2)


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (httpx.Response(400, json={"error": "bad schema"}), NebiusErrorKind.BAD_REQUEST),
        (httpx.Response(404), NebiusErrorKind.BAD_REQUEST),
        (nebius_completion(""), NebiusErrorKind.INVALID_OUTPUT),
        (httpx.Response(200, json={"choices": []}), NebiusErrorKind.INVALID_OUTPUT),
        (httpx.Response(200, text="not json"), NebiusErrorKind.INVALID_OUTPUT),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": "", "refusal": "no"}}]}),
            NebiusErrorKind.INVALID_OUTPUT,
        ),
    ],
)
async def test_unusable_responses_are_classified(
    response: httpx.Response, kind: NebiusErrorKind
) -> None:
    client = nebius_client(response)

    with pytest.raises(NebiusError) as exc:
        await call(client)

    assert exc.value.kind == kind


async def test_available_models_lists_catalog_ids() -> None:
    client = nebius_client(
        httpx.Response(200, json={"data": [{"id": "nvidia/nemotron-test"}, {"id": "other"}]})
    )

    assert await client.available_models() == ["nvidia/nemotron-test", "other"]

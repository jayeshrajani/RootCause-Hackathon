"""NVIDIA Nemotron on Nebius Token Factory (OpenAI-compatible chat completions, text only).

Errors are classified so callers can tell a bad key from a rate limit, an outage or unusable
output. Prompts, completions and the API key are never logged.
"""

import asyncio
import logging
import re
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

import httpx
import truststore

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Nebius Token Factory"

ReasoningMode = Literal["default", "off", "low", "on"]
StructuredOutput = Literal["json_schema", "json_object"]

_REASONING_KWARGS: dict[str, dict[str, bool]] = {
    "off": {"enable_thinking": False},
    "low": {"enable_thinking": True, "low_effort": True},
    "on": {"enable_thinking": True},
}
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MIN_RETRY_SECONDS = 5.0
_MAX_RETRY_AFTER_SECONDS = 3.0


class NebiusErrorKind(StrEnum):
    AUTH = "auth_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "provider_unavailable"
    BAD_REQUEST = "bad_request"
    INVALID_OUTPUT = "invalid_output"


class NebiusError(Exception):
    """Inference failed. The message is safe to log and show in diagnostics."""

    def __init__(
        self, kind: NebiusErrorKind, message: str, *, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class NebiusCompletion:
    content: str = ""
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
    attempts: int = 1


def extract_json_text(content: str) -> str:
    """The JSON object in a completion, without reasoning blocks or code fences."""
    text = _THINK_BLOCK.sub("", content)
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    text = text.strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class FallbackNebiusClient:
    """One Nemotron model, then another when the first fails for any reason but a bad key."""

    def __init__(
        self, primary: "NebiusClient", fallback: "NebiusClient", *, min_seconds: float = 10.0
    ) -> None:
        self.model = primary.model
        self.provider = primary.provider
        self._primary = primary
        self._fallback = fallback
        self._min_seconds = min_seconds

    async def structured_completion(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        deadline: float | None = None,
    ) -> NebiusCompletion:
        try:
            return await self._primary.structured_completion(
                system=system, user=user, schema_name=schema_name, schema=schema, deadline=deadline
            )
        except NebiusError as exc:
            left = None if deadline is None else deadline - time.monotonic()
            if exc.kind == NebiusErrorKind.AUTH or (left is not None and left < self._min_seconds):
                raise
            logger.warning(
                "Nemotron model %s failed (%s); trying %s",
                self._primary.model,
                exc.kind.value,
                self._fallback.model,
            )
            return await self._fallback.structured_completion(
                system=system, user=user, schema_name=schema_name, schema=schema, deadline=deadline
            )


class NebiusClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 30,
        max_retries: int = 1,
        reasoning: ReasoningMode = "low",
        structured_output: StructuredOutput = "json_schema",
        max_tokens: int = 6000,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.model = model
        self.provider = PROVIDER_NAME
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._reasoning = reasoning
        self._structured_output = structured_output
        self._max_tokens = max_tokens
        self._transport = transport
        self._sleep = sleep

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            transport=self._transport,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )

    def _body(self, system: str, user: str, schema_name: str, schema: dict[str, Any]) -> Any:
        response_format: dict[str, Any] = (
            {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
            if self._structured_output == "json_schema"
            else {"type": "json_object"}
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": response_format,
            "max_tokens": self._max_tokens,
            # NVIDIA suggests 1.0; a lower value keeps evidence reviews steadier.
            "temperature": 0.6,
            "top_p": 0.95,
        }
        if self._reasoning in _REASONING_KWARGS:
            body["chat_template_kwargs"] = _REASONING_KWARGS[self._reasoning]
        return body

    async def structured_completion(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        deadline: float | None = None,
    ) -> NebiusCompletion:
        """JSON text under `schema`. Retries only transient failures while time remains."""
        body = self._body(system, user, schema_name, schema)
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise NebiusError(NebiusErrorKind.TIMEOUT, "No time left for the review")
            timeout = self._timeout if remaining is None else min(self._timeout, remaining)
            try:
                result = await self._once(body, request_seconds=timeout)
            except NebiusError as exc:
                retryable = exc.kind in (NebiusErrorKind.UNAVAILABLE, NebiusErrorKind.RATE_LIMITED)
                wait = min(exc.retry_after or 1.0, _MAX_RETRY_AFTER_SECONDS)
                left = None if deadline is None else deadline - time.monotonic() - wait
                if (
                    not retryable
                    or attempt > self._max_retries
                    or (exc.retry_after or 0) > _MAX_RETRY_AFTER_SECONDS
                    or (left is not None and left < _MIN_RETRY_SECONDS)
                ):
                    logger.warning(
                        "Nebius completion failed model=%s kind=%s attempts=%d: %s",
                        self.model,
                        exc.kind.value,
                        attempt,
                        exc,
                    )
                    raise
                await self._sleep(wait)
                continue
            latency_ms = round((time.monotonic() - started) * 1000)
            logger.info(
                "Nebius completion model=%s prompt_tokens=%s completion_tokens=%s "
                "attempts=%d elapsed_ms=%d",
                result.model,
                result.prompt_tokens,
                result.completion_tokens,
                attempt,
                latency_ms,
            )
            return NebiusCompletion(
                content=result.content,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=latency_ms,
                attempts=attempt,
            )

    async def _once(self, body: Any, *, request_seconds: float) -> NebiusCompletion:
        try:
            async with self._client(request_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise NebiusError(NebiusErrorKind.TIMEOUT, "Nemotron request timed out") from exc
        except httpx.HTTPError as exc:
            raise NebiusError(
                NebiusErrorKind.UNAVAILABLE, f"Nemotron request failed: {type(exc).__name__}"
            ) from exc

        code = response.status_code
        if code in (401, 403):
            raise NebiusError(NebiusErrorKind.AUTH, f"Nebius rejected the API key (HTTP {code})")
        if code == 429:
            raise NebiusError(
                NebiusErrorKind.RATE_LIMITED,
                "Nebius rate limit reached (HTTP 429)",
                retry_after=_retry_after(response),
            )
        if code in (400, 404, 413, 422):
            raise NebiusError(
                NebiusErrorKind.BAD_REQUEST,
                f"Nebius rejected the request (HTTP {code}); check the model id and options",
            )
        if code >= 500:
            raise NebiusError(NebiusErrorKind.UNAVAILABLE, f"Nebius returned HTTP {code}")
        if code != 200:
            raise NebiusError(NebiusErrorKind.UNAVAILABLE, f"Nebius returned HTTP {code}")

        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise NebiusError(
                NebiusErrorKind.INVALID_OUTPUT, "Nebius returned an unexpected payload"
            ) from exc
        if message.get("refusal"):
            raise NebiusError(NebiusErrorKind.INVALID_OUTPUT, "Nemotron refused the request")
        text = extract_json_text(str(content))
        if not text:
            truncated = choice.get("finish_reason") == "length"
            raise NebiusError(
                NebiusErrorKind.INVALID_OUTPUT,
                "Nemotron output was truncated" if truncated else "Nemotron output was empty",
            )
        usage = payload.get("usage") or {}
        return NebiusCompletion(
            content=text,
            model=str(payload.get("model") or self.model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    async def available_models(self) -> list[str]:
        """Model ids in the account's catalog (used by the smoke test, not by requests)."""
        try:
            async with self._client(self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            raise NebiusError(
                NebiusErrorKind.UNAVAILABLE, f"Model list failed: {type(exc).__name__}"
            ) from exc
        if response.status_code in (401, 403):
            raise NebiusError(NebiusErrorKind.AUTH, "Nebius rejected the API key")
        if response.status_code != 200:
            raise NebiusError(
                NebiusErrorKind.UNAVAILABLE, f"Model list returned HTTP {response.status_code}"
            )
        try:
            return [str(item["id"]) for item in response.json()["data"]]
        except (ValueError, KeyError, TypeError) as exc:
            raise NebiusError(NebiusErrorKind.INVALID_OUTPUT, "Unexpected model list") from exc

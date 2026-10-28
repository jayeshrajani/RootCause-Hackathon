"""Tavily Search and Extract, called server-side only. Results are untrusted until validated."""

import logging
import ssl
import time
from enum import StrEnum
from typing import Any

import httpx
import truststore
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Tavily"
BASE_URL = "https://api.tavily.com"


class TavilyErrorKind(StrEnum):
    AUTH = "auth_failed"
    RATE_LIMITED = "rate_limited"
    QUOTA = "quota_exceeded"
    BAD_REQUEST = "bad_request"
    TIMEOUT = "timeout"
    UNAVAILABLE = "provider_unavailable"
    MALFORMED = "malformed_response"


class TavilyError(Exception):
    """A Tavily call failed. The message is safe to log."""

    def __init__(self, kind: TavilyErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class TavilyUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    credits: float | None = None


class TavilyResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    title: str = ""
    content: str = ""
    score: float | None = None
    published_date: str | None = None


class TavilySearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    results: list[TavilyResult] = Field(default_factory=list)
    usage: TavilyUsage | None = None


class TavilyExtractResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    raw_content: str = ""


class TavilyExtractResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    results: list[TavilyExtractResult] = Field(default_factory=list)
    failed_results: list[dict[str, Any]] = Field(default_factory=list)
    usage: TavilyUsage | None = None


class TavilyClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 12,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def search(
        self,
        *,
        query: str,
        include_domains: list[str],
        max_results: int,
        search_depth: str = "basic",
        country: str | None = None,
        timeout_seconds: float | None = None,
    ) -> TavilySearchResponse:
        body: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "topic": "general",
            "max_results": max_results,
            "chunks_per_source": 3,
            "include_domains": include_domains,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_published_date": True,
            "include_usage": True,
        }
        if country:
            body["country"] = country
        data = await self._post("/search", body, timeout_seconds)
        try:
            return TavilySearchResponse.model_validate(data)
        except ValidationError as exc:
            raise TavilyError(
                TavilyErrorKind.MALFORMED, "Unexpected Tavily search payload"
            ) from exc

    async def extract(
        self, *, urls: list[str], query: str, timeout_seconds: float | None = None
    ) -> TavilyExtractResponse:
        timeout = timeout_seconds or self._timeout
        body: dict[str, Any] = {
            "urls": urls,
            "query": query,
            "chunks_per_source": 3,
            "extract_depth": "basic",
            "format": "text",
            "include_images": False,
            "include_usage": True,
            "timeout": max(1.0, min(timeout - 0.5, 60.0)),
        }
        data = await self._post("/extract", body, timeout)
        try:
            return TavilyExtractResponse.model_validate(data)
        except ValidationError as exc:
            raise TavilyError(
                TavilyErrorKind.MALFORMED, "Unexpected Tavily extract payload"
            ) from exc

    async def _post(self, path: str, body: dict[str, Any], request_seconds: float | None) -> Any:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=request_seconds or self._timeout,
                transport=self._transport,
                verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            ) as client:
                response = await client.post(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise TavilyError(TavilyErrorKind.TIMEOUT, f"Tavily {path} timed out") from exc
        except httpx.HTTPError as exc:
            raise TavilyError(
                TavilyErrorKind.UNAVAILABLE, f"Tavily {path} failed: {type(exc).__name__}"
            ) from exc

        code = response.status_code
        if code == 401:
            raise TavilyError(TavilyErrorKind.AUTH, "Tavily rejected the API key (HTTP 401)")
        if code == 429:
            raise TavilyError(TavilyErrorKind.RATE_LIMITED, "Tavily rate limit reached (HTTP 429)")
        if code in (432, 433):
            raise TavilyError(TavilyErrorKind.QUOTA, f"Tavily plan limit reached (HTTP {code})")
        if code in (400, 422):
            raise TavilyError(TavilyErrorKind.BAD_REQUEST, f"Tavily rejected {path} (HTTP {code})")
        if code != 200:
            raise TavilyError(TavilyErrorKind.UNAVAILABLE, f"Tavily {path} returned HTTP {code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise TavilyError(
                TavilyErrorKind.MALFORMED, f"Tavily {path} returned non-JSON"
            ) from exc
        logger.info("Tavily %s ok elapsed_ms=%d", path, round((time.monotonic() - started) * 1000))
        return data

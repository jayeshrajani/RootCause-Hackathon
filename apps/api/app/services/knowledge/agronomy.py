"""Agricultural guidance retrieval: Tavily search restricted to approved publishers.

Tavily finds documents; it is not treated as an authority. Every result is re-validated here
(HTTPS, approved domain, crop and condition relevance, pertinent text) before it can reach the
reviewer or the farmer. Queries are built only from the crop, condition keys and country name:
never from farmer text or coordinates.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

from app.integrations.tavily import (
    TavilyError,
    TavilyErrorKind,
    TavilyExtractResponse,
    TavilyResult,
    TavilySearchResponse,
)
from app.schemas.investigation import AgronomySource
from app.services.knowledge.safety import looks_like_instructions, safe_excerpt
from app.services.knowledge.sources import (
    CONDITION_TERMS,
    CROP_TERMS,
    TAVILY_COUNTRIES,
    ApprovedSource,
    match_approved,
    mentions_any,
)

logger = logging.getLogger(__name__)

MAX_CONDITIONS = 2
MIN_EXCERPT_CHARS = 80
_MAX_CACHE_ENTRIES = 256
_MIN_EXTRACT_SECONDS = 4.0
_EXTRACT_URLS = 2

_GUIDANCE_WORDS = (
    "symptom", "sign", "lesion", "spot", "manage", "management", "control", "prevent",
    "prevention", "remove", "rotation", "rotate", "resistant", "variet", "sanitation",
    "irrigat", "drain", "spread", "favour", "favor", "humid", "moist", "infect", "monitor",
    "scout", "cultural", "practice", "condition", "cause", "damage", "yellow", "wilt",
)  # fmt: skip


class ResearchStatus(StrEnum):
    AVAILABLE = "available"
    NO_MATCHING_SOURCES = "no_matching_sources"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class AgronomyResearch:
    status: ResearchStatus
    sources: tuple[AgronomySource, ...] = ()
    detail: str | None = None
    duration_ms: int | None = None
    credits: float | None = None
    queries: tuple[str, ...] = field(default=())
    cached: bool = False


class GuidanceSearcher(Protocol):
    async def search(
        self,
        *,
        query: str,
        include_domains: list[str],
        max_results: int,
        search_depth: str = "basic",
        country: str | None = None,
        timeout_seconds: float | None = None,
    ) -> TavilySearchResponse: ...

    async def extract(
        self, *, urls: list[str], query: str, timeout_seconds: float | None = None
    ) -> TavilyExtractResponse: ...


def build_query(crop: str, condition_key: str) -> str | None:
    crop_vocab = CROP_TERMS.get(crop)
    condition = CONDITION_TERMS.get(condition_key)
    if crop_vocab is None or condition is None:
        return None
    return f"{crop_vocab.label} {condition.label} symptoms and management extension guide"


def normalized_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{(parts.hostname or '').lower()}{parts.path.rstrip('/')}"


def safe_url(url: str, sources: tuple[ApprovedSource, ...]) -> ApprovedSource | None:
    """The approved publisher for an HTTPS URL without credentials or odd ports, else None."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return None
    if port not in (None, 443) or host.replace(".", "").isdigit() or ":" in host:
        return None
    return match_approved(host, sources)


def published_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _pertinent(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _GUIDANCE_WORDS)


class _Cache:
    def __init__(self, ttl_seconds: float, clock: Callable[[], float]) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[tuple[str, ...], tuple[float, AgronomyResearch]] = OrderedDict()

    def get(self, key: tuple[str, ...]) -> AgronomyResearch | None:
        entry = self._entries.get(key)
        if entry is None or self._clock() - entry[0] > self._ttl:
            return None
        self._entries.move_to_end(key)
        return entry[1]

    def put(self, key: tuple[str, ...], value: AgronomyResearch) -> None:
        if self._ttl <= 0:
            return
        self._entries[key] = (self._clock(), value)
        self._entries.move_to_end(key)
        while len(self._entries) > _MAX_CACHE_ENTRIES:
            self._entries.popitem(last=False)


class AgronomyResearchService:
    def __init__(
        self,
        searcher: GuidanceSearcher | None,
        *,
        enabled: bool,
        sources: tuple[ApprovedSource, ...],
        max_results: int = 4,
        timeout_seconds: float = 12,
        search_depth: str = "basic",
        extract_enabled: bool = True,
        cache_ttl_seconds: float = 6 * 3600,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._searcher = searcher
        self._enabled = enabled
        self._sources = sources
        self._max_results = max_results
        self._timeout = timeout_seconds
        self._depth = search_depth
        self._extract = extract_enabled
        self._cache = _Cache(cache_ttl_seconds, clock)
        self._clock = clock
        self._now = now

    @property
    def configured(self) -> bool:
        return self._enabled and self._searcher is not None and bool(self._sources)

    async def research(
        self, *, crop: str | None, condition_keys: Sequence[str], country: str | None
    ) -> AgronomyResearch:
        if not self._enabled:
            return AgronomyResearch(ResearchStatus.DISABLED, detail="Guidance search is disabled.")
        if self._searcher is None or not self._sources:
            return AgronomyResearch(
                ResearchStatus.NOT_CONFIGURED, detail="Guidance search is not configured."
            )
        if crop is None or crop not in CROP_TERMS:
            return AgronomyResearch(
                ResearchStatus.SKIPPED,
                detail="The crop was not specific enough for a targeted guidance search.",
            )
        keys = [k for k in dict.fromkeys(condition_keys) if k in CONDITION_TERMS][:MAX_CONDITIONS]
        if not keys:
            return AgronomyResearch(
                ResearchStatus.SKIPPED,
                detail="No specific possible cause to search guidance for.",
            )
        country_hint = country.strip().lower() if country else None
        country_hint = country_hint if country_hint in TAVILY_COUNTRIES else None
        cache_key = (crop, *keys, country_hint or "")
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AgronomyResearch(
                cached.status,
                cached.sources,
                cached.detail,
                duration_ms=0,
                credits=0.0,
                queries=cached.queries,
                cached=True,
            )

        started = self._clock()
        deadline = started + self._timeout
        try:
            async with asyncio.timeout(self._timeout):
                result = await self._run(crop, keys, country_hint, deadline)
        except TimeoutError:
            result = AgronomyResearch(
                ResearchStatus.TIMEOUT, detail="Guidance search took too long and was skipped."
            )
        result = AgronomyResearch(
            result.status,
            result.sources,
            result.detail,
            duration_ms=round((self._clock() - started) * 1000),
            credits=result.credits,
            queries=result.queries,
        )
        if result.status in (ResearchStatus.AVAILABLE, ResearchStatus.NO_MATCHING_SOURCES):
            self._cache.put(cache_key, result)
        return result

    async def _run(
        self, crop: str, keys: list[str], country: str | None, deadline: float
    ) -> AgronomyResearch:
        assert self._searcher is not None
        queries = [q for q in (build_query(crop, key) for key in keys) if q]
        domains = [source.domain for source in self._sources]
        outcomes = await asyncio.gather(
            *(
                self._searcher.search(
                    query=query,
                    include_domains=domains,
                    max_results=self._max_results,
                    search_depth=self._depth,
                    country=country,
                    timeout_seconds=self._timeout,
                )
                for query in queries
            ),
            return_exceptions=True,
        )
        errors = [o for o in outcomes if isinstance(o, BaseException)]
        responses = [o for o in outcomes if isinstance(o, TavilySearchResponse)]
        for error in errors:
            if not isinstance(error, TavilyError):
                raise error
        if not responses:
            first = errors[0]
            assert isinstance(first, TavilyError)
            status = (
                ResearchStatus.TIMEOUT
                if first.kind == TavilyErrorKind.TIMEOUT
                else ResearchStatus.UNAVAILABLE
            )
            return AgronomyResearch(status, detail=f"Tavily: {first}", queries=tuple(queries))

        credits = sum((r.usage.credits or 0.0) for r in responses if r.usage)
        candidates: list[tuple[float, AgronomySource]] = []
        seen: set[str] = set()
        for key, outcome in zip(keys, outcomes, strict=True):
            if not isinstance(outcome, TavilySearchResponse):
                continue
            for item in outcome.results:
                source = self._validate(item, crop, key)
                if source is None or normalized_url(source.url) in seen:
                    continue
                seen.add(normalized_url(source.url))
                candidates.append((item.score or 0.0, source))

        # Interleave conditions so the second hypothesis is not crowded out.
        by_key: dict[str, list[AgronomySource]] = {key: [] for key in keys}
        for _, source in sorted(candidates, key=lambda c: c[0], reverse=True):
            by_key[source.condition_keys[0]].append(source)
        ordered: list[AgronomySource] = []
        while any(by_key.values()) and len(ordered) < self._max_results:
            for key in keys:
                if by_key[key] and len(ordered) < self._max_results:
                    ordered.append(by_key[key].pop(0))

        detail = None if not errors else "Some guidance searches failed; results may be partial."
        if self._extract and ordered and deadline - self._clock() >= _MIN_EXTRACT_SECONDS:
            ordered, extract_credits = await self._enrich(ordered, crop, deadline)
            credits += extract_credits
        sources = tuple(
            source.model_copy(update={"id": f"S{index}"})
            for index, source in enumerate(ordered, start=1)
        )
        if not sources:
            return AgronomyResearch(
                ResearchStatus.NO_MATCHING_SOURCES,
                detail="No relevant guidance was found on the approved agricultural sites.",
                credits=credits or None,
                queries=tuple(queries),
            )
        return AgronomyResearch(
            ResearchStatus.AVAILABLE,
            sources,
            detail,
            credits=credits or None,
            queries=tuple(queries),
        )

    def _validate(self, item: TavilyResult, crop: str, key: str) -> AgronomySource | None:
        approved = safe_url(item.url, self._sources)
        if approved is None:
            return None
        title = safe_excerpt(item.title, limit=200)
        text = f"{item.title} {item.content}"
        crop_ok = mentions_any(text, CROP_TERMS[crop].terms)
        condition_ok = mentions_any(text, CONDITION_TERMS[key].terms)
        if not (crop_ok and condition_ok) or looks_like_instructions(item.title):
            return None
        excerpt = safe_excerpt(item.content)
        if len(excerpt) < MIN_EXCERPT_CHARS or not _pertinent(excerpt):
            return None
        parts = urlsplit(item.url.strip())
        return AgronomySource(
            id="",
            title=title or approved.publisher,
            url=item.url.strip(),
            publisher=approved.publisher,
            domain=(parts.hostname or approved.domain).lower(),
            region=approved.region,
            retrieved_at=self._now(),
            published_at=published_date(item.published_date),
            excerpt=excerpt,
            crop_relevance=crop_ok,
            condition_relevance=condition_ok,
            condition_keys=[key],
        )

    async def _enrich(
        self, sources: list[AgronomySource], crop: str, deadline: float
    ) -> tuple[list[AgronomySource], float]:
        """Replace short search snippets with query-ranked page text when Extract succeeds."""
        assert self._searcher is not None
        targets = sources[:_EXTRACT_URLS]
        key = targets[0].condition_keys[0]
        query = build_query(crop, key) or ""
        try:
            response = await self._searcher.extract(
                urls=[s.url for s in targets],
                query=query,
                timeout_seconds=max(1.0, deadline - self._clock() - 0.5),
            )
        except TavilyError as exc:
            logger.info("Tavily extract skipped: %s", exc.kind.value)
            return sources, 0.0
        extracted = {normalized_url(r.url): r.raw_content for r in response.results}
        enriched: list[AgronomySource] = []
        for source in sources:
            raw = extracted.get(normalized_url(source.url))
            text = safe_excerpt(raw) if raw else ""
            condition_terms = CONDITION_TERMS[source.condition_keys[0]].terms
            if (
                len(text) > len(source.excerpt)
                and mentions_any(text, condition_terms)
                and _pertinent(text)
            ):
                enriched.append(source.model_copy(update={"excerpt": text}))
            else:
                enriched.append(source)
        credits = response.usage.credits if response.usage and response.usage.credits else 0.0
        return enriched, credits

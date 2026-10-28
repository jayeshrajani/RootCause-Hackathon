"""Process-local investigation state: follow-up contexts, daily cap and provider health.

Kept in memory on purpose (no database). Contexts expire, the store is bounded, and everything
resets on restart; with several instances a follow-up can land elsewhere and report expiry.
"""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.schemas.investigation import AgronomySource, InvestigationReview
from app.schemas.triage import TriageResponse


@dataclass(slots=True)
class InvestigationContext:
    response: TriageResponse
    review_en: InvestigationReview
    sources: tuple[AgronomySource, ...]
    region: str | None
    answered: bool = False
    in_progress: bool = False


class InvestigationStore:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, InvestigationContext]] = OrderedDict()

    def put(self, report_id: str, context: InvestigationContext) -> None:
        self._entries[report_id] = (self._clock(), context)
        self._entries.move_to_end(report_id)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def get(self, report_id: str) -> InvestigationContext | None:
        entry = self._entries.get(report_id)
        if entry is None:
            return None
        if self._clock() - entry[0] > self._ttl:
            del self._entries[report_id]
            return None
        return entry[1]

    def __len__(self) -> int:
        return len(self._entries)


class InvestigationTracker:
    """Daily review cap (cost bound) and the last successful live calls, for /health."""

    def __init__(
        self,
        *,
        daily_limit: int,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._limit = daily_limit
        self._today = today
        self._now = now
        self._day: date | None = None
        self._count = 0
        self.review_last_success_at: datetime | None = None
        self.review_last_error: str | None = None
        self.research_last_success_at: datetime | None = None

    def try_acquire(self) -> bool:
        today = self._today()
        if today != self._day:
            self._day, self._count = today, 0
        if self._count >= self._limit:
            return False
        self._count += 1
        return True

    def review_succeeded(self) -> None:
        self.review_last_success_at = self._now()
        self.review_last_error = None

    def review_failed(self, kind: str) -> None:
        self.review_last_error = kind

    def research_succeeded(self) -> None:
        self.research_last_success_at = self._now()

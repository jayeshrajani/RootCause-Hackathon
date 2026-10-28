"""Per-client hourly cap on model-backed endpoints, kept in memory per instance.

Behind a proxy, the client address is read from X-Forwarded-For counting `trusted_hops`
entries from the right, so a client cannot pick its own address by sending the header.
"""

import time
from collections import OrderedDict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.errors import AppError

WINDOW_SECONDS = 3600.0
_MAX_CLIENTS = 10_000


class RateLimiter:
    def __init__(
        self,
        *,
        limit_per_hour: int,
        trusted_hops: int = 0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit_per_hour
        self._hops = trusted_hops
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def client_key(self, request: Request) -> str:
        if self._hops > 0:
            forwarded = request.headers.get("x-forwarded-for", "")
            hops = [part.strip() for part in forwarded.split(",") if part.strip()]
            if len(hops) >= self._hops:
                return hops[-self._hops]
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        key = self.client_key(request)
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            hits = self._hits[key] = deque()
        self._hits.move_to_end(key)
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._limit:
            retry = max(1, int(WINDOW_SECONDS - (now - hits[0])))
            raise AppError(
                429,
                "rate_limited",
                f"Too many requests from this connection. Please try again in {retry // 60 + 1} "
                "minutes.",
            )
        hits.append(now)
        while len(self._hits) > _MAX_CLIENTS:
            self._hits.popitem(last=False)


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency for model-backed routes; a no-op when limits are disabled."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None:
        limiter.check(request)

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimiter
from app.main import create_app


def fake_request(host: str = "10.0.0.1", forwarded: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope: dict[str, Any] = {"type": "http", "headers": headers, "client": (host, 1234)}
    return Request(scope)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_limit_applies_per_client_and_window_slides() -> None:
    clock = Clock()
    limiter = RateLimiter(limit_per_hour=2, clock=clock)

    limiter.check(fake_request())
    limiter.check(fake_request())
    with pytest.raises(AppError) as exc:
        limiter.check(fake_request())
    assert exc.value.status_code == 429

    limiter.check(fake_request(host="10.0.0.2"))
    clock.now = 3600
    limiter.check(fake_request())


def test_forwarded_header_is_only_trusted_from_the_right() -> None:
    limiter = RateLimiter(limit_per_hour=1, trusted_hops=1)

    assert limiter.client_key(fake_request(forwarded="6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    untrusted = RateLimiter(limit_per_hour=1)
    assert untrusted.client_key(fake_request(forwarded="6.6.6.6")) == "10.0.0.1"


def test_model_endpoints_return_429_after_the_limit() -> None:
    settings = Settings(analysis_provider="mock", rate_limit_per_hour=1, _env_file=None)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        first = client.post("/api/v1/triage/translate", json={})
        second = client.post("/api/v1/triage/translate", json={})
        health = client.get("/api/v1/health")

    assert first.status_code == 422
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert health.status_code == 200

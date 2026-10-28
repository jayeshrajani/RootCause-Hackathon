from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

VALID_FORM = {
    "crop": "tomato",
    "description": "Yellow spots on lower leaves, spreading upwards over the last week.",
    "latitude": "18.52",
    "longitude": "73.86",
    "location_label": "Near Pune",
    "symptom_duration": "3_to_7_days",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_PROVIDER_KEYS = (
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_PRIORITY",
    "GEMINI_API_KEY_FALLBACK",
    "ROOTCAUSE_GEMINI_API_KEY",
    "ROOTCAUSE_GEMINI_API_KEY_FALLBACK",
    "CEREBRAS_API_KEY",
    "ROOTCAUSE_CEREBRAS_API_KEY",
    "NEBIUS_API_KEY",
    "ROOTCAUSE_NEBIUS_API_KEY",
    "TAVILY_API_KEY",
    "ROOTCAUSE_TAVILY_API_KEY",
)


@pytest.fixture(autouse=True)
def _no_live_provider_keys(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never reach a paid provider, even if keys are exported in the shell."""
    if request.node.get_closest_marker("live") is None:
        for name in _PROVIDER_KEYS:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test", max_image_bytes=1024, analysis_provider="mock", _env_file=None
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client


def jpeg(name: str = "leaf.jpg") -> tuple[str, tuple[str, bytes, str]]:
    return ("images", (name, JPEG_BYTES, "image/jpeg"))

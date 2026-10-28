from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parents[1]

MEBIBYTE = 1024 * 1024


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed with ROOTCAUSE_."""

    model_config = SettingsConfigDict(
        env_prefix="ROOTCAUSE_",
        # Later files take precedence: apps/api/.env overrides the repo-root .env.
        env_file=(_REPO_ROOT / ".env", _API_DIR / ".env"),
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    max_images: int = Field(default=3, ge=1, le=10)
    max_image_bytes: int = Field(default=5 * MEBIBYTE, ge=1)

    # "auto" uses Cerebras when CEREBRAS_API_KEY is set, otherwise the labelled mock.
    analysis_provider: Literal["auto", "mock", "cerebras"] = "auto"
    analysis_timeout_seconds: float = Field(default=45, gt=0)

    cerebras_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CEREBRAS_API_KEY", "ROOTCAUSE_CEREBRAS_API_KEY"),
    )
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model: str = "qwen-3.8-27b"
    cerebras_reasoning_effort: Literal["low", "medium", "high"] = "low"

    # Raw reference datasets, caches and indexes. Keep outside Git and synced folders.
    data_dir: Path | None = None
    # Local DINOv2 model directory; defaults to DATA_DIR/models/dinov2-small/<revision>.
    embedding_model_dir: Path | None = None
    # FAISS index root (holds one folder per version) and the version to serve.
    retrieval_index_dir: Path | None = None
    retrieval_index_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")

    # Google Earth Engine satellite evidence. Credentials come from ADC (local) or the
    # attached service account / workload identity (production); never from files in Git.
    google_cloud_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_CLOUD_PROJECT_ID", "ROOTCAUSE_GOOGLE_CLOUD_PROJECT_ID"
        ),
    )
    satellite_enabled: bool = True
    satellite_window_days: int = Field(default=45, ge=10, le=120)
    satellite_buffer_m: int = Field(default=100, ge=30, le=1000)
    satellite_timeout_seconds: float = Field(default=25, gt=0, le=120)
    satellite_min_clear_coverage: float = Field(default=0.6, gt=0, le=1)
    satellite_stale_days: int = Field(default=20, ge=5, le=120)
    satellite_cache_ttl_seconds: int = Field(default=6 * 3600, ge=0)

    # Voice input (Google Cloud Speech-to-Text V2). Project defaults to GOOGLE_CLOUD_PROJECT_ID;
    # credentials come from ADC / the attached service account, never from files in Git.
    speech_enabled: bool = True
    speech_project_id: str | None = None
    speech_location: str = Field(default="us", pattern=r"^[a-z0-9-]{2,32}$")
    speech_model: str = "chirp_3"
    # Chirp 3 GA locales; ta-IN, te-IN, mr-IN, bn-IN, gu-IN, kn-IN, ml-IN are Preview only.
    speech_languages: list[str] = Field(default_factory=lambda: ["en-IN", "hi-IN"])
    speech_timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_audio_bytes: int = Field(default=5 * MEBIBYTE, ge=1024, le=8 * MEBIBYTE)

    # Evidence review by NVIDIA Nemotron on Nebius Token Factory (OpenAI-compatible, text only).
    nebius_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("NEBIUS_API_KEY", "ROOTCAUSE_NEBIUS_API_KEY"),
    )
    nebius_enabled: bool = True
    nebius_base_url: str = "https://api.tokenfactory.us-central1.nebius.com/v1/"
    nebius_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nebius_timeout_seconds: float = Field(default=30, gt=0, le=120)
    nebius_max_retries: int = Field(default=1, ge=0, le=3)
    # "default" sends no reasoning switch, for endpoints that reject chat_template_kwargs.
    nebius_reasoning: Literal["default", "off", "low", "on"] = "low"
    nebius_max_tokens: int = Field(default=6000, ge=500, le=32000)
    nebius_structured_output: Literal["json_schema", "json_object"] = "json_schema"
    # Strict mode: a missing or failed Nemotron review is reported as an error state.
    hackathon_require_live_nebius: bool = False

    # Agricultural guidance search (Tavily), restricted to the approved-domain allowlist.
    tavily_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TAVILY_API_KEY", "ROOTCAUSE_TAVILY_API_KEY"),
    )
    tavily_enabled: bool = True
    tavily_timeout_seconds: float = Field(default=12, gt=0, le=60)
    tavily_max_results: int = Field(default=4, ge=1, le=8)
    tavily_cache_ttl_seconds: int = Field(default=6 * 3600, ge=0)
    tavily_extract_enabled: bool = True
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    # Optional subset of the built-in allowlist (hostnames); unknown domains are ignored.
    tavily_allowed_domains: list[str] | None = None

    # Time budget for guidance search + Nemotron review after the first-stage triage.
    investigation_timeout_seconds: float = Field(default=55, gt=0, le=150)
    investigation_daily_limit: int = Field(default=300, ge=0)
    follow_up_ttl_seconds: int = Field(default=3600, ge=60, le=24 * 3600)
    follow_up_max_reports: int = Field(default=500, ge=1, le=10_000)

    # Per-client hourly cap on model-backed endpoints (in memory, per instance).
    rate_limit_enabled: bool = True
    rate_limit_per_hour: int = Field(default=60, ge=1)
    # Proxies in front of the API that append to X-Forwarded-For (Cloud Run: 1).
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    @field_validator("cerebras_api_key", "nebius_api_key", "tavily_api_key", mode="before")
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        # `KEY=` placeholders in .env must not count as a configured provider.
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def nebius_configured(self) -> bool:
        return self.nebius_enabled and self.nebius_api_key is not None

    @property
    def tavily_configured(self) -> bool:
        return self.tavily_enabled and self.tavily_api_key is not None

    @property
    def speech_project(self) -> str | None:
        return self.speech_project_id or self.google_cloud_project_id

    @property
    def speech_configured(self) -> bool:
        return self.speech_enabled and bool(self.speech_project)

    @property
    def satellite_configured(self) -> bool:
        return self.satellite_enabled and bool(self.google_cloud_project_id)

    @property
    def use_cerebras(self) -> bool:
        if self.analysis_provider == "cerebras":
            return True
        return self.analysis_provider == "auto" and self.cerebras_api_key is not None

    @property
    def max_request_bytes(self) -> int:
        # Allow headroom for text fields and multipart boundaries.
        return self.max_images * self.max_image_bytes + MEBIBYTE


@lru_cache
def get_settings() -> Settings:
    return Settings()

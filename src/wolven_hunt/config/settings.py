from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WH_", env_file=".env", extra="ignore")

    llm_provider: Literal["mock", "litellm"] = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "mock/deterministic"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=4, ge=0)
    llm_budget_per_game: int = Field(default=100_000, ge=0)
    llm_provider_map: str = ""
    review_provider: Literal["mock", "litellm"] = "mock"
    review_api_key: str = ""
    review_base_url: str = "https://yunwu.ai/v1"
    review_model: str = "gpt-5.5"
    review_timeout_seconds: float = Field(default=60.0, gt=0)
    evolution_enabled: bool = False
    evolution_window_size: int = Field(default=5, ge=1)
    evolution_min_margin: float = 2.0
    evolution_regression_tolerance: float = 3.0
    evolution_char_cap_ratio: float = Field(default=1.10, gt=0)
    pacing_profile: Literal["live", "fast", "off"] = "live"
    pacing_phase_ms: int = Field(default=600, ge=0)
    pacing_speech_ms: int = Field(default=400, ge=0)
    pacing_night_ms: int = Field(default=1000, ge=0)
    pacing_ack_timeout_ms: int = Field(default=15_000, ge=0)
    runs_dir: Path = Path("runs")
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=7002, ge=1, le=65535)
    api_cors_origins: str = "http://localhost:7001"
    serve_static: bool = False

    @property
    def parsed_api_cors_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()
        )

    def require_real_llm_credentials(self) -> None:
        if self.llm_provider == "litellm" and not self.llm_api_key:
            raise ValueError("WH_LLM_API_KEY is required when WH_LLM_PROVIDER=litellm")


def load_settings() -> Settings:
    settings = Settings()
    settings.require_real_llm_credentials()
    return settings

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WH_", env_file=".env", extra="ignore")

    llm_provider: Literal["mock", "litellm"] = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "mock/deterministic"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_budget_per_game: int = Field(default=100_000, ge=0)
    runs_dir: Path = Path("runs")
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> tuple[str, ...] | object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    def require_real_llm_credentials(self) -> None:
        if self.llm_provider == "litellm" and not self.llm_api_key:
            raise ValueError("WH_LLM_API_KEY is required when WH_LLM_PROVIDER=litellm")


def load_settings() -> Settings:
    settings = Settings()
    settings.require_real_llm_credentials()
    return settings

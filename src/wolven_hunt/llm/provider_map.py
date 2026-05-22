from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.seat import Seat


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: Literal["mock", "litellm"]
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 30.0


class ProviderMap:
    def __init__(self, *, default: ProviderConfig, per_seat: Mapping[int, ProviderConfig]) -> None:
        self.default = default
        self.per_seat = dict(per_seat)

    def for_seat(self, seat: Seat) -> ProviderConfig:
        return self.per_seat.get(seat.number, self.default)


def provider_config_from_settings(settings: Settings) -> ProviderConfig:
    return ProviderConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def load_provider_map(
    settings: Settings, *, environ: Mapping[str, str] | None = None
) -> ProviderMap:
    default = provider_config_from_settings(settings)
    if not settings.llm_provider_map:
        return ProviderMap(default=default, per_seat={})
    path = Path(settings.llm_provider_map)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"provider map must be a mapping: {path}")
    env = os.environ if environ is None else environ
    mapped_default = _config_from_mapping(raw.get("default"), fallback=default, environ=env)
    seats_raw = raw.get("seats") or raw.get("per_seat") or {}
    if not isinstance(seats_raw, dict):
        raise ValueError("provider map seats must be a mapping")
    per_seat: dict[int, ProviderConfig] = {}
    for seat_key, seat_raw in seats_raw.items():
        seat = int(seat_key)
        per_seat[seat] = _config_from_mapping(seat_raw, fallback=mapped_default, environ=env)
    return ProviderMap(default=mapped_default, per_seat=per_seat)


def merge_provider_config(
    fallback: ProviderConfig,
    raw: Mapping[str, object],
    *,
    environ: Mapping[str, str] | None = None,
) -> ProviderConfig:
    return _config_from_mapping(
        raw, fallback=fallback, environ=os.environ if environ is None else environ
    )


def _config_from_mapping(
    raw: object,
    *,
    fallback: ProviderConfig,
    environ: Mapping[str, str],
) -> ProviderConfig:
    if raw is None:
        return fallback
    if not isinstance(raw, Mapping):
        raise ValueError(f"provider config must be a mapping: {raw!r}")
    data = cast(Mapping[str, Any], raw)
    provider = str(data.get("provider", fallback.provider))
    if provider not in {"mock", "litellm"}:
        raise ValueError(f"unsupported provider: {provider}")
    api_key = str(data.get("api_key", ""))
    api_key_env = str(data.get("api_key_env", ""))
    if not api_key and api_key_env:
        if api_key_env not in environ:
            raise ValueError(f"missing api key env: {api_key_env}")
        api_key = environ[api_key_env]
    if not api_key:
        api_key = fallback.api_key
    timeout = data.get("timeout_seconds", fallback.timeout_seconds)
    return replace(
        fallback,
        provider=cast(Literal["mock", "litellm"], provider),
        model=str(data.get("model", fallback.model)),
        base_url=str(data.get("base_url", fallback.base_url)),
        api_key=api_key,
        timeout_seconds=float(timeout),
    )

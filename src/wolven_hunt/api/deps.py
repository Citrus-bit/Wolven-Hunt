from __future__ import annotations

from functools import lru_cache

from wolven_hunt.config.settings import Settings, load_settings
from wolven_hunt.orchestration.runtime import GameRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_registry() -> GameRegistry:
    return GameRegistry(settings=get_settings())

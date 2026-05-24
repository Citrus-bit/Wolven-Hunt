from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import (
    LiteLLMProvider,
    build_provider_from_config,
    normalize_litellm_model,
)
from wolven_hunt.llm.provider_map import (
    ProviderConfig,
    load_provider_map,
    merge_provider_config,
)
from wolven_hunt.orchestration.runtime import GameRegistry


def test_provider_map_empty_uses_global_fallback() -> None:
    provider_map = load_provider_map(
        Settings(
            llm_provider="litellm",
            llm_model="global-model",
            llm_api_key="global-key",
            pacing_profile="off",
        )
    )

    config = provider_map.for_seat(Seat(1))

    assert config.provider == "litellm"
    assert config.model == "global-model"
    assert config.api_key == "global-key"


def test_provider_map_partial_map_partially_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        """
default:
  provider: mock
  model: default-model
seats:
  2:
    provider: litellm
    model: seat-two
    api_key_env: SEAT_TWO_KEY
""",
        encoding="utf-8",
    )

    provider_map = load_provider_map(
        Settings(llm_provider_map=str(path), pacing_profile="off"),
        environ={"SEAT_TWO_KEY": "seat-secret"},
    )

    assert provider_map.for_seat(Seat(1)).model == "default-model"
    assert provider_map.for_seat(Seat(2)).model == "seat-two"
    assert provider_map.for_seat(Seat(2)).api_key == "seat-secret"


def test_provider_map_missing_api_key_env_raises(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        """
default:
  provider: litellm
  model: missing-env
  api_key_env: MISSING_KEY
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing api key env"):
        load_provider_map(Settings(llm_provider_map=str(path), pacing_profile="off"), environ={})


def test_merge_provider_config_none_timeout_uses_fallback() -> None:
    config = merge_provider_config(
        ProviderConfig(
            provider="litellm",
            model="fallback-model",
            timeout_seconds=22,
        ),
        {
            "kind": "llm",
            "provider": "litellm",
            "model": "seat-model",
            "timeout_seconds": None,
        },
    )

    assert config.timeout_seconds == 22


def test_merge_provider_config_reads_thinking_enabled() -> None:
    config = merge_provider_config(
        ProviderConfig(provider="litellm", model="fallback-model"),
        {
            "kind": "llm",
            "provider": "litellm",
            "model": "qwen3.6-flash",
            "thinking_enabled": True,
        },
    )

    assert config.thinking_enabled is True


def test_litellm_model_with_base_url_uses_custom_openai_prefix() -> None:
    assert (
        normalize_litellm_model(model="qwen3.6-flash", base_url="https://example.test/v1")
        == "custom_openai/qwen3.6-flash"
    )
    assert (
        normalize_litellm_model(
            model="custom_openai/qwen3.6-flash",
            base_url="https://example.test/v1",
        )
        == "custom_openai/qwen3.6-flash"
    )


def test_litellm_provider_uses_phase_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": '{"target":1}'}}], "model": "m", "usage": {}}

    monkeypatch.setattr(
        "wolven_hunt.llm.provider._litellm_module",
        lambda: SimpleNamespace(completion=fake_completion),
    )
    provider = LiteLLMProvider(
        model="qwen3.6-flash",
        api_key="test-key",
        timeout_seconds=30,
        phase_timeout_seconds={"DAY_SPEECH": 20},
    )

    provider.complete(
        seat=Seat(1),
        phase="DAY_SPEECH",
        prompt="{}",
        rng=DeterministicRNG("phase-timeout"),
    )

    assert captured["timeout"] == 20


def test_build_provider_from_config_applies_thinking_extra_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": '{"target":1}'}}], "model": "m", "usage": {}}

    monkeypatch.setattr(
        "wolven_hunt.llm.provider._litellm_module",
        lambda: SimpleNamespace(completion=fake_completion),
    )
    provider = build_provider_from_config(
        ProviderConfig(
            provider="litellm",
            model="qwen3.6-flash",
            api_key="test-key",
            thinking_enabled=True,
        )
    )

    provider.complete(
        seat=Seat(1),
        phase="NIGHT_GUARD",
        prompt="{}",
        rng=DeterministicRNG("thinking-provider"),
    )

    assert captured["extra_body"] == {"enable_thinking": True}


def test_provider_api_key_is_not_written_to_manifest(tmp_path: Path) -> None:
    registry = GameRegistry(
        settings=Settings(runs_dir=tmp_path, llm_provider="mock", pacing_profile="off")
    )
    session = asyncio.run(_finished_provider_map_session(registry))

    assert "super-secret" not in session.store.manifest_path.read_text(encoding="utf-8")


async def _finished_provider_map_session(registry: GameRegistry):
    session = await registry.create_game(
        config_path=Path("configs/games/classic_10.yaml"),
        seed="provider-map-secret",
        agent_specs={
            1: {
                "kind": "llm",
                "provider": "mock",
                "model": "mock/deterministic",
                "api_key": "super-secret",
            }
        },
    )
    assert session.task is not None
    await session.task
    return session

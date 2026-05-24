from __future__ import annotations

from tests.conftest import CONFIG_PATH

from wolven_hunt.config.loader import load_game_config


def test_loads_classic_10_config() -> None:
    config = load_game_config(CONFIG_PATH)
    assert config.name == "classic_10"
    assert config.role_pack.seat_count == 10
    assert config.role_pack.roles["wolf"].count == 3
    assert config.role_pack.roles["villager"].count == 4
    assert config.rule_set.first_night_can_die is True
    assert config.rule_set.fallback.actions["DAY_SPEECH"] == "contextual_public_speech"
    assert config.rule_set.fallback.retry_backoff_base_seconds == 1
    assert config.rule_set.fallback.retry_backoff_multiplier == 2
    assert config.rule_set.fallback.retry_backoff_max_seconds == 8
    assert config.rule_set.fallback.retry_backoff_jitter is False
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_SPEECH"] == 45
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_VOTE"] == 20
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_VOTE_PK"] == 20
    assert config.rule_set.fallback.phase_max_retries["DAY_SPEECH"] == 2
    assert config.rule_set.fallback.phase_max_retries["DAY_VOTE"] == 1
    assert config.rule_set.fallback.phase_max_retries["DAY_VOTE_PK"] == 1
    assert len(config.config_hash) == 64

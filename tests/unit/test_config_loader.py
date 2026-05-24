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
    assert config.rule_set.vote.can_abstain is True
    assert config.rule_set.wolves.can_kill_self is True
    assert config.rule_set.wolves.can_kill_wolf_teammate is False
    assert config.rule_set.wolves.can_no_kill is False
    assert config.rule_set.name == "majority_or_side_elimination"
    assert "alive_villagers_eq_0" in config.rule_set.win_conditions.wolf_wins_when
    assert "alive_gods_eq_0" in config.rule_set.win_conditions.wolf_wins_when
    assert "alive_good_players_eq_0" not in config.rule_set.win_conditions.wolf_wins_when
    assert config.rule_set.fallback.actions["DAY_SPEECH"] == "contextual_public_speech"
    assert config.rule_set.fallback.retry_backoff_base_seconds == 1
    assert config.rule_set.fallback.retry_backoff_multiplier == 2
    assert config.rule_set.fallback.retry_backoff_max_seconds == 8
    assert config.rule_set.fallback.retry_backoff_jitter is False
    assert config.rule_set.fallback.phase_timeout_seconds["NIGHT_WOLF_CHAT"] == 15
    assert config.rule_set.fallback.phase_timeout_seconds["NIGHT_WOLF_VOTE"] == 8
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_SPEECH"] == 25
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_VOTE"] == 8
    assert config.rule_set.fallback.phase_timeout_seconds["DAY_VOTE_PK"] == 8
    assert config.rule_set.fallback.phase_max_retries["NIGHT_WOLF_CHAT"] == 1
    assert config.rule_set.fallback.phase_max_retries["NIGHT_WOLF_VOTE"] == 0
    assert config.rule_set.fallback.phase_max_retries["DAY_SPEECH"] == 1
    assert config.rule_set.fallback.phase_max_retries["DAY_VOTE"] == 0
    assert config.rule_set.fallback.phase_max_retries["DAY_VOTE_PK"] == 0
    assert len(config.config_hash) == 64

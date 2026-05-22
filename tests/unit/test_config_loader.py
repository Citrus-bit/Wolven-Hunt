from __future__ import annotations

from tests.conftest import CONFIG_PATH

from wolven_hunt.config.loader import load_game_config


def test_loads_classic_8_config() -> None:
    config = load_game_config(CONFIG_PATH)
    assert config.role_pack.seat_count == 8
    assert config.rule_set.first_night_can_die is True
    assert len(config.config_hash) == 64

from __future__ import annotations

from dataclasses import replace

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.orchestration.fsm import day_speech_order


def test_day_speech_starts_after_first_night_death(game_config: GameConfig) -> None:
    state = _state_after_night_deaths(game_config, (6,))

    assert _numbers(day_speech_order(state, game_config.rule_set)) == [
        7,
        8,
        9,
        10,
        1,
        2,
        3,
        4,
        5,
    ]


def test_day_speech_uses_configured_first_speaker_without_night_death(
    game_config: GameConfig,
) -> None:
    state, _ = build_initial_state(game_config, "speech-order-no-death")

    assert _numbers(day_speech_order(state, game_config.rule_set)) == list(range(1, 11))


def test_day_speech_anchors_on_largest_death_when_multiple_players_die(
    game_config: GameConfig,
) -> None:
    state = _state_after_night_deaths(game_config, (4, 8))

    assert _numbers(day_speech_order(state, game_config.rule_set)) == [
        9,
        10,
        1,
        2,
        3,
        5,
        6,
        7,
    ]


def test_day_speech_wraps_when_anchor_is_after_last_seat(game_config: GameConfig) -> None:
    state = _state_after_night_deaths(game_config, (10,))

    assert _numbers(day_speech_order(state, game_config.rule_set)) == list(range(1, 10))


def _state_after_night_deaths(game_config: GameConfig, deaths: tuple[int, ...]) -> GameState:
    state, _ = build_initial_state(game_config, f"speech-order-{'-'.join(map(str, deaths))}")
    for number in deaths:
        state = state.mark_dead(Seat(number), "NIGHT_RESOLVE")
    return replace(state, last_night_deaths=tuple(Seat(number) for number in deaths))


def _numbers(seats: tuple[Seat, ...]) -> list[int]:
    return [seat.number for seat in seats]

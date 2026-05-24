from __future__ import annotations

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.ids import GameId
from wolven_hunt.core.seat import Camp, Role, Seat
from wolven_hunt.core.state import GameState, PlayerState
from wolven_hunt.core.win import check_winner


def _state(roles: tuple[Role, ...], alive: tuple[bool, ...]) -> GameState:
    players = tuple(
        PlayerState(
            seat=Seat(index + 1),
            role=role,
            alive=is_alive,
            death_day=None if is_alive else 1,
            death_phase=None if is_alive else "test",
        )
        for index, (role, is_alive) in enumerate(zip(roles, alive, strict=True))
    )
    base_players = players + tuple(
        PlayerState(
            seat=Seat(index),
            role=Role.VILLAGER,
            alive=False,
            death_day=1,
            death_phase="test",
        )
        for index in range(len(players) + 1, 9)
    )

    return GameState(
        game_id=GameId.deterministic("win"),
        config_hash="hash",
        seed="win",
        players=base_players,
        day=1,
        phase="test",
    )


def test_wolf_strict_majority_wins(game_config: GameConfig) -> None:
    state = _state((Role.WOLF, Role.WOLF, Role.VILLAGER), (True, True, True))
    assert check_winner(state, game_config.rule_set) is Camp.WOLF


def test_equal_counts_with_villager_and_god_alive_do_not_give_wolf_win(
    game_config: GameConfig,
) -> None:
    state = _state(
        (Role.WOLF, Role.WOLF, Role.VILLAGER, Role.SEER),
        (True, True, True, True),
    )
    assert check_winner(state, game_config.rule_set) is None


def test_good_wins_when_all_wolves_dead(game_config: GameConfig) -> None:
    state = _state((Role.WOLF, Role.VILLAGER), (False, True))
    assert check_winner(state, game_config.rule_set) is Camp.GOOD


def test_villager_side_elimination_gives_wolf_win(game_config: GameConfig) -> None:
    state = _state((Role.WOLF, Role.SEER), (True, True))
    assert check_winner(state, game_config.rule_set) is Camp.WOLF


def test_god_side_elimination_gives_wolf_win(game_config: GameConfig) -> None:
    state = _state((Role.WOLF, Role.VILLAGER, Role.SEER), (True, True, False))
    assert check_winner(state, game_config.rule_set) is Camp.WOLF

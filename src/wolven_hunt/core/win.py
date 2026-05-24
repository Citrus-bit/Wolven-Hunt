from __future__ import annotations

from collections.abc import Mapping

from wolven_hunt.config.schema import RuleSet
from wolven_hunt.core.seat import Camp, Role
from wolven_hunt.core.state import GameState


def check_winner(state: GameState, rule_set: RuleSet) -> Camp | None:
    counts = _alive_counts(state)
    if any(
        _condition_matches(condition, counts)
        for condition in rule_set.win_conditions.good_wins_when
    ):
        return Camp.GOOD
    if any(
        _condition_matches(condition, counts)
        for condition in rule_set.win_conditions.wolf_wins_when
    ):
        return Camp.WOLF
    return None


class WinCondition:
    @staticmethod
    def check(state: GameState, rule_set: RuleSet) -> Camp | None:
        return check_winner(state, rule_set)


def _alive_counts(state: GameState) -> dict[str, int]:
    alive_wolves = 0
    alive_good = 0
    alive_villagers = 0
    alive_gods = 0
    for player in state.players:
        if not player.alive:
            continue
        if player.camp is Camp.WOLF:
            alive_wolves += 1
            continue
        alive_good += 1
        if player.role is Role.VILLAGER:
            alive_villagers += 1
        else:
            alive_gods += 1
    return {
        "alive_wolves": alive_wolves,
        "alive_good_players": alive_good,
        "alive_villagers": alive_villagers,
        "alive_gods": alive_gods,
    }


def _condition_matches(condition: str, counts: Mapping[str, int]) -> bool:
    if condition == "alive_wolves_eq_0":
        return counts["alive_wolves"] == 0
    if condition == "alive_good_players_eq_0":
        return counts["alive_good_players"] == 0
    if condition == "alive_wolves_gt_alive_good_players":
        return counts["alive_wolves"] > counts["alive_good_players"]
    if condition == "alive_villagers_eq_0":
        return counts["alive_villagers"] == 0
    if condition == "alive_gods_eq_0":
        return counts["alive_gods"] == 0
    raise ValueError(f"unknown win condition: {condition}")

from __future__ import annotations

from wolven_hunt.core.seat import Camp
from wolven_hunt.core.state import GameState


def check_winner(state: GameState) -> Camp | None:
    alive_wolves, alive_good = state.alive_camp_counts()
    if alive_wolves == 0:
        return Camp.GOOD
    if alive_good == 0 or alive_wolves > alive_good:
        return Camp.WOLF
    return None


class WinCondition:
    @staticmethod
    def check(state: GameState) -> Camp | None:
        return check_winner(state)

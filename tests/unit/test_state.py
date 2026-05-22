from __future__ import annotations

import pytest

from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import PlayerState


def test_dead_player_requires_death_metadata() -> None:
    with pytest.raises(ValueError):
        PlayerState(seat=Seat(1), role=Role.WOLF, alive=False)

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Camp(StrEnum):
    WOLF = "wolf"
    GOOD = "good"


class Role(StrEnum):
    WOLF = "wolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    GUARD = "guard"


ROLE_TO_CAMP: dict[Role, Camp] = {
    Role.WOLF: Camp.WOLF,
    Role.VILLAGER: Camp.GOOD,
    Role.SEER: Camp.GOOD,
    Role.WITCH: Camp.GOOD,
    Role.GUARD: Camp.GOOD,
}


@dataclass(frozen=True, slots=True, order=True)
class Seat:
    """1-based seat number. Board-specific upper bounds are validated by Referee."""

    number: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"seat number must be positive: {self.number}")

    def __str__(self) -> str:
        return str(self.number)


def seat_numbers(seats: tuple[Seat, ...]) -> tuple[int, ...]:
    return tuple(seat.number for seat in seats)

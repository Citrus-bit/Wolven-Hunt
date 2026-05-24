from __future__ import annotations

from dataclasses import dataclass, replace

from wolven_hunt.core.ids import GameId
from wolven_hunt.core.seat import ROLE_TO_CAMP, Camp, Role, Seat


@dataclass(frozen=True, slots=True)
class PlayerState:
    seat: Seat
    role: Role
    alive: bool = True
    death_day: int | None = None
    death_phase: str | None = None

    def __post_init__(self) -> None:
        if not self.alive and self.death_day is None:
            raise ValueError("dead player must have death_day")
        if not self.alive and self.death_phase is None:
            raise ValueError("dead player must have death_phase")

    @property
    def camp(self) -> Camp:
        return ROLE_TO_CAMP[self.role]


@dataclass(frozen=True, slots=True)
class GameState:
    game_id: GameId
    config_hash: str
    seed: str
    players: tuple[PlayerState, ...]
    day: int
    phase: str
    last_guard_target: Seat | None = None
    witch_antidote_used: bool = False
    witch_poison_used: bool = False
    pk_seats: tuple[Seat, ...] = ()
    pk_round: int = 0
    winner: Camp | None = None
    night_guard_target: Seat | None = None
    night_wolf_votes: tuple[tuple[Seat, Seat], ...] = ()
    night_wolf_target: Seat | None = None
    night_witch_action: str | None = None
    night_witch_target: Seat | None = None
    last_night_deaths: tuple[Seat, ...] = ()
    first_night_deaths: tuple[Seat, ...] = ()
    votes: tuple[tuple[Seat, Seat | None], ...] = ()
    pk_votes: tuple[tuple[Seat, Seat | None], ...] = ()

    def player(self, seat: Seat) -> PlayerState:
        if not self.has_seat(seat):
            raise ValueError(f"seat out of game range: {seat.number}")
        return self.players[seat.number - 1]

    def has_seat(self, seat: Seat) -> bool:
        return 1 <= seat.number <= len(self.players)

    def seat_range(self) -> tuple[int, int]:
        if not self.players:
            return (1, 0)
        return (self.players[0].seat.number, self.players[-1].seat.number)

    def role_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for player in self.players:
            counts[player.role.value] = counts.get(player.role.value, 0) + 1
        return counts

    def with_phase(self, phase: str) -> GameState:
        return replace(self, phase=phase)

    def with_day(self, day: int) -> GameState:
        return replace(self, day=day)

    def alive_seats(self) -> tuple[Seat, ...]:
        return tuple(player.seat for player in self.players if player.alive)

    def alive_players(self) -> tuple[PlayerState, ...]:
        return tuple(player for player in self.players if player.alive)

    def wolf_seats(self, *, alive_only: bool = False) -> tuple[Seat, ...]:
        return tuple(
            player.seat
            for player in self.players
            if player.role is Role.WOLF and (player.alive or not alive_only)
        )

    def seats_by_role(self, role: Role, *, alive_only: bool = False) -> tuple[Seat, ...]:
        return tuple(
            player.seat
            for player in self.players
            if player.role is role and (player.alive or not alive_only)
        )

    def alive_camp_counts(self) -> tuple[int, int]:
        alive_wolves = sum(
            1 for player in self.players if player.alive and player.camp is Camp.WOLF
        )
        alive_good = sum(1 for player in self.players if player.alive and player.camp is Camp.GOOD)
        return alive_wolves, alive_good

    def mark_dead(self, seat: Seat, phase: str) -> GameState:
        old = self.player(seat)
        if not old.alive:
            return self
        new_player = replace(old, alive=False, death_day=self.day, death_phase=phase)
        players = tuple(new_player if player.seat == seat else player for player in self.players)
        return replace(self, players=players)

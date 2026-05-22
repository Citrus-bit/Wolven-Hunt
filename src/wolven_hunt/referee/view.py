from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from wolven_hunt.config.schema import RuleSet
from wolven_hunt.core.events import Event
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.referee.visibility import filter_events


@dataclass(frozen=True, slots=True)
class PlayerView:
    perspective: Literal["player", "spectator"]
    seat_or_none: Seat | None
    self_role: Role | None
    teammates: tuple[Seat, ...]
    visible_events: tuple[Event, ...]
    rule_set_summary: dict[str, Any]


def build_view(
    state: GameState,
    events: tuple[Event, ...],
    *,
    rule_set: RuleSet,
    seat: Seat | None,
) -> PlayerView:
    perspective: Literal["player", "spectator"] = "spectator" if seat is None else "player"
    player = state.player(seat) if seat is not None else None
    teammates: tuple[Seat, ...] = ()
    if player is not None and player.role is Role.WOLF:
        teammates = tuple(wolf for wolf in state.wolf_seats() if wolf != player.seat)
    summary: dict[str, Any] = {
        "day": state.day,
        "phase": state.phase,
        "alive_seats": [seat_.number for seat_ in state.alive_seats()],
        "last_guard_target": None
        if state.last_guard_target is None
        else state.last_guard_target.number,
        "pk_seats": [seat_.number for seat_ in state.pk_seats],
        "max_chars": rule_set.speech.max_chars,
        "can_vote_self": rule_set.vote.can_vote_self,
    }
    return PlayerView(
        perspective=perspective,
        seat_or_none=seat,
        self_role=None if player is None else player.role,
        teammates=teammates,
        visible_events=filter_events(events, state=state, seat=seat),
        rule_set_summary=summary,
    )

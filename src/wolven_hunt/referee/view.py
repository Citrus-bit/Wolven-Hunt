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
    seat_start, seat_end = state.seat_range()
    summary: dict[str, Any] = {
        "day": state.day,
        "phase": state.phase,
        "seat_range": {"start": seat_start, "end": seat_end},
        "seat_count": len(state.players),
        "role_counts": state.role_counts(),
        "alive_seats": [seat_.number for seat_ in state.alive_seats()],
        "pk_seats": [seat_.number for seat_ in state.pk_seats],
        "max_chars": rule_set.speech.max_chars,
        "can_vote_self": rule_set.vote.can_vote_self,
        "can_abstain": rule_set.vote.can_abstain,
        "vote_sheriff": rule_set.vote.sheriff,
    }
    if player is not None and player.role is Role.GUARD and state.phase == "NIGHT_GUARD":
        summary["last_guard_target"] = (
            None if state.last_guard_target is None else state.last_guard_target.number
        )
    if player is not None and player.role is Role.WITCH and state.phase == "NIGHT_WITCH":
        summary["wolf_kill_target"] = (
            None if state.night_wolf_target is None else state.night_wolf_target.number
        )
        summary["witch_antidote_available"] = not state.witch_antidote_used
        summary["witch_poison_available"] = not state.witch_poison_used
    return PlayerView(
        perspective=perspective,
        seat_or_none=seat,
        self_role=None if player is None else player.role,
        teammates=teammates,
        visible_events=filter_events(events, state=state, seat=seat),
        rule_set_summary=summary,
    )

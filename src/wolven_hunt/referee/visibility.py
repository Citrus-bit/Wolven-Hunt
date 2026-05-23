from __future__ import annotations

from wolven_hunt.core.events import Event, EventType
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState

HIDDEN_EVENT_TYPES = {
    EventType.AGENT_TIMEOUT,
    EventType.AGENT_INVALID_ACTION,
    EventType.AGENT_FALLBACK_TRIGGERED,
    EventType.LLM_CALL,
}

SPECTATOR_VISIBLE_PRIVATE_EVENT_TYPES = {
    EventType.WOLF_CHAT_MESSAGE,
}


def filter_events(
    events: tuple[Event, ...],
    *,
    state: GameState,
    seat: Seat | None,
) -> tuple[Event, ...]:
    visible: list[Event] = []
    for event in events:
        if event.type in HIDDEN_EVENT_TYPES:
            continue
        if event.type is EventType.GAME_START:
            visible.append(_sanitize_game_start(event, state=state, seat=seat))
            continue
        if event.visibility.public:
            visible.append(event)
            continue
        if seat is None and event.type in SPECTATOR_VISIBLE_PRIVATE_EVENT_TYPES:
            visible.append(event)
            continue
        if seat is not None and seat.number in event.visibility.seats:
            visible.append(event)
    return tuple(visible)


def filter_spectator_events(events: tuple[Event, ...]) -> tuple[Event, ...]:
    visible: list[Event] = []
    for event in events:
        if event.type in HIDDEN_EVENT_TYPES:
            continue
        if event.type is EventType.GAME_START:
            payload = dict(event.payload)
            payload.pop("selected", None)
            payload.pop("candidates", None)
            visible.append(event.model_copy(update={"payload": payload}))
            continue
        if event.visibility.public:
            visible.append(event)
            continue
        if event.type in SPECTATOR_VISIBLE_PRIVATE_EVENT_TYPES:
            visible.append(event)
    return tuple(visible)


def _sanitize_game_start(event: Event, *, state: GameState, seat: Seat | None) -> Event:
    payload = dict(event.payload)
    payload.pop("selected", None)
    payload.pop("candidates", None)
    if seat is not None:
        payload.pop("role_assignment", None)
        player = state.player(seat)
        payload["self_role"] = player.role.value
        if player.role is Role.WOLF:
            payload["teammates"] = [
                wolf.number for wolf in state.wolf_seats() if wolf.number != seat.number
            ]
        else:
            payload["teammates"] = []
    return event.model_copy(update={"payload": payload})

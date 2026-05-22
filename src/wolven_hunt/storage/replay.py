from __future__ import annotations

from wolven_hunt.core.events import Event


def replay_deterministic(events: tuple[Event, ...]) -> tuple[Event, ...]:
    previous_seq = 0
    game_end_count = 0
    for event in events:
        if event.seq <= previous_seq:
            raise ValueError(f"event seq must be strictly increasing: {event.seq}")
        previous_seq = event.seq
        if event.type.value == "game_end":
            game_end_count += 1
    if game_end_count > 1:
        raise ValueError("event log contains more than one game_end")
    return events

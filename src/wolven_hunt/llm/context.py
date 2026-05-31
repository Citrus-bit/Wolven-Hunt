from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from wolven_hunt.core.events import Event

DEFAULT_FORCE_KEEP_TYPES = frozenset(
    {
        "game_start",
        "day_announce",
        "death_at_night",
        "exile",
        "vote_result",
        "vote_pk_enter",
        "witch_action",
        "seer_check_result",
    }
)


def select_events_for_prompt(
    events: tuple[Event, ...],
    *,
    max_count: int = 40,
    force_keep_types: set[str] | frozenset[str] = DEFAULT_FORCE_KEEP_TYPES,
) -> tuple[Event, ...]:
    """Keep important events first, then fill the prompt window with recent events."""
    if max_count <= 0:
        raise ValueError("max_count must be positive")
    if len(events) <= max_count:
        return events

    force_keep = tuple(event for event in events if _event_type(event) in force_keep_types)
    if len(force_keep) >= max_count:
        return _trim_force_keep(force_keep, max_count=max_count)

    selected_by_seq = {event.seq: event for event in force_keep}
    for event in reversed(events):
        if len(selected_by_seq) >= max_count:
            break
        selected_by_seq.setdefault(event.seq, event)
    return tuple(sorted(selected_by_seq.values(), key=lambda event: event.seq))


def build_prompt_visible_events(
    events: tuple[Event, ...],
    *,
    max_count: int = 40,
    summary_threshold: int = 60,
    head_count: int = 10,
    recent_count: int = 30,
    exclude_types: set[str] | frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], ...]:
    """Build deterministic, JSON-serializable visible event context for prompts."""
    if exclude_types:
        events = tuple(event for event in events if _event_type(event) not in exclude_types)
    if len(events) <= summary_threshold:
        return tuple(
            event_to_prompt_dict(event)
            for event in select_events_for_prompt(events, max_count=max_count)
        )

    if head_count < 0 or recent_count < 0:
        raise ValueError("head_count and recent_count must be non-negative")
    if head_count + recent_count >= len(events):
        return tuple(
            event_to_prompt_dict(event)
            for event in select_events_for_prompt(events, max_count=max_count)
        )

    head = events[:head_count]
    middle = events[head_count:-recent_count] if recent_count else events[head_count:]
    recent = events[-recent_count:] if recent_count else ()
    rows = [event_to_prompt_dict(event) for event in head]
    if middle:
        rows.append(summarize_events_for_prompt(middle))
    rows.extend(event_to_prompt_dict(event) for event in recent)
    return tuple(rows)


def build_speech_context(
    events: tuple[Event, ...],
    *,
    current_seat: int | None,
    current_day: int | None,
    alive_seats: Iterable[int] = (),
    max_speeches: int = 20,
) -> dict[str, Any]:
    if max_speeches <= 0:
        raise ValueError("max_speeches must be positive")

    speech_events = tuple(event for event in events if _is_public_speech(event))
    already_spoken_seats: list[int] = []
    seen_seats: set[int] = set()
    for event in speech_events:
        if event.day != current_day or event.phase != "DAY_SPEECH" or event.actor is None:
            continue
        if event.actor in seen_seats:
            continue
        already_spoken_seats.append(event.actor)
        seen_seats.add(event.actor)
    not_yet_spoken_seats = [
        seat
        for seat in alive_seats
        if seat != current_seat and seat not in seen_seats
    ]

    own_public_speeches = tuple(
        _speech_row(event) for event in speech_events if event.actor == current_seat
    )
    prior_public_speeches = tuple(
        _speech_row(event) for event in speech_events if event.actor != current_seat
    )
    return {
        "current_seat": current_seat,
        "already_spoken_seats": already_spoken_seats,
        "not_yet_spoken_seats": not_yet_spoken_seats,
        "own_public_speeches": own_public_speeches[-max_speeches:],
        "prior_public_speeches": prior_public_speeches[-max_speeches:],
    }


def build_current_turn_context(
    events: tuple[Event, ...],
    *,
    current_seat: int | None,
    phase: str,
) -> dict[str, Any]:
    latest_vote_result = _latest_event_of_type(events, "vote_result")
    vote_events = _vote_events_for_result(events, latest_vote_result)
    own_vote = next(
        (_vote_row(event) for event in reversed(vote_events) if event.actor == current_seat),
        None,
    )
    votes_on_me = tuple(
        _vote_row(event)
        for event in vote_events
        if current_seat is not None and _payload_int(event, "target") == current_seat
    )
    latest_own_speech = next(
        (
            _speech_row(event)
            for event in reversed(events)
            if _is_public_speech(event) and event.actor == current_seat
        ),
        None,
    )
    return {
        "reason": _current_turn_reason(
            events,
            current_seat=current_seat,
            phase=phase,
        ),
        "actor_seat": current_seat,
        "latest_own_speech": latest_own_speech,
        "votes_on_me": votes_on_me,
        "own_vote": own_vote,
        "latest_vote_result": (
            None if latest_vote_result is None else event_to_prompt_dict(latest_vote_result)
        ),
    }


def summarize_events_for_prompt(events: Iterable[Event]) -> dict[str, Any]:
    event_tuple = tuple(events)
    if not event_tuple:
        return {
            "type": "summary",
            "day": None,
            "phase": "SUMMARY",
            "actor": None,
            "summary_text": "无中间事件。",
        }

    counts = Counter(_event_type(event) for event in event_tuple)
    count_text = ", ".join(f"{event_type}={count}" for event_type, count in sorted(counts.items()))
    important = [
        _one_line_event_summary(event)
        for event in event_tuple
        if _event_type(event) in DEFAULT_FORCE_KEEP_TYPES
    ]
    important_text = "; ".join(important)
    if not important_text:
        important_text = "无强制保留关键事件"
    first = event_tuple[0]
    last = event_tuple[-1]
    return {
        "type": "summary",
        "day": first.day if first.day == last.day else None,
        "phase": "SUMMARY",
        "actor": None,
        "summary_text": (
            f"压缩事件 seq {first.seq}-{last.seq}, 共 {len(event_tuple)} 条; "
            f"类型计数: {count_text}; 关键事件: {important_text}。"
        ),
    }


def _trim_force_keep(events: tuple[Event, ...], *, max_count: int) -> tuple[Event, ...]:
    game_start = next((event for event in events if _event_type(event) == "game_start"), None)
    selected: list[Event] = []
    seen: set[int] = set()
    if game_start is not None:
        selected.append(game_start)
        seen.add(game_start.seq)
    for event in reversed(events):
        if len(selected) >= max_count:
            break
        if event.seq in seen:
            continue
        selected.append(event)
        seen.add(event.seq)
    return tuple(sorted(selected, key=lambda event: event.seq))


def event_to_prompt_dict(event: Event) -> dict[str, Any]:
    row = event.model_dump(mode="json", exclude={"event_id", "timestamp"})
    payload = dict(row.get("payload") or {})
    for internal_key in ("role_assignment", "rng_stream", "candidates", "selected"):
        payload.pop(internal_key, None)
    row["payload"] = payload
    return row


def _speech_row(event: Event) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "actor": event.actor,
        "text": str(event.payload.get("text", "")),
    }


def _vote_row(event: Event) -> dict[str, Any]:
    payload = event.payload
    return {
        "seq": event.seq,
        "day": event.day,
        "phase": event.phase,
        "actor": event.actor,
        "target": payload.get("target"),
        "abstain": bool(payload.get("abstain", False)),
    }


def _is_public_speech(event: Event) -> bool:
    return _event_type(event) == "speech" and event.visibility.public and event.actor is not None


def _one_line_event_summary(event: Event) -> str:
    payload = event.payload
    details = []
    for key in ("target", "seat", "victim", "exiled", "winner", "camp", "result"):
        if key in payload:
            details.append(f"{key}={payload[key]}")
    suffix = "" if not details else f" ({', '.join(details)})"
    actor = "system" if event.actor is None else f"seat{event.actor}"
    return f"seq{event.seq}:{_event_type(event)}:{actor}{suffix}"


def _event_type(event: Event) -> str:
    return event.type.value


def _latest_event_of_type(events: tuple[Event, ...], event_type: str) -> Event | None:
    for event in reversed(events):
        if _event_type(event) == event_type:
            return event
    return None


def _vote_events_for_result(
    events: tuple[Event, ...],
    latest_vote_result: Event | None,
) -> tuple[Event, ...]:
    if latest_vote_result is None:
        return tuple(event for event in events if _event_type(event) == "vote_cast")
    return tuple(
        event
        for event in events
        if _event_type(event) == "vote_cast"
        and event.day == latest_vote_result.day
        and event.phase == latest_vote_result.phase
        and event.seq < latest_vote_result.seq
    )


def _current_turn_reason(
    events: tuple[Event, ...],
    *,
    current_seat: int | None,
    phase: str,
) -> str:
    if phase != "DAY_LAST_WORDS" or current_seat is None:
        return "normal_turn"
    latest_exile = _latest_event_of_type(events, "exile")
    if latest_exile is not None and _payload_int(latest_exile, "seat") == current_seat:
        return "exiled"
    if any(
        _event_type(event) == "death_at_night"
        and event.day == 1
        and _payload_int(event, "seat") == current_seat
        for event in events
    ):
        return "first_night_death"
    return "other_last_words"


def _payload_int(event: Event, key: str) -> int | None:
    value = event.payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None

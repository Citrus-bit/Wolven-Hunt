from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from wolven_hunt.core.events import Event

DEFAULT_FORCE_KEEP_TYPES = frozenset(
    {
        "game_start",
        "death_at_night",
        "exile",
        "knight_result",
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
) -> tuple[dict[str, Any], ...]:
    """Build deterministic, JSON-serializable visible event context for prompts."""
    if len(events) <= summary_threshold:
        return tuple(
            _event_to_prompt_dict(event)
            for event in select_events_for_prompt(events, max_count=max_count)
        )

    if head_count < 0 or recent_count < 0:
        raise ValueError("head_count and recent_count must be non-negative")
    if head_count + recent_count >= len(events):
        return tuple(
            _event_to_prompt_dict(event)
            for event in select_events_for_prompt(events, max_count=max_count)
        )

    head = events[:head_count]
    middle = events[head_count:-recent_count] if recent_count else events[head_count:]
    recent = events[-recent_count:] if recent_count else ()
    rows = [_event_to_prompt_dict(event) for event in head]
    if middle:
        rows.append(summarize_events_for_prompt(middle))
    rows.extend(_event_to_prompt_dict(event) for event in recent)
    return tuple(rows)


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


def _event_to_prompt_dict(event: Event) -> dict[str, Any]:
    row = event.model_dump(mode="json", exclude={"event_id", "timestamp"})
    payload = dict(row.get("payload") or {})
    for internal_key in ("role_assignment", "rng_stream", "candidates", "selected"):
        payload.pop(internal_key, None)
    row["payload"] = payload
    return row


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

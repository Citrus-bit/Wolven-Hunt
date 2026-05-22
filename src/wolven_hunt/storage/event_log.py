from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from wolven_hunt.core.events import Event
from wolven_hunt.core.ids import EventId


class EventLog:
    """Append-only in-memory event log with deterministic seq/id/timestamp stamping."""

    def __init__(
        self,
        *,
        seed: str,
        start: datetime | None = None,
        on_append: Callable[[Event], None] | None = None,
    ) -> None:
        self._seed = seed
        self._start = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)
        self._events: list[Event] = []
        self._on_append = on_append

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def append(self, event: Event) -> Event:
        seq = len(self._events) + 1
        stamped = event.model_copy(
            update={
                "seq": seq,
                "event_id": EventId.deterministic(self._seed, seq, event.type.value),
                "timestamp": self._start + timedelta(milliseconds=seq),
            }
        )
        try:
            stamped = Event.model_validate(stamped)
        except ValidationError as exc:
            raise ValueError(f"invalid event: {exc}") from exc
        self._events.append(stamped)
        if self._on_append is not None:
            self._on_append(stamped)
        return stamped

    def append_all(self, events: tuple[Event, ...] | list[Event]) -> tuple[Event, ...]:
        return tuple(self.append(event) for event in events)

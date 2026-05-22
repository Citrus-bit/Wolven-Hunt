from __future__ import annotations

from pathlib import Path

from wolven_hunt.core.events import Event


def events_to_jsonl(events: tuple[Event, ...]) -> str:
    return "".join(event.model_dump_json() + "\n" for event in events)


def events_from_jsonl(text: str) -> tuple[Event, ...]:
    return tuple(Event.model_validate_json(line) for line in text.splitlines() if line.strip())


def read_events_jsonl(path: str | Path) -> tuple[Event, ...]:
    return events_from_jsonl(Path(path).read_text(encoding="utf-8"))


def write_events_jsonl(path: str | Path, events: tuple[Event, ...]) -> None:
    Path(path).write_text(events_to_jsonl(events), encoding="utf-8")

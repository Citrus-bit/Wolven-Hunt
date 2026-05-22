from __future__ import annotations

import pytest
from pydantic import ValidationError

from wolven_hunt.core.events import Event, EventType, Visibility, draft_event, public_visibility
from wolven_hunt.core.ids import GameId


def test_visibility_sorts_and_deduplicates_seats() -> None:
    assert Visibility(public=False, seats=(2, 1, 2)).seats == (1, 2)


def test_event_is_frozen() -> None:
    event = draft_event(
        game_id=GameId.deterministic("seed"),
        phase="GAME_START",
        day=1,
        event_type=EventType.GAME_START,
        actor=None,
        visibility=public_visibility(),
    )
    with pytest.raises(ValidationError):
        event.seq = 999  # type: ignore[misc]


def test_unknown_event_type_fails() -> None:
    event = draft_event(
        game_id=GameId.deterministic("seed"),
        phase="GAME_START",
        day=1,
        event_type=EventType.GAME_START,
        actor=None,
        visibility=public_visibility(),
    )
    data = event.model_dump(mode="json")
    data["type"] = "unknown"
    with pytest.raises(ValidationError):
        Event.model_validate(data)

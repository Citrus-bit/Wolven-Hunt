from __future__ import annotations

from wolven_hunt.core.events import DRAFT_TIMESTAMP, Event, EventType, public_visibility
from wolven_hunt.core.ids import EventId, GameId
from wolven_hunt.llm.context import (
    build_prompt_visible_events,
    build_speech_context,
    select_events_for_prompt,
)


def test_select_events_returns_all_when_under_limit() -> None:
    events = tuple(_event(seq, EventType.PHASE_ENTER) for seq in range(1, 5))

    assert select_events_for_prompt(events, max_count=40) == events


def test_select_events_keeps_important_and_recent() -> None:
    events = tuple(
        _event(
            seq,
            {
                1: EventType.GAME_START,
                8: EventType.DEATH_AT_NIGHT,
                15: EventType.EXILE,
                24: EventType.WITCH_ACTION,
                31: EventType.SEER_CHECK_RESULT,
            }.get(seq, EventType.SPEECH),
        )
        for seq in range(1, 61)
    )

    selected = select_events_for_prompt(events, max_count=40)
    selected_types = {event.type for event in selected}

    assert len(selected) == 40
    assert EventType.GAME_START in selected_types
    assert EventType.DEATH_AT_NIGHT in selected_types
    assert EventType.EXILE in selected_types
    assert EventType.WITCH_ACTION in selected_types
    assert EventType.SEER_CHECK_RESULT in selected_types
    assert selected[-1].seq == 60
    assert tuple(event.seq for event in selected) == tuple(sorted(event.seq for event in selected))


def test_build_prompt_visible_events_summarizes_long_context_deterministically() -> None:
    events = tuple(
        _event(
            seq,
            {
                1: EventType.GAME_START,
                18: EventType.DEATH_AT_NIGHT,
                36: EventType.EXILE,
                50: EventType.WITCH_ACTION,
            }.get(seq, EventType.SPEECH),
        )
        for seq in range(1, 76)
    )

    first = build_prompt_visible_events(events)
    second = build_prompt_visible_events(events)
    summary_rows = [row for row in first if row["type"] == "summary"]

    assert first == second
    assert len(summary_rows) == 1
    assert "seq 11-45" in str(summary_rows[0]["summary_text"])
    assert first[0]["seq"] == 1
    assert first[-1]["seq"] == 75
    assert [row["seq"] for row in first[:10]] == list(range(1, 11))
    assert [row["seq"] for row in first[-30:]] == list(range(46, 76))


def test_build_prompt_visible_events_can_exclude_speech_rows() -> None:
    events = (
        _speech_event(1, actor=1, text="我先发言。"),
        _event(2, EventType.DAY_ANNOUNCE),
        _speech_event(3, actor=2, text="我回应1号。"),
    )

    rows = build_prompt_visible_events(events, exclude_types=frozenset({"speech"}))

    assert [row["type"] for row in rows] == ["day_announce"]


def test_build_speech_context_keeps_other_speakers_out_of_own_history() -> None:
    events = (
        _speech_event(1, actor=3, text="我关注4号和6号。"),
        _speech_event(2, actor=4, text="3号点了我4号,我要回应。"),
    )

    context = build_speech_context(events, current_seat=5, current_day=1)

    assert context["current_seat"] == 5
    assert context["already_spoken_seats"] == [3, 4]
    assert context["own_public_speeches"] == ()
    assert context["prior_public_speeches"] == (
        {"seq": 1, "actor": 3, "text": "我关注4号和6号。"},
        {"seq": 2, "actor": 4, "text": "3号点了我4号,我要回应。"},
    )


def test_build_speech_context_marks_later_seats_as_not_yet_spoken() -> None:
    context = build_speech_context(
        (),
        current_seat=1,
        current_day=1,
        alive_seats=tuple(range(1, 9)),
    )

    assert context["already_spoken_seats"] == []
    assert context["not_yet_spoken_seats"] == [2, 3, 4, 5, 6, 7, 8]
    assert 7 in context["not_yet_spoken_seats"]
    assert 8 in context["not_yet_spoken_seats"]


def test_build_speech_context_keeps_recent_speeches() -> None:
    events = tuple(_speech_event(seq, actor=seq, text=f"{seq}号发言") for seq in range(1, 15))

    context = build_speech_context(events, current_seat=15, current_day=1, max_speeches=12)

    assert [row["actor"] for row in context["prior_public_speeches"]] == list(range(3, 15))


def _event(seq: int, event_type: EventType) -> Event:
    return Event(
        event_id=EventId.deterministic("context", seq, event_type.value),
        game_id=GameId.deterministic("context"),
        seq=seq,
        phase="DAY_SPEECH",
        day=1 if seq < 40 else 2,
        timestamp=DRAFT_TIMESTAMP,
        type=event_type,
        actor=None if event_type is EventType.GAME_START else ((seq % 8) + 1),
        visibility=public_visibility(),
        payload={"target": ((seq + 1) % 8) + 1} if event_type is not EventType.SPEECH else {},
    )


def _speech_event(seq: int, *, actor: int, text: str) -> Event:
    return Event(
        event_id=EventId.deterministic("context-speech", seq, actor),
        game_id=GameId.deterministic("context-speech"),
        seq=seq,
        phase="DAY_SPEECH",
        day=1,
        timestamp=DRAFT_TIMESTAMP,
        type=EventType.SPEECH,
        actor=actor,
        visibility=public_visibility(),
        payload={"text": text},
    )

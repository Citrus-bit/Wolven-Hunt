from __future__ import annotations

from threading import Thread
from time import sleep

from wolven_hunt.core.events import EventType, draft_event, public_visibility
from wolven_hunt.core.ids import GameId
from wolven_hunt.orchestration.pacing import (
    PacingController,
    PacingProfile,
    spectator_effect_ack_event,
)


def test_pacing_ack_timeout_unblocks_without_event_log_side_effect() -> None:
    controller = PacingController(
        PacingProfile("live", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=1),
        sleeper=lambda seconds: None,
    )
    event = draft_event(
        game_id=GameId.deterministic("ack-test"),
        phase="NIGHT_START",
        day=1,
        event_type=EventType.PHASE_ENTER,
        actor=None,
        visibility=public_visibility(),
        payload={"phase": "NIGHT_START"},
    )

    controller.on_event(event)


def test_pacing_waits_for_witch_audio_ack() -> None:
    controller = PacingController(
        PacingProfile("live", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=25),
        sleeper=lambda seconds: None,
    )
    controller.ack(phase="NIGHT_WITCH", event="night_witch_done")
    event = draft_event(
        game_id=GameId.deterministic("ack-witch-test"),
        phase="NIGHT_WITCH",
        day=1,
        event_type=EventType.PHASE_ENTER,
        actor=None,
        visibility=public_visibility(),
        payload={"phase": "NIGHT_WITCH"},
    )

    controller.on_event(event)


def test_pacing_waits_for_guard_audio_ack() -> None:
    controller = PacingController(
        PacingProfile("live", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=1000),
        sleeper=lambda seconds: None,
    )
    event = draft_event(
        game_id=GameId.deterministic("ack-guard-test"),
        phase="NIGHT_GUARD",
        day=1,
        event_type=EventType.PHASE_ENTER,
        actor=None,
        visibility=public_visibility(),
        payload={"phase": "NIGHT_GUARD"},
    )
    thread = Thread(target=controller.on_event, args=(event,))

    thread.start()
    sleep(0.02)

    assert thread.is_alive()
    controller.ack(phase="NIGHT_GUARD", event="night_guard_done")
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_live_pacing_waits_for_each_spectator_effect_ack() -> None:
    cases = [
        (EventType.GUARD_PROTECT, "NIGHT_GUARD", 4, {"target": 2}),
        (EventType.WOLF_KILL_DECIDED, "NIGHT_WOLF_VOTE", None, {"target": 2}),
        (EventType.WITCH_ACTION, "NIGHT_WITCH", 3, {"action": "save", "target": 2}),
        (EventType.SEER_CHECK, "NIGHT_SEER", 5, {"target": 2}),
    ]
    for index, (event_type, phase, actor, payload) in enumerate(cases, start=7):
        controller = PacingController(
            PacingProfile("live", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=1000),
            sleeper=lambda seconds: None,
        )
        event = draft_event(
            game_id=GameId.deterministic(f"ack-effect-test-{index}"),
            phase=phase,
            day=1,
            event_type=event_type,
            actor=actor,
            visibility=public_visibility(),
            payload=payload,
        ).model_copy(update={"seq": index})
        thread = Thread(target=controller.on_event, args=(event,))

        thread.start()
        sleep(0.02)

        assert thread.is_alive()
        controller.ack(phase=phase, event=spectator_effect_ack_event(index))
        thread.join(timeout=1)
        assert not thread.is_alive()


def test_fast_pacing_does_not_wait_for_spectator_effect_ack() -> None:
    controller = PacingController(
        PacingProfile("fast", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=1000),
        sleeper=lambda seconds: None,
    )
    event = draft_event(
        game_id=GameId.deterministic("ack-effect-fast-test"),
        phase="NIGHT_WITCH",
        day=1,
        event_type=EventType.WITCH_ACTION,
        actor=3,
        visibility=public_visibility(),
        payload={"action": "save", "target": 5},
    ).model_copy(update={"seq": 11})

    controller.on_event(event)


def test_witch_skip_does_not_wait_for_spectator_effect_ack() -> None:
    controller = PacingController(
        PacingProfile("live", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=1000),
        sleeper=lambda seconds: None,
    )
    event = draft_event(
        game_id=GameId.deterministic("ack-effect-skip-test"),
        phase="NIGHT_WITCH",
        day=1,
        event_type=EventType.WITCH_ACTION,
        actor=3,
        visibility=public_visibility(),
        payload={"action": "skip", "target": None},
    ).model_copy(update={"seq": 12})

    controller.on_event(event)

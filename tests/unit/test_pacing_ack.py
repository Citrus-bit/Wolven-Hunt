from __future__ import annotations

from wolven_hunt.core.events import EventType, draft_event, public_visibility
from wolven_hunt.core.ids import GameId
from wolven_hunt.orchestration.pacing import PacingController, PacingProfile


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

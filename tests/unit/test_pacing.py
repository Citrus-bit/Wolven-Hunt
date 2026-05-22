from __future__ import annotations

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.events import EventType, draft_event, public_visibility
from wolven_hunt.core.ids import GameId
from wolven_hunt.orchestration.pacing import PacingController, PacingProfile, profile_from_settings


def test_pacing_off_is_noop() -> None:
    calls: list[float] = []
    controller = PacingController(
        PacingProfile("off", phase_ms=0, speech_ms=0, night_ms=0, ack_timeout_ms=0),
        sleeper=calls.append,
    )

    for _ in range(100):
        controller.on_event(_event("DAY_VOTE"))

    assert calls == []


def test_live_profile_sleeps_on_phase_changes() -> None:
    calls: list[float] = []
    controller = PacingController(
        PacingProfile("live", phase_ms=600, speech_ms=400, night_ms=1000, ack_timeout_ms=0),
        sleeper=calls.append,
    )

    for _ in range(100):
        controller.on_event(_event("DAY_VOTE"))

    assert sum(calls) >= 60


def test_fast_profile_is_less_than_live_quarter() -> None:
    live = profile_from_settings(Settings(pacing_profile="live"))
    fast = profile_from_settings(Settings(pacing_profile="fast"))

    assert fast.phase_ms <= live.phase_ms / 4


def _event(phase: str):
    return draft_event(
        game_id=GameId.deterministic("pacing-test"),
        phase=phase,
        day=1,
        event_type=EventType.PHASE_ENTER,
        actor=None,
        visibility=public_visibility(),
        payload={"phase": phase},
    )

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.events import Event, EventType
from wolven_hunt.core.state import GameState

PacingName = Literal["live", "fast", "off"]


@dataclass(frozen=True, slots=True)
class PacingProfile:
    name: PacingName
    phase_ms: int
    speech_ms: int
    night_ms: int
    ack_timeout_ms: int


class PacingController:
    def __init__(
        self,
        profile: PacingProfile,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.profile = profile
        self._sleeper = sleeper
        self._condition = threading.Condition()
        self._acks: set[tuple[str, str]] = set()

    def ack(self, *, phase: str, event: str, client_event_id: str = "") -> None:
        del client_event_id
        if self.profile.name == "off":
            return
        with self._condition:
            self._acks.add((phase, event))
            self._condition.notify_all()

    def on_state(self, state: GameState) -> None:
        del state

    def on_event(self, event: Event) -> None:
        if self.profile.name == "off":
            return
        if event.type is EventType.PHASE_ENTER:
            self._sleep(
                self.profile.night_ms if event.phase == "NIGHT_START" else self.profile.phase_ms
            )
            ack_event = _ack_event_for_phase(event.phase)
            if ack_event is not None:
                self._wait_for_ack(event.phase, ack_event)
            return
        if event.type in {
            EventType.SPEECH,
            EventType.WOLF_CHAT_MESSAGE,
            EventType.LAST_WORDS,
        }:
            self._sleep(self.profile.speech_ms)
            return

    def _sleep(self, ms: int) -> None:
        if ms <= 0:
            return
        self._sleeper(ms / 1000)

    def _wait_for_ack(self, phase: str, event: str) -> None:
        timeout_seconds = self.profile.ack_timeout_ms / 1000
        if timeout_seconds <= 0:
            return
        key = (phase, event)
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while key not in self._acks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._condition.wait(remaining)
            self._acks.remove(key)


def profile_from_settings(
    settings: Settings, *, override: PacingName | None = None
) -> PacingProfile:
    name = settings.pacing_profile if override is None else override
    if name == "off":
        return PacingProfile(
            name="off",
            phase_ms=0,
            speech_ms=0,
            night_ms=0,
            ack_timeout_ms=0,
        )
    if name == "fast":
        return PacingProfile(
            name="fast",
            phase_ms=max(0, min(settings.pacing_phase_ms, 80)),
            speech_ms=max(0, min(settings.pacing_speech_ms, 50)),
            night_ms=max(0, min(settings.pacing_night_ms, 120)),
            ack_timeout_ms=0,
        )
    return PacingProfile(
        name="live",
        phase_ms=settings.pacing_phase_ms,
        speech_ms=settings.pacing_speech_ms,
        night_ms=settings.pacing_night_ms,
        ack_timeout_ms=settings.pacing_ack_timeout_ms,
    )


def _ack_event_for_phase(phase: str) -> str | None:
    return {
        "NIGHT_START": "night_intro_done",
        "NIGHT_WOLF_CHAT": "night_wolves_done",
        "NIGHT_WITCH": "night_witch_done",
        "NIGHT_SEER": "night_seer_done",
        "DAY_ANNOUNCE": "day_intro_done",
    }.get(phase)

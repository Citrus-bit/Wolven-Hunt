from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from wolven_hunt.core.events import Event, EventType

SpectatorEffectKind = Literal[
    "guard_shield",
    "wolf_attack",
    "seer_vision",
    "witch_potion",
    "death_reveal",
]


@dataclass(frozen=True, slots=True)
class SpectatorEffect:
    seq: int
    day: int
    phase: str
    kind: SpectatorEffectKind
    actor: int | None
    source_seat: int | None
    target_seat: int
    asset_key: str
    duration_ms: int
    meta: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def event_to_spectator_effects(
    event: Event, events: tuple[Event, ...]
) -> tuple[SpectatorEffect, ...]:
    payload = event.payload
    if event.type is EventType.GUARD_PROTECT:
        target = _int_or_none(payload.get("target"))
        if target is None:
            return ()
        return (
            SpectatorEffect(
                seq=event.seq,
                day=event.day,
                phase=event.phase,
                kind="guard_shield",
                actor=event.actor,
                source_seat=event.actor,
                target_seat=target,
                asset_key="guard_shield",
                duration_ms=0,
                meta={"persist_until": "NIGHT_RESOLVE"},
            ),
        )
    if event.type is EventType.WOLF_KILL_DECIDED:
        target = _int_or_none(payload.get("target"))
        if target is None:
            return ()
        guarded_target = _guard_target_for_day(events, day=event.day)
        blocked = guarded_target == target
        return (
            SpectatorEffect(
                seq=event.seq,
                day=event.day,
                phase=event.phase,
                kind="wolf_attack",
                actor=event.actor,
                source_seat=None,
                target_seat=target,
                asset_key="wolf_attack",
                duration_ms=3000 if blocked else 0,
                meta={"blocked_by_guard": blocked},
            ),
        )
    if event.type is EventType.SEER_CHECK:
        target = _int_or_none(payload.get("target"))
        if target is None:
            return ()
        return (
            SpectatorEffect(
                seq=event.seq,
                day=event.day,
                phase=event.phase,
                kind="seer_vision",
                actor=event.actor,
                source_seat=event.actor,
                target_seat=target,
                asset_key="seer_vision",
                duration_ms=1800,
                meta={},
            ),
        )
    if event.type is EventType.WITCH_ACTION:
        action = payload.get("action")
        target = _int_or_none(payload.get("target"))
        if action not in {"save", "poison"} or target is None:
            return ()
        return (
            SpectatorEffect(
                seq=event.seq,
                day=event.day,
                phase=event.phase,
                kind="witch_potion",
                actor=event.actor,
                source_seat=event.actor,
                target_seat=target,
                asset_key="potion_antidote" if action == "save" else "potion_poison",
                duration_ms=1200,
                meta={"action": action},
            ),
        )
    if event.type is EventType.DAY_ANNOUNCE:
        deaths = payload.get("deaths")
        if not isinstance(deaths, list):
            return ()
        effects: list[SpectatorEffect] = []
        for death in deaths:
            target = _int_or_none(death)
            if target is None:
                continue
            effects.append(
                SpectatorEffect(
                    seq=event.seq,
                    day=event.day,
                    phase=event.phase,
                    kind="death_reveal",
                    actor=None,
                    source_seat=None,
                    target_seat=target,
                    asset_key="out_badge",
                    duration_ms=0,
                    meta={},
                )
            )
        return tuple(effects)
    return ()


def events_to_spectator_effects(
    events: tuple[Event, ...], *, after: int = 0
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    history: list[Event] = []
    for event in events:
        history.append(event)
        if event.seq <= after:
            continue
        rows.extend(
            effect.to_dict() for effect in event_to_spectator_effects(event, tuple(history))
        )
    return tuple(rows)


def _guard_target_for_day(events: tuple[Event, ...], *, day: int) -> int | None:
    for event in reversed(events):
        if event.day != day:
            continue
        if event.type is EventType.GUARD_PROTECT:
            return _int_or_none(event.payload.get("target"))
    return None


def _int_or_none(value: object) -> int | None:
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

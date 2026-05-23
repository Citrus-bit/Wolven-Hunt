from __future__ import annotations

from wolven_hunt.core.events import EventType, draft_event, public_visibility, seats_visibility
from wolven_hunt.core.ids import GameId
from wolven_hunt.storage.event_log import EventLog
from wolven_hunt.storage.spectator_effects import events_to_spectator_effects


def test_spectator_effects_project_private_night_actions() -> None:
    log = EventLog(seed="effects")
    game_id = GameId.deterministic("effects")
    _append(log, game_id, EventType.GUARD_PROTECT, actor=4, payload={"target": 2})
    _append(log, game_id, EventType.WOLF_KILL_DECIDED, actor=None, payload={"target": 2})
    _append(log, game_id, EventType.SEER_CHECK, actor=5, payload={"target": 7})
    _append(
        log,
        game_id,
        EventType.WITCH_ACTION,
        actor=6,
        payload={"action": "save", "target": 2},
    )
    _append(
        log,
        game_id,
        EventType.WITCH_ACTION,
        actor=6,
        payload={"action": "poison", "target": 8},
    )
    _append(
        log,
        game_id,
        EventType.WITCH_ACTION,
        actor=6,
        payload={"action": "skip", "target": None},
    )
    _append(
        log,
        game_id,
        EventType.DAY_ANNOUNCE,
        phase="DAY_ANNOUNCE",
        actor=None,
        visibility_public=True,
        payload={"deaths": [8], "message": "昨晚死亡玩家: 8"},
    )

    effects = events_to_spectator_effects(log.events)

    assert [effect["kind"] for effect in effects] == [
        "guard_shield",
        "wolf_attack",
        "seer_vision",
        "witch_potion",
        "witch_potion",
        "death_reveal",
    ]
    assert effects[1]["target_seat"] == 2
    assert effects[1]["meta"] == {"blocked_by_guard": True}
    assert effects[3]["asset_key"] == "potion_antidote"
    assert effects[4]["asset_key"] == "potion_poison"
    assert effects[5]["asset_key"] == "out_badge"


def test_spectator_effects_after_cursor() -> None:
    log = EventLog(seed="effects-cursor")
    game_id = GameId.deterministic("effects-cursor")
    _append(log, game_id, EventType.GUARD_PROTECT, actor=4, payload={"target": 2})
    _append(log, game_id, EventType.SEER_CHECK, actor=5, payload={"target": 7})

    effects = events_to_spectator_effects(log.events, after=1)

    assert len(effects) == 1
    assert effects[0]["kind"] == "seer_vision"
    assert effects[0]["seq"] == 2


def _append(
    log: EventLog,
    game_id: GameId,
    event_type: EventType,
    *,
    actor: int | None,
    payload: dict[str, object],
    phase: str = "NIGHT_WITCH",
    visibility_public: bool = False,
) -> None:
    visibility = public_visibility() if visibility_public else seats_visibility((actor or 1,))
    log.append(
        draft_event(
            game_id=game_id,
            phase=phase,
            day=1,
            event_type=event_type,
            actor=actor,
            visibility=visibility,
            payload=payload,
        )
    )

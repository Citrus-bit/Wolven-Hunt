from __future__ import annotations

# ruff: noqa: RUF001
from wolven_hunt.core.events import Event, EventType, draft_event, public_visibility
from wolven_hunt.core.state import GameState


def build_role_reveal(state: GameState, events: tuple[Event, ...] = ()) -> Event | None:
    if state.winner is None:
        return None
    payload = build_role_reveal_payload(state, events)
    return draft_event(
        game_id=state.game_id,
        phase="GAME_END",
        day=state.day,
        event_type=EventType.ROLE_REVEAL,
        actor=None,
        visibility=public_visibility(),
        payload=payload,
    )


def build_role_reveal_payload(
    state: GameState,
    events: tuple[Event, ...] = (),
) -> dict[str, object]:
    if state.winner is None:
        raise ValueError("role reveal requires a finished game")
    return {
        "winner": state.winner.value,
        "seats": [
            {
                "seat": player.seat.number,
                "role": player.role.value,
                "alive": player.alive,
            }
            for player in state.players
        ],
        "highlights": _highlights(events),
    }


def _highlights(events: tuple[Event, ...]) -> list[dict[str, object]]:
    highlights: list[dict[str, object]] = []
    for event in events:
        summary = _summary_for_event(event)
        if summary is None:
            continue
        highlights.append({"seq": event.seq, "summary": summary})
        if len(highlights) >= 5:
            break
    if not highlights:
        highlights.append({"seq": 0, "summary": "游戏进入终局"})
    while len(highlights) < 3:
        highlights.append({"seq": highlights[-1]["seq"], "summary": "公开信息持续累积"})
    return highlights[:5]


def _summary_for_event(event: Event) -> str | None:
    payload = event.payload
    if event.type is EventType.DEATH_AT_NIGHT and event.day == 1:
        return f"首夜 {payload.get('seat')} 号玩家死亡"
    if event.type is EventType.NO_DEATH_TONIGHT and event.day == 1:
        return "首夜是平安夜"
    if event.type is EventType.SEER_CHECK_RESULT:
        return f"预言家首次查验 {payload.get('target')} 号为{_camp_label(payload.get('camp'))}"
    if event.type is EventType.KNIGHT_RESULT:
        result = "命中狼人" if payload.get("result") == "hit_wolf" else "挑战失败"
        return f"骑士决斗{result}，{payload.get('killed')} 号死亡"
    if event.type is EventType.EXILE:
        return f"白天放逐 {payload.get('seat')} 号玩家"
    return None


def _camp_label(value: object) -> str:
    return "狼人" if value == "wolf" else "好人"

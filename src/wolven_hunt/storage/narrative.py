from __future__ import annotations

# ruff: noqa: RUF001
from dataclasses import asdict, dataclass
from typing import Literal

from wolven_hunt.core.events import Event, EventType

NarrativeKind = Literal["system", "speech", "action", "announce", "verdict"]


@dataclass(frozen=True, slots=True)
class NarrativeRow:
    seq: int
    day: int
    phase: str
    kind: NarrativeKind
    text: str
    actor: int | None
    icon: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def event_to_narrative(event: Event) -> NarrativeRow | None:
    if event.type is EventType.ROLE_REVEAL:
        return None
    payload = event.payload
    if event.type is EventType.PHASE_ENTER:
        text = _phase_text(str(payload.get("phase", event.phase)))
        if text is None:
            return None
        return _row(event, "system", text)
    if event.type is EventType.SPEECH:
        return _row(event, "speech", f"{event.actor}号：{payload.get('text', '')}")
    if event.type is EventType.LAST_WORDS:
        return _row(event, "speech", f"{event.actor}号遗言：{payload.get('text', '')}")
    if event.type is EventType.DAY_ANNOUNCE:
        return _row(event, "announce", str(payload.get("message", "白天公示")))
    if event.type is EventType.DEATH_AT_NIGHT:
        return _row(event, "announce", f"{payload.get('seat')}号倒在了夜里")
    if event.type is EventType.NO_DEATH_TONIGHT:
        return _row(event, "announce", "昨晚是平安夜")
    if event.type is EventType.VOTE_CAST:
        return _row(event, "action", f"{event.actor}号投票给{payload.get('target')}号")
    if event.type is EventType.VOTE_RESULT:
        counts = payload.get("counts")
        return _row(event, "verdict", f"投票结果：{_format_counts(counts)}")
    if event.type is EventType.VOTE_PK_ENTER:
        seats = payload.get("pk_seats", [])
        return _row(event, "verdict", f"平票，{_format_seats(seats)}进入 PK")
    if event.type is EventType.PEACEFUL_DAY:
        return _row(event, "verdict", "本轮无人被放逐，直接进入夜晚")
    if event.type is EventType.EXILE:
        return _row(event, "verdict", f"{payload.get('seat')}号被放逐")
    if event.type is EventType.KNIGHT_CHALLENGE:
        return _row(event, "action", f"骑士向{payload.get('target')}号发起决斗")
    if event.type is EventType.KNIGHT_RESULT:
        result = "命中狼人" if payload.get("result") == "hit_wolf" else "挑战失败"
        return _row(event, "verdict", f"骑士决斗{result}，{payload.get('killed')}号死亡")
    if event.type is EventType.GAME_END:
        return _row(event, "verdict", f"游戏结束，{_winner_label(payload.get('winner'))}胜利")
    return None


def _row(event: Event, kind: NarrativeKind, text: str) -> NarrativeRow:
    return NarrativeRow(
        seq=event.seq,
        day=event.day,
        phase=event.phase,
        kind=kind,
        text=text,
        actor=event.actor,
        icon=None,
    )


def _phase_text(phase: str) -> str | None:
    return {
        "NIGHT_START": "夜幕降临",
        "NIGHT_GUARD": "夜幕降临，守卫开始行动",
        "NIGHT_WOLF_CHAT": "狼人正在讨论",
        "NIGHT_WOLF_VOTE": "狼人正在行动",
        "NIGHT_SEER": "预言家正在行动",
        "NIGHT_RESOLVE": "夜晚行动结算中",
        "DAY_ANNOUNCE": "天亮了，开始公布昨夜情况",
        "DAY_LAST_WORDS": "死亡玩家正在发表遗言",
        "DAY_SPEECH": "白天发言开始",
        "DAY_VOTE": "正在举行公民投票",
        "DAY_VOTE_PK": "正在进行 PK 重投",
        "GAME_END": "游戏进入终局",
    }.get(phase)


def _format_counts(value: object) -> str:
    if not isinstance(value, dict):
        return "暂无票型"
    parts = [
        f"{seat}号 {count}票"
        for seat, count in sorted(value.items(), key=lambda item: int(item[0]))
    ]
    return " / ".join(parts)


def _format_seats(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return "、".join(f"{seat}号" for seat in value)


def _winner_label(value: object) -> str:
    return "狼人" if value == "wolf" else "好人"

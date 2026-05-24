from __future__ import annotations

import json
from pathlib import Path

from wolven_hunt.llm.context import build_prompt_visible_events, build_speech_context
from wolven_hunt.referee.view import PlayerView

PHASE_TEMPLATE_KIND: dict[str, str] = {
    "NIGHT_GUARD": "night_action",
    "NIGHT_WOLF_CHAT": "night_action",
    "NIGHT_WOLF_VOTE": "night_action",
    "NIGHT_WITCH": "night_action",
    "NIGHT_SEER": "night_action",
    "DAY_SPEECH": "speech",
    "DAY_VOTE": "vote",
    "DAY_VOTE_PK": "vote",
    "DAY_LAST_WORDS": "last_words",
}


class PromptRenderer:
    def __init__(self, prompt_root: Path, *, version: str = "v1") -> None:
        self.prompt_root = prompt_root
        self.version = version

    def render(
        self,
        *,
        view: PlayerView,
        phase: str,
        schema_json: dict[str, object],
        retry_error: str | None = None,
    ) -> str:
        role_name = "villager" if view.self_role is None else view.self_role.value
        current_seat = None if view.seat_or_none is None else view.seat_or_none.number
        exclude_event_types = frozenset({"speech"}) if phase == "DAY_SPEECH" else frozenset()
        payload = {
            "seat": current_seat,
            "role": role_name,
            "phase": phase,
            "rule_set_summary": view.rule_set_summary,
            "teammates": [seat.number for seat in view.teammates],
            "visible_events": build_prompt_visible_events(
                view.visible_events,
                max_count=40,
                exclude_types=exclude_event_types,
            ),
            "speech_context": build_speech_context(
                view.visible_events,
                current_seat=current_seat,
                current_day=_int_or_none(view.rule_set_summary.get("day")),
                alive_seats=_int_tuple(view.rule_set_summary.get("alive_seats")),
                max_speeches=12,
            ),
            "output_schema": schema_json,
        }
        parts = [
            self._load_system_template(),
            self._load_template(role_name, phase),
            "以下 JSON payload 是你本次决策唯一可用的结构化上下文:",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ]
        if retry_error:
            parts.append(f"上一次输出未被接受: {retry_error}。请只返回符合 schema 的 JSON。")
        return "\n\n".join(parts)

    def _load_template(self, role_name: str, phase: str) -> str:
        kind = PHASE_TEMPLATE_KIND.get(phase, "speech")
        path = self.prompt_root / role_name / f"{kind}.{self.version}.md"
        if not path.exists():
            return f"# {role_name} {kind} {self.version}"
        return path.read_text(encoding="utf-8")

    def _load_system_template(self) -> str:
        path = self.prompt_root / f"system.{self.version}.md"
        if not path.exists():
            return (
                f"# Wolven Hunt System {self.version}\n\n"
                "你必须只基于 PlayerView 中的可见事件行动, 并且只返回 JSON object。"
            )
        return path.read_text(encoding="utf-8")


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[int] = []
    for item in value:
        if isinstance(item, int):
            result.append(item)
        elif isinstance(item, str):
            try:
                result.append(int(item))
            except ValueError:
                continue
    return tuple(result)

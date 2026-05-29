from __future__ import annotations

# ruff: noqa: RUF001
from dataclasses import dataclass
from typing import Literal

from wolven_hunt.core.seat import Role
from wolven_hunt.storage.review_report import ScoreKey

PromptKind = Literal["speech", "vote", "night_action"]

EVOLVABLE_ROLES: tuple[Role, ...] = (
    Role.WOLF,
    Role.VILLAGER,
    Role.SEER,
    Role.WITCH,
    Role.GUARD,
)


@dataclass(frozen=True, slots=True, order=True)
class EvolutionAxis:
    role: Role
    score_key: ScoreKey
    prompt_kind: PromptKind

    @property
    def key(self) -> str:
        return f"{self.role.value}.{self.score_key}"

    @property
    def prompt_relative_path(self) -> str:
        return f"{self.role.value}/{self.prompt_kind}.md"


AXES: tuple[EvolutionAxis, ...] = tuple(
    axis
    for role in EVOLVABLE_ROLES
    for axis in (
        EvolutionAxis(role=role, score_key="speech", prompt_kind="speech"),
        EvolutionAxis(role=role, score_key="voting", prompt_kind="vote"),
        *(
            ()
            if role is Role.VILLAGER
            else (
                EvolutionAxis(
                    role=role,
                    score_key="role_duty",
                    prompt_kind="night_action",
                ),
            )
        ),
    )
)

AXES_BY_KEY: dict[str, EvolutionAxis] = {axis.key: axis for axis in AXES}

COMMON_ANCHORS: dict[PromptKind, tuple[str, ...]] = {
    "speech": ('返回 `{"text": "你的发言"}`。',),
    "vote": ('返回 `{"target": 座位号或 null}`。',),
    "night_action": ("严格参考 JSON payload 中的 `output_schema`。",),
}

ROLE_KIND_ANCHORS: dict[tuple[Role, PromptKind], tuple[str, ...]] = {
    (Role.WOLF, "speech"): (
        "禁止复述、引用、暗示 `wolf_chat_message`、`wolf_kill_vote`、`wolf_kill_decided`、`wolf_tie_random` 的内容。",
        "禁止使用“我们昨晚”“狼队”“我刀”“兄弟”“同伴”“队友”“我们决定”等表达。",
    ),
    (Role.WOLF, "vote"): ("禁止根据夜聊、狼刀、队友身份或狼队私有票型解释投票。",),
    (Role.WOLF, "night_action"): ("不允许单方面刀未自投的狼队友，不允许空刀。",),
    (Role.SEER, "speech"): ("不能编造未出现在 `visible_events` 中的查验。",),
    (Role.SEER, "night_action"): ("可以查验死亡玩家，但不能查验自己。",),
    (Role.WITCH, "night_action"): (
        '返回 `{"action": "save" | "poison" | "skip", "target": 座位号或 null}`。',
    ),
    (Role.GUARD, "night_action"): ("返回 `{\"target\": 座位号}`。",),
}


def axis_from_key(key: str) -> EvolutionAxis:
    try:
        return AXES_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown evolution axis: {key}") from exc


def anchors_for_axis(axis: EvolutionAxis) -> tuple[str, ...]:
    anchors = COMMON_ANCHORS[axis.prompt_kind] + ROLE_KIND_ANCHORS.get(
        (axis.role, axis.prompt_kind),
        (),
    )
    return tuple(dict.fromkeys(anchors))


def validate_invariants(axis: EvolutionAxis, text: str) -> tuple[str, ...]:
    return tuple(anchor for anchor in anchors_for_axis(axis) if anchor not in text)

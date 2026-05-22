from __future__ import annotations

import json

import pytest
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.llm.prompts import PromptRenderer
from wolven_hunt.llm.schemas import (
    GuardOutput,
    KnightOutput,
    LastWordsOutput,
    SeerOutput,
    SpeechOutput,
    VoteOutput,
    WolfChatOutput,
    WolfKillOutput,
)
from wolven_hunt.referee.view import build_view

PROMPT_PAYLOAD_MARKER = "以下 JSON payload 是你本次决策唯一可用的结构化上下文:"

PHASE_SCHEMAS = {
    "NIGHT_GUARD": GuardOutput,
    "NIGHT_WOLF_CHAT": WolfChatOutput,
    "NIGHT_WOLF_VOTE": WolfKillOutput,
    "NIGHT_SEER": SeerOutput,
    "DAY_SPEECH": SpeechOutput,
    "DAY_KNIGHT_INTERRUPT": KnightOutput,
    "DAY_VOTE": VoteOutput,
    "DAY_VOTE_PK": VoteOutput,
    "DAY_LAST_WORDS": LastWordsOutput,
}

ROLE_PHASES = (
    (Role.WOLF, "NIGHT_WOLF_CHAT"),
    (Role.WOLF, "NIGHT_WOLF_VOTE"),
    (Role.WOLF, "DAY_SPEECH"),
    (Role.WOLF, "DAY_VOTE"),
    (Role.WOLF, "DAY_LAST_WORDS"),
    (Role.SEER, "NIGHT_SEER"),
    (Role.SEER, "DAY_SPEECH"),
    (Role.SEER, "DAY_VOTE"),
    (Role.SEER, "DAY_LAST_WORDS"),
    (Role.GUARD, "NIGHT_GUARD"),
    (Role.GUARD, "DAY_SPEECH"),
    (Role.GUARD, "DAY_VOTE"),
    (Role.KNIGHT, "DAY_KNIGHT_INTERRUPT"),
    (Role.KNIGHT, "DAY_VOTE"),
    (Role.KNIGHT, "DAY_LAST_WORDS"),
    (Role.VILLAGER, "DAY_SPEECH"),
    (Role.VILLAGER, "DAY_VOTE"),
    (Role.VILLAGER, "DAY_LAST_WORDS"),
)

MODEL_NAMES_AND_NICKNAMES = {
    "MiniMax-M2.7-highspeed",
    "qwen3.6-plus",
    "kimi-k2.5",
    "mimo-v2.5-pro",
    "glm-5.1",
    "doubao-seed-2-0-pro-260215",
    "deepseek-v4-pro",
    "hy3-preview",
    "minimax老师",
    "万问",
    "光之明面",
    "大米",
    "学霸",
    "小豆包儿",
    "海瑟音",
    "阿元替身版",
}

WOLF_PRIVATE_EVENT_TYPES = {
    EventType.WOLF_CHAT_MESSAGE.value,
    EventType.WOLF_KILL_VOTE.value,
    EventType.WOLF_KILL_DECIDED.value,
    EventType.WOLF_TIE_RANDOM.value,
}

SEER_PRIVATE_EVENT_TYPES = {
    EventType.SEER_CHECK.value,
    EventType.SEER_CHECK_RESULT.value,
}

GUARD_PRIVATE_EVENT_TYPES = {
    EventType.GUARD_PROTECT.value,
}

ALWAYS_HIDDEN_EVENT_TYPES = {
    EventType.LLM_CALL.value,
}


@pytest.mark.leakage
@pytest.mark.parametrize(("role", "phase"), ROLE_PHASES)
def test_prompt_does_not_leak_model_names_or_nicknames(
    game_config: GameConfig,
    role: Role,
    phase: str,
) -> None:
    prompt, _ = _render_prompt(game_config, role=role, phase=phase)

    for forbidden in MODEL_NAMES_AND_NICKNAMES:
        assert forbidden not in prompt


@pytest.mark.leakage
@pytest.mark.parametrize(("role", "phase"), ROLE_PHASES)
def test_prompt_payload_uses_only_referee_filtered_view(
    game_config: GameConfig,
    role: Role,
    phase: str,
) -> None:
    prompt, seat = _render_prompt(game_config, role=role, phase=phase)
    payload = _extract_payload(prompt)
    visible_events_json = json.dumps(payload["visible_events"], ensure_ascii=False)

    assert payload["seat"] == seat.number
    assert payload["role"] == role.value
    assert "role_assignment" not in visible_events_json
    assert '"selected"' not in visible_events_json
    assert '"candidates"' not in visible_events_json

    if role is not Role.WOLF:
        assert payload["teammates"] == []
    else:
        assert set(payload["teammates"])
        assert all(isinstance(teammate, int) for teammate in payload["teammates"])

    if role is not Role.WOLF:
        for event_type in WOLF_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
    if role is not Role.SEER:
        for event_type in SEER_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
    if role is not Role.GUARD:
        for event_type in GUARD_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
    for event_type in ALWAYS_HIDDEN_EVENT_TYPES:
        assert event_type not in visible_events_json


def _render_prompt(
    game_config: GameConfig,
    *,
    role: Role,
    phase: str,
) -> tuple[str, Seat]:
    state, event_log = simulate(game_config, f"prompt-leakage-{role.value}-{phase}")
    seat = next(player.seat for player in state.players if player.role is role)
    view = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=seat)
    renderer = PromptRenderer(game_config.prompt_pack_root, version="v1")
    output_model = PHASE_SCHEMAS[phase]
    return (
        renderer.render(
            view=view,
            phase=phase,
            schema_json=output_model.model_json_schema(),
        ),
        seat,
    )


def _extract_payload(prompt: str) -> dict[str, object]:
    after_marker = prompt.split(PROMPT_PAYLOAD_MARKER, maxsplit=1)[1].lstrip()
    payload, _ = json.JSONDecoder().raw_decode(after_marker)
    assert isinstance(payload, dict)
    return payload

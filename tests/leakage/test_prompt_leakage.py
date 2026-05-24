from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.llm.prompts import PromptRenderer
from wolven_hunt.llm.schemas import (
    GuardOutput,
    LastWordsOutput,
    SeerOutput,
    SpeechOutput,
    VoteOutput,
    WitchOutput,
    WolfChatOutput,
    WolfKillOutput,
)
from wolven_hunt.referee.view import build_view

PROMPT_PAYLOAD_MARKER = "以下 JSON payload 是你本次决策唯一可用的结构化上下文:"

PHASE_SCHEMAS = {
    "NIGHT_GUARD": GuardOutput,
    "NIGHT_WOLF_CHAT": WolfChatOutput,
    "NIGHT_WOLF_VOTE": WolfKillOutput,
    "NIGHT_WITCH": WitchOutput,
    "NIGHT_SEER": SeerOutput,
    "DAY_SPEECH": SpeechOutput,
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
    (Role.WITCH, "NIGHT_WITCH"),
    (Role.WITCH, "DAY_VOTE"),
    (Role.WITCH, "DAY_LAST_WORDS"),
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
    "gemini-3.1-pro-preview",
    "claude-sonnet-4-6",
    "gpt-5.4",
    "minimax老师",
    "万问",
    "光之明面",
    "大米",
    "学霸",
    "小豆包儿",
    "海瑟音",
    "Gemini",
    "克劳德",
    "GPT",
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

GUARD_PRIVATE_SUMMARY_KEYS = {
    "last_guard_target",
}

WITCH_PRIVATE_EVENT_TYPES = {
    EventType.WITCH_ACTION.value,
}

WITCH_PRIVATE_SUMMARY_KEYS = {
    "wolf_kill_target",
    "witch_antidote_available",
    "witch_poison_available",
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
    speech_context = payload["speech_context"]
    assert isinstance(speech_context, dict)
    assert set(speech_context) == {
        "current_seat",
        "already_spoken_seats",
        "own_public_speeches",
        "prior_public_speeches",
    }
    speech_context_json = json.dumps(speech_context, ensure_ascii=False)

    assert payload["seat"] == seat.number
    assert payload["role"] == role.value
    assert speech_context["current_seat"] == seat.number
    assert "role_assignment" not in visible_events_json
    assert "role_assignment" not in speech_context_json
    assert '"selected"' not in visible_events_json
    assert '"selected"' not in speech_context_json
    assert '"candidates"' not in visible_events_json
    assert '"candidates"' not in speech_context_json

    if role is not Role.WOLF:
        assert payload["teammates"] == []
    else:
        assert set(payload["teammates"])
        assert all(isinstance(teammate, int) for teammate in payload["teammates"])

    if role is not Role.WOLF:
        for event_type in WOLF_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
            assert event_type not in speech_context_json
    if role is not Role.SEER:
        for event_type in SEER_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
            assert event_type not in speech_context_json
    if role is not Role.GUARD:
        for event_type in GUARD_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
            assert event_type not in speech_context_json
    if role is not Role.GUARD or phase != "NIGHT_GUARD":
        for key in GUARD_PRIVATE_SUMMARY_KEYS:
            assert key not in payload["rule_set_summary"]
            assert key not in speech_context_json
    if role is not Role.WITCH:
        for event_type in WITCH_PRIVATE_EVENT_TYPES:
            assert event_type not in visible_events_json
            assert event_type not in speech_context_json
    if role is not Role.WITCH or phase != "NIGHT_WITCH":
        for key in WITCH_PRIVATE_SUMMARY_KEYS:
            assert key not in payload["rule_set_summary"]
            assert key not in speech_context_json
    for event_type in ALWAYS_HIDDEN_EVENT_TYPES:
        assert event_type not in visible_events_json
        assert event_type not in speech_context_json


@pytest.mark.leakage
def test_prompt_exposes_last_guard_target_only_to_guard_night_action(
    game_config: GameConfig,
) -> None:
    state, events = build_initial_state(game_config, "prompt-last-guard-target")
    guard = state.seats_by_role(Role.GUARD)[0]
    non_guard = next(player.seat for player in state.players if player.seat != guard)
    state = replace(state, phase="NIGHT_GUARD", last_guard_target=Seat(7))
    renderer = PromptRenderer(game_config.prompt_pack_root, version="v1")

    guard_prompt = renderer.render(
        view=build_view(state, events, rule_set=game_config.rule_set, seat=guard),
        phase="NIGHT_GUARD",
        schema_json=GuardOutput.model_json_schema(),
    )
    non_guard_prompt = renderer.render(
        view=build_view(
            replace(state, phase="DAY_SPEECH"),
            events,
            rule_set=game_config.rule_set,
            seat=non_guard,
        ),
        phase="DAY_SPEECH",
        schema_json=SpeechOutput.model_json_schema(),
    )

    guard_payload = _extract_payload(guard_prompt)
    non_guard_payload = _extract_payload(non_guard_prompt)
    assert guard_payload["rule_set_summary"]["last_guard_target"] == 7
    assert "last_guard_target" not in non_guard_payload["rule_set_summary"]
    assert "last_guard_target" not in non_guard_prompt
    assert "守卫首夜守护" not in non_guard_prompt


@pytest.mark.leakage
def test_prompt_warns_day_speech_is_sequential(game_config: GameConfig) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.VILLAGER, phase="DAY_SPEECH")

    assert "白天发言是顺序进行的" in prompt
    assert "不要因为后续座位暂未发言就指控其沉默或划水" in prompt
    assert "不要把其他座位发言当成自己说过" in prompt
    assert "speech_context" in prompt


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

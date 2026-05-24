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
DEFAULT_PROMPT_VERSION = "v3"

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
    "qwen3.6-flash",
    "kimi-k2.5",
    "mimo-v2.5-pro",
    "glm-4.5-air",
    "doubao-seed-2-0-pro-260215",
    "deepseek-v4-flash",
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
        "not_yet_spoken_seats",
        "own_public_speeches",
        "prior_public_speeches",
    }
    speech_context_json = json.dumps(speech_context, ensure_ascii=False)

    assert payload["seat"] == seat.number
    assert payload["role"] == role.value
    assert payload["rule_set_summary"]["vote_sheriff"] is False
    assert payload["rule_set_summary"]["can_abstain"] is True
    assert payload["rule_set_summary"]["wolf_can_kill_self"] is True
    assert payload["rule_set_summary"]["wolf_can_kill_teammate"] is False
    assert payload["rule_set_summary"]["wolf_can_no_kill"] is False
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
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)

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
    assert "未轮到不等于不活跃" in prompt
    assert "不要因为后续座位暂未发言就指控其沉默、划水、不活跃、发言少或藏身份" in prompt
    assert "not_yet_spoken_seats" in prompt
    assert "不要把其他座位发言当成自己说过" in prompt
    assert "speech_context" in prompt


@pytest.mark.leakage
def test_prompt_declares_no_sheriff_rule(game_config: GameConfig) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.VILLAGER, phase="DAY_VOTE")
    payload = _extract_payload(prompt)

    assert payload["rule_set_summary"]["vote_sheriff"] is False
    assert payload["rule_set_summary"]["can_abstain"] is True
    assert "本局无警长" in prompt
    assert "警长归票" in prompt


@pytest.mark.leakage
def test_wolf_night_prompt_declares_self_kill_rule(game_config: GameConfig) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.WOLF, phase="NIGHT_WOLF_VOTE")

    assert "允许自刀" in prompt
    assert "不允许刀其他狼人同伴" in prompt


@pytest.mark.leakage
def test_prompt_v3_template_pack_is_complete(game_config: GameConfig) -> None:
    root = game_config.prompt_pack_root
    expected_paths = [root / f"system.{DEFAULT_PROMPT_VERSION}.md"]
    for role_name in ("guard", "seer", "villager", "witch", "wolf"):
        for kind in ("last_words", "night_action", "speech", "vote"):
            expected_paths.append(root / role_name / f"{kind}.{DEFAULT_PROMPT_VERSION}.md")

    missing = [str(path.relative_to(root)) for path in expected_paths if not path.exists()]

    assert missing == []


@pytest.mark.leakage
@pytest.mark.parametrize("role", [Role.VILLAGER, Role.WOLF, Role.SEER, Role.WITCH, Role.GUARD])
def test_day_speech_prompt_v3_contains_density_constraints(
    game_config: GameConfig,
    role: Role,
) -> None:
    prompt, _ = _render_prompt(game_config, role=role, phase="DAY_SPEECH")

    assert "高信息密度" in prompt
    assert "禁止占位废话" in prompt
    assert "2-4 句" in prompt
    assert "不要把信息有限/等大家发完作为主要内容" in prompt


@pytest.mark.leakage
def test_wolf_day_prompt_payload_excludes_wolf_private_context(
    game_config: GameConfig,
) -> None:
    state, event_log = simulate(game_config, "prompt-wolf-day-isolation")
    wolf = next(player.seat for player in state.players if player.role is Role.WOLF)
    wolf_chat_text = next(
        str(event.payload["text"])
        for event in event_log.events
        if event.type is EventType.WOLF_CHAT_MESSAGE
    )
    state = replace(state, phase="DAY_SPEECH")
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)

    prompt = renderer.render(
        view=build_view(state, event_log.events, rule_set=game_config.rule_set, seat=wolf),
        phase="DAY_SPEECH",
        schema_json=SpeechOutput.model_json_schema(),
    )
    payload = _extract_payload(prompt)
    visible_events_json = json.dumps(payload["visible_events"], ensure_ascii=False)

    assert "wolf_private_context" not in payload
    assert wolf_chat_text not in visible_events_json
    for event_type in WOLF_PRIVATE_EVENT_TYPES:
        assert event_type not in visible_events_json


@pytest.mark.leakage
def test_wolf_night_prompt_payload_moves_private_events_to_private_context(
    game_config: GameConfig,
) -> None:
    state, event_log = simulate(game_config, "prompt-wolf-night-private-context")
    wolf = next(player.seat for player in state.players if player.role is Role.WOLF)
    wolf_chat_text = next(
        str(event.payload["text"])
        for event in event_log.events
        if event.type is EventType.WOLF_CHAT_MESSAGE
    )
    state = replace(state, phase="NIGHT_WOLF_CHAT")
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)

    prompt = renderer.render(
        view=build_view(state, event_log.events, rule_set=game_config.rule_set, seat=wolf),
        phase="NIGHT_WOLF_CHAT",
        schema_json=WolfChatOutput.model_json_schema(),
    )
    payload = _extract_payload(prompt)
    visible_events_json = json.dumps(payload["visible_events"], ensure_ascii=False)
    private_context_json = json.dumps(payload["wolf_private_context"], ensure_ascii=False)

    assert "wolf_private_context" in payload
    assert wolf_chat_text in private_context_json
    assert EventType.WOLF_CHAT_MESSAGE.value in private_context_json
    for event_type in WOLF_PRIVATE_EVENT_TYPES:
        assert event_type not in visible_events_json


@pytest.mark.leakage
def test_non_wolf_prompt_payload_never_includes_wolf_private_context(
    game_config: GameConfig,
) -> None:
    state, event_log = simulate(game_config, "prompt-non-wolf-no-private-context")
    non_wolf = next(player.seat for player in state.players if player.role is not Role.WOLF)
    state = replace(state, phase="DAY_VOTE")
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)

    prompt = renderer.render(
        view=build_view(
            state,
            event_log.events,
            rule_set=game_config.rule_set,
            seat=non_wolf,
        ),
        phase="DAY_VOTE",
        schema_json=VoteOutput.model_json_schema(),
    )
    payload = _extract_payload(prompt)

    assert "wolf_private_context" not in payload


@pytest.mark.leakage
@pytest.mark.parametrize(
    ("role", "phase"),
    [
        (Role.VILLAGER, "DAY_VOTE"),
        (Role.VILLAGER, "DAY_VOTE_PK"),
        (Role.WOLF, "NIGHT_WOLF_CHAT"),
        (Role.WOLF, "NIGHT_WOLF_VOTE"),
    ],
)
def test_compressed_prompt_phases_move_public_speech_out_of_visible_events(
    game_config: GameConfig,
    role: Role,
    phase: str,
) -> None:
    state, event_log = simulate(game_config, f"prompt-compressed-speech-{role.value}-{phase}")
    seat = next(player.seat for player in state.players if player.role is role)
    state = replace(state, phase=phase)
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)

    prompt = renderer.render(
        view=build_view(state, event_log.events, rule_set=game_config.rule_set, seat=seat),
        phase=phase,
        schema_json=PHASE_SCHEMAS[phase].model_json_schema(),
    )
    payload = _extract_payload(prompt)
    visible_events_json = json.dumps(payload["visible_events"], ensure_ascii=False)
    speech_context_json = json.dumps(payload["speech_context"], ensure_ascii=False)
    last_public_speech = next(
        event
        for event in reversed(event_log.events)
        if event.type is EventType.SPEECH and event.visibility.public
    )
    last_public_speech_text = str(last_public_speech.payload["text"])

    assert all(event["type"] != EventType.SPEECH.value for event in payload["visible_events"])
    assert last_public_speech_text not in visible_events_json
    assert last_public_speech_text in speech_context_json


def _render_prompt(
    game_config: GameConfig,
    *,
    role: Role,
    phase: str,
) -> tuple[str, Seat]:
    state, event_log = simulate(game_config, f"prompt-leakage-{role.value}-{phase}")
    seat = next(player.seat for player in state.players if player.role is role)
    view = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=seat)
    renderer = PromptRenderer(game_config.prompt_pack_root, version=DEFAULT_PROMPT_VERSION)
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

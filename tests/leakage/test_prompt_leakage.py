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
DEFAULT_PROMPT_VERSION = "v5"

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
    "glm-4-flash",
    "doubao-seed-2.0-pro",
    "deepseek-v4-flash",
    "gemini-3.5-flash",
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
    assert payload["rule_set_summary"]["wolf_can_follow_teammate_self_kill"] is True
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
@pytest.mark.parametrize("role", [Role.VILLAGER, Role.WOLF, Role.SEER, Role.WITCH, Role.GUARD])
def test_prompt_warns_day_speech_is_sequential(
    game_config: GameConfig,
    role: Role,
) -> None:
    prompt, _ = _render_prompt(game_config, role=role, phase="DAY_SPEECH")

    assert "白天发言是顺序进行的" in prompt
    assert "只能评价已经出现在 `speech_context.prior_public_speeches` 的公开发言" in prompt
    assert "未轮到不等于不报查验" in prompt
    assert "不能当作不报查验、未回应、沉默、划水、不活跃、发言少或藏身份的证据" in prompt
    assert "not_yet_spoken_seats" in prompt
    assert "不要把其他座位发言当成自己说过" in prompt
    assert "判断预言家是否报查验" in prompt
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
    assert "如果队友本轮选择自刀" in prompt
    assert "你可以跟票配合" in prompt
    assert "不允许单方面刀未自投的狼队友" in prompt


@pytest.mark.leakage
def test_prompt_v5_template_pack_is_complete(game_config: GameConfig) -> None:
    root = game_config.prompt_pack_root
    expected_paths = [root / f"system.{DEFAULT_PROMPT_VERSION}.md"]
    for role_name in ("guard", "seer", "villager", "witch", "wolf"):
        for kind in ("last_words", "night_action", "speech", "vote"):
            expected_paths.append(root / role_name / f"{kind}.{DEFAULT_PROMPT_VERSION}.md")

    missing = [str(path.relative_to(root)) for path in expected_paths if not path.exists()]

    assert missing == []


@pytest.mark.leakage
@pytest.mark.parametrize("role", [Role.VILLAGER, Role.WOLF, Role.SEER, Role.WITCH, Role.GUARD])
def test_day_speech_prompt_v5_contains_density_constraints(
    game_config: GameConfig,
    role: Role,
) -> None:
    prompt, _ = _render_prompt(game_config, role=role, phase="DAY_SPEECH")

    assert "高信息密度" in prompt
    assert "禁止占位废话" in prompt
    assert "2-4 句" in prompt
    assert "不要把信息有限/等大家发完作为主要内容" in prompt


@pytest.mark.leakage
@pytest.mark.parametrize("role", [Role.VILLAGER, Role.WOLF, Role.SEER, Role.WITCH, Role.GUARD])
@pytest.mark.parametrize("phase", ["DAY_VOTE", "DAY_VOTE_PK"])
def test_day_vote_prompt_v5_rejects_unspoken_seat_as_vote_reason(
    game_config: GameConfig,
    role: Role,
    phase: str,
) -> None:
    prompt, _ = _render_prompt(game_config, role=role, phase=phase)

    assert "投票只能参考已经完成的公开发言、公开票型、夜晚公示和可见查验链" in prompt
    assert "后置位尚未发言不是投票理由" in prompt
    assert "判断预言家是否报查验" in prompt


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
def test_wolf_night_prompt_v5_contains_refined_attack_strategy(
    game_config: GameConfig,
) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.WOLF, phase="NIGHT_WOLF_VOTE")

    assert "允许自刀" in prompt
    assert "狼队应统一跟票该自刀目标" in prompt
    assert "不要机械刀明跳预言家" in prompt
    assert "守卫大概率守预言家" in prompt
    assert "优先换刀女巫、守卫、强民或外置神" in prompt
    assert "不能连续两晚守同一人" in prompt
    assert "首夜平安夜要优先按女巫救人高概率评估" in prompt
    assert "不要仅因无人死亡就认定首夜刀口被守卫守护" in prompt
    assert "第二夜若可信预言家已暴露" in prompt
    assert "守卫今晚可能守预言家" in prompt
    assert "不要因为首夜刀的是外置位就认为第二夜刀预言家必成" in prompt
    assert "不能把该刀口当成守卫上一守" in prompt
    assert "守卫风险应按轮次切换评估" in prompt
    assert "夜聊必须同时给出刀口和次日公开策略" in prompt
    assert "谁悍跳、谁倒钩、谁冲锋或切割" in prompt


@pytest.mark.leakage
def test_system_prompt_v5_contains_night_result_and_witch_fact_boundaries(
    game_config: GameConfig,
) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.VILLAGER, phase="DAY_SPEECH")

    assert "只能在 `DAY_ANNOUNCE` 或公开 `visible_events` 已经出现后" in prompt
    assert "夜晚未结算、未公开前不得提前宣布平安夜或死亡结果" in prompt
    assert "公开双死不等于公开证明女巫一定用毒" in prompt
    assert "非女巫不得确定声称女巫毒药状态" in prompt
    assert "死因、狼刀、守卫挡刀等私有夜晚原因" in prompt


@pytest.mark.leakage
def test_vote_prompts_v5_warn_against_unjustified_self_vote(
    game_config: GameConfig,
) -> None:
    for role in (Role.WOLF, Role.SEER, Role.GUARD, Role.WITCH, Role.VILLAGER):
        prompt, _ = _render_prompt(game_config, role=role, phase="DAY_VOTE")

        assert "规则允许普通投票自投，但默认不要自投" in prompt
        assert "公开收益" in prompt


@pytest.mark.leakage
def test_wolf_speech_prompt_v5_requires_public_strategy_consistency(
    game_config: GameConfig,
) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.WOLF, phase="DAY_SPEECH")

    assert "白天发言要和自己此前公开发言" in prompt
    assert "夜间制定的公开战术方向自洽" in prompt
    assert "仍不得泄露夜聊或狼队身份" in prompt


@pytest.mark.leakage
def test_witch_prompts_v5_warn_against_unproven_potion_claims(
    game_config: GameConfig,
) -> None:
    for phase in ("DAY_SPEECH", "DAY_VOTE", "DAY_LAST_WORDS"):
        prompt, _ = _render_prompt(game_config, role=Role.WITCH, phase=phase)

        assert "自己的私有用药记录支持" in prompt
        assert "未公开死因" in prompt


@pytest.mark.leakage
def test_witch_night_prompt_v5_warns_against_blind_first_save(
    game_config: GameConfig,
) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.WITCH, phase="NIGHT_WITCH")

    assert "首夜默认救" in prompt
    assert "不要无脑救" in prompt
    assert "银水不等于铁好" in prompt
    assert "留解药能逼狼刀" in prompt


@pytest.mark.leakage
def test_guard_night_prompt_v5_warns_against_mechanical_seer_guard(
    game_config: GameConfig,
) -> None:
    prompt, _ = _render_prompt(game_config, role=Role.GUARD, phase="NIGHT_GUARD")

    assert "不能机械连续守明预" in prompt
    assert "按规则换守女巫、强民、外置神或自守" in prompt


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

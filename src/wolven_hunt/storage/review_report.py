from __future__ import annotations

# ruff: noqa: RUF001
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import ROLE_TO_CAMP, Role, Seat
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider, ProviderResponse

REVIEW_REPORT_SCHEMA_VERSION: Literal["1.1"] = "1.1"

ScoreKey = Literal[
    "speech",
    "reasoning",
    "voting",
    "camp_contribution",
    "information_control",
    "role_duty",
]
GenerationMode = Literal["real_ai", "offline_mock"]

SCORE_KEYS: tuple[ScoreKey, ...] = (
    "speech",
    "reasoning",
    "voting",
    "camp_contribution",
    "information_control",
    "role_duty",
)
BASE_SCORE_LABELS: dict[ScoreKey, str] = {
    "speech": "发言质量",
    "reasoning": "推理逻辑",
    "voting": "票型执行",
    "camp_contribution": "阵营贡献",
    "information_control": "信息控制",
    "role_duty": "角色职责",
}
ROLE_DUTY_LABELS = {
    Role.WOLF.value: "狼队协同",
    Role.SEER.value: "查验价值",
    Role.WITCH.value: "药水决策",
    Role.GUARD.value: "守护判断",
    Role.VILLAGER.value: "平民职责",
}
ROLE_LABELS = {
    Role.WOLF.value: "狼人",
    Role.VILLAGER.value: "村民",
    Role.SEER.value: "预言家",
    Role.WITCH.value: "女巫",
    Role.GUARD.value: "守卫",
}


class ReviewReportSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: str
    verdict: str
    turning_points: tuple[str, ...] = ()
    overall_assessment: str


class ReviewReportLeaderboardItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    seat: int = Field(ge=1)
    nickname: str
    role: str
    camp: str
    overall_score: int = Field(ge=0, le=100)
    reason: str


class ReviewReportScoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: ScoreKey
    label: str
    value: int = Field(ge=0, le=100)

    @field_validator("label")
    @classmethod
    def _no_generic_skill_label(cls, value: str) -> str:
        if value.strip() == "技能":
            raise ValueError("review score label must be role-aware, not generic skill")
        return value


class ReviewReportPlayerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: int = Field(ge=1)
    nickname: str
    role: str
    camp: str
    alive: bool
    scores: tuple[ReviewReportScoreModel, ...]
    overall_score: int = Field(ge=0, le=100)
    evaluation: str
    evidence: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()
    mistakes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()

    @field_validator("scores")
    @classmethod
    def _scores_are_hex_axes(
        cls,
        value: tuple[ReviewReportScoreModel, ...],
    ) -> tuple[ReviewReportScoreModel, ...]:
        keys = tuple(score.key for score in value)
        if keys != SCORE_KEYS:
            raise ValueError("review scores must contain the fixed six radar axes in order")
        return value


class ReviewReportDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int
    phase: str
    seq: int | None = None
    title: str
    analysis: str
    impact: str


class ReviewReportCounterfactualModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise: str
    likely_outcome: str
    lesson: str


class ReviewReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"] = REVIEW_REPORT_SCHEMA_VERSION
    game_id: str
    generated_at: str
    generation_mode: GenerationMode
    summary: ReviewReportSummaryModel
    leaderboard: tuple[ReviewReportLeaderboardItemModel, ...]
    players: tuple[ReviewReportPlayerModel, ...]
    key_decisions: tuple[ReviewReportDecisionModel, ...]
    counterfactuals: tuple[ReviewReportCounterfactualModel, ...]


def generate_review_report(
    *,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    settings: Settings,
) -> dict[str, Any]:
    prompt = build_review_prompt(
        game_id=game_id,
        events=events,
        narrative_rows=narrative_rows,
        reveal=reveal,
        seat_presentation=seat_presentation,
    )
    provider = _review_provider(settings)
    response = provider.complete(
        seat=Seat(1),
        phase="REVIEW_REPORT",
        prompt=prompt,
        rng=DeterministicRNG(f"review-report:{game_id}"),
    )
    raw = json.loads(response.content)
    report = ReviewReportModel.model_validate(
        {
            **(raw if isinstance(raw, dict) else {}),
            "schema_version": REVIEW_REPORT_SCHEMA_VERSION,
            "game_id": game_id,
            "generated_at": _now_iso(),
            "generation_mode": _generation_mode(settings),
        }
    )
    return report.model_dump(mode="json")


def build_mock_review_report(
    *,
    game_id: str,
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    narrative_rows: tuple[dict[str, object], ...],
    events: tuple[dict[str, object], ...] = (),
) -> dict[str, Any]:
    winner = str(reveal.get("winner") or "unknown")
    seats = _reveal_seats(reveal)
    stats = _build_player_stats(events=events, narrative_rows=narrative_rows)
    players = tuple(
        _mock_player_row(
            seat,
            index=index,
            winner=winner,
            stats=stats.get(_int_value(seat.get("seat"), default=index + 1), {}),
            seat_presentation=seat_presentation,
        )
        for index, seat in enumerate(seats)
    )
    leaderboard = tuple(
        {
            "rank": index + 1,
            "seat": player["seat"],
            "nickname": player["nickname"],
            "role": player["role"],
            "camp": player["camp"],
            "overall_score": player["overall_score"],
            "reason": _leaderboard_reason(player),
        }
        for index, player in enumerate(
            sorted(players, key=lambda item: _int_value(item.get("overall_score")), reverse=True)
        )
    )
    highlights = tuple(str(item.get("summary")) for item in _reveal_highlights(reveal))
    turning_points = tuple(item for item in highlights if item)[:3]
    key_decisions = _mock_key_decisions(events=events, narrative_rows=narrative_rows)
    return ReviewReportModel(
        game_id=game_id,
        generated_at=_now_iso(),
        generation_mode="offline_mock",
        summary=ReviewReportSummaryModel(
            winner=winner,
            verdict="狼人胜利" if winner == "wolf" else "好人胜利",
            turning_points=turning_points or ("终局身份揭晓完成。",),
            overall_assessment=(
                "离线复盘基于观众可见事件、叙事流和终局身份生成，"
                "用于快速定位发言、票型和角色职责表现。"
            ),
        ),
        leaderboard=tuple(ReviewReportLeaderboardItemModel.model_validate(item) for item in leaderboard),
        players=tuple(ReviewReportPlayerModel.model_validate(item) for item in players),
        key_decisions=tuple(ReviewReportDecisionModel.model_validate(item) for item in key_decisions),
        counterfactuals=_mock_counterfactuals(winner=winner, key_decisions=key_decisions),
    ).model_dump(mode="json")


def build_review_prompt(
    *,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
) -> str:
    payload = {
        "game_id": game_id,
        "spectator_events": events,
        "narrative_rows": narrative_rows,
        "role_reveal": reveal,
        "seat_presentation": {
            str(seat): presentation for seat, presentation in sorted(seat_presentation.items())
        },
        "score_axes": [
            {"key": "speech", "label": "发言质量"},
            {"key": "reasoning", "label": "推理逻辑"},
            {"key": "voting", "label": "票型执行"},
            {"key": "camp_contribution", "label": "阵营贡献"},
            {"key": "information_control", "label": "信息控制"},
            {
                "key": "role_duty",
                "label_by_role": {
                    "wolf": "狼队协同",
                    "villager": "平民职责",
                    "seer": "查验价值",
                    "witch": "药水决策",
                    "guard": "守护判断",
                },
            },
        ],
        "output_schema": {
            "summary": {
                "winner": "wolf|good",
                "verdict": "中文胜负结论",
                "turning_points": ["关键转折, 需要引用天数或公开事件"],
                "overall_assessment": "总体评价",
            },
            "leaderboard": [
                {
                    "rank": 1,
                    "seat": 1,
                    "nickname": "玩家昵称",
                    "role": "wolf|villager|seer|witch|guard",
                    "camp": "wolf|good",
                    "overall_score": 0,
                    "reason": "排序理由, 引用公开表现",
                }
            ],
            "players": [
                {
                    "seat": 1,
                    "nickname": "玩家昵称",
                    "role": "wolf|villager|seer|witch|guard",
                    "camp": "wolf|good",
                    "alive": True,
                    "scores": [
                        {"key": "speech", "label": "发言质量", "value": 0},
                        {"key": "reasoning", "label": "推理逻辑", "value": 0},
                        {"key": "voting", "label": "票型执行", "value": 0},
                        {"key": "camp_contribution", "label": "阵营贡献", "value": 0},
                        {"key": "information_control", "label": "信息控制", "value": 0},
                        {"key": "role_duty", "label": "角色职责对应标签", "value": 0},
                    ],
                    "overall_score": 0,
                    "evaluation": "不少于两句的具体评语",
                    "evidence": ["公开证据, 引用第几天/seq/票型/发言"],
                    "strengths": ["做得好的点"],
                    "mistakes": ["可改进问题"],
                    "suggestions": ["下一局建议"],
                }
            ],
            "key_decisions": [
                {
                    "day": 1,
                    "phase": "DAY_VOTE",
                    "seq": 1,
                    "title": "关键决策标题",
                    "analysis": "复盘分析",
                    "impact": "对胜负影响",
                }
            ],
            "counterfactuals": [
                {
                    "premise": "如果...",
                    "likely_outcome": "可能结果",
                    "lesson": "复盘启发",
                }
            ],
        },
    }
    return (
        "你是狼人杀赛后复盘分析师。只基于下方 spectator-safe JSON 输入生成中文结构化复盘报告。"
        "不要引用 raw response、provider、API key、prompt、未授权私有事件或系统实现细节。"
        "只返回 JSON 对象，不要 Markdown。schema_version、game_id、generated_at、generation_mode 由后端填充。"
        "每名玩家必须有 scores 六项，key 顺序必须严格等于 score_axes。"
        "前五项 label 固定为发言质量、推理逻辑、票型执行、阵营贡献、信息控制；"
        "第六项 key=role_duty，label 必须按角色写成狼队协同、查验价值、药水决策、守护判断或平民职责。"
        "不要把村民或任何玩家的评分项叫做技能。"
        "evaluation、evidence、reason、key_decisions 必须引用公开发言、票型、天数或 seq，避免空泛套话。"
        "\n\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


def _review_provider(settings: Settings) -> LiteLLMProvider | MockLLMProvider:
    if settings.review_provider == "litellm":
        if not settings.review_api_key:
            raise ValueError("WH_REVIEW_API_KEY is required when WH_REVIEW_PROVIDER=litellm")
        return LiteLLMProvider(
            model=settings.review_model,
            api_key=settings.review_api_key,
            base_url=settings.review_base_url,
            timeout_seconds=settings.review_timeout_seconds,
        )
    return _MockReviewProvider(model=settings.review_model)


def _generation_mode(settings: Settings) -> GenerationMode:
    return "real_ai" if settings.review_provider == "litellm" else "offline_mock"


class _MockReviewProvider(MockLLMProvider):
    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, rng
        payload = _payload_from_prompt(prompt)
        content = json.dumps(
            _mock_report_content(
                reveal=payload.get("role_reveal") if isinstance(payload, dict) else {},
                seat_presentation=_seat_presentation_from_payload(payload),
                narrative_rows=_narrative_from_payload(payload),
                events=_events_from_payload(payload),
            ),
            ensure_ascii=False,
        )
        return ProviderResponse(content=content, model=self.model)


def _mock_report_content(
    *,
    reveal: object,
    seat_presentation: dict[int, dict[str, str]],
    narrative_rows: tuple[dict[str, object], ...],
    events: tuple[dict[str, object], ...],
) -> dict[str, object]:
    report = build_mock_review_report(
        game_id="mock",
        reveal=reveal if isinstance(reveal, dict) else {},
        seat_presentation=seat_presentation,
        narrative_rows=narrative_rows,
        events=events,
    )
    return {
        key: value
        for key, value in report.items()
        if key not in {"schema_version", "game_id", "generated_at", "generation_mode"}
    }


def _mock_player_row(
    seat: dict[str, object],
    *,
    index: int,
    winner: str,
    stats: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
) -> dict[str, object]:
    seat_number = _int_value(seat.get("seat"), default=index + 1)
    role = str(seat.get("role") or Role.VILLAGER.value)
    camp = _camp_for_role(role)
    alive = bool(seat.get("alive"))
    speech_count = _int_value(stats.get("speech_count"))
    vote_count = _int_value(stats.get("vote_count"))
    abstain_count = _int_value(stats.get("abstain_count"))
    wolf_chat_count = _int_value(stats.get("wolf_chat_count"))
    winner_bonus = 10 if camp == winner else -2
    role_bonus = _role_duty_bonus(role=role, stats=stats, winner_bonus=winner_bonus)
    scores = _hex_scores(
        role=role,
        speech=_clamp_score(58 + speech_count * 7 + (0 if alive else -3) - index),
        reasoning=_clamp_score(56 + speech_count * 5 + vote_count * 2 + winner_bonus - index),
        voting=_clamp_score(58 + vote_count * 7 - abstain_count * 5 + winner_bonus - index),
        camp_contribution=_clamp_score(60 + winner_bonus + speech_count * 3 + vote_count * 2),
        information_control=_clamp_score(60 + speech_count * 3 + wolf_chat_count * 3 + (4 if alive else 0)),
        role_duty=_clamp_score(58 + role_bonus + speech_count * 2 - index),
    )
    overall = round(sum(_int_value(score["value"]) for score in scores) / len(scores))
    nickname = seat_presentation.get(seat_number, {}).get("nickname") or f"{seat_number}号"
    evidence = _player_evidence(seat_number=seat_number, stats=stats, role=role, alive=alive)
    return {
        "seat": seat_number,
        "nickname": nickname,
        "role": role,
        "camp": camp,
        "alive": alive,
        "scores": scores,
        "overall_score": overall,
        "evaluation": _player_evaluation(
            seat_number=seat_number,
            role=role,
            camp=camp,
            overall=overall,
            evidence=evidence,
        ),
        "evidence": evidence,
        "strengths": _player_strengths(role=role, stats=stats, scores=scores),
        "mistakes": _player_mistakes(stats=stats, scores=scores),
        "suggestions": _player_suggestions(role=role, stats=stats),
    }


def _hex_scores(
    *,
    role: str,
    speech: int,
    reasoning: int,
    voting: int,
    camp_contribution: int,
    information_control: int,
    role_duty: int,
) -> tuple[dict[str, object], ...]:
    values = {
        "speech": speech,
        "reasoning": reasoning,
        "voting": voting,
        "camp_contribution": camp_contribution,
        "information_control": information_control,
        "role_duty": role_duty,
    }
    return tuple(
        {
            "key": key,
            "label": ROLE_DUTY_LABELS.get(role, "角色职责")
            if key == "role_duty"
            else BASE_SCORE_LABELS[key],
            "value": _clamp_score(values[key]),
        }
        for key in SCORE_KEYS
    )


def _role_duty_bonus(*, role: str, stats: dict[str, object], winner_bonus: int) -> int:
    if role == Role.WOLF.value:
        return winner_bonus + _int_value(stats.get("wolf_chat_count")) * 8
    if role == Role.VILLAGER.value:
        return winner_bonus + _int_value(stats.get("speech_count")) * 4 + _int_value(stats.get("vote_count")) * 3
    return winner_bonus + 8


def _leaderboard_reason(player: dict[str, object]) -> str:
    evidence = player.get("evidence")
    if isinstance(evidence, tuple | list) and evidence:
        return str(evidence[0])
    role = ROLE_LABELS.get(str(player.get("role") or ""), str(player.get("role") or "玩家"))
    return f"{player.get('seat')}号以{role}身份完成公开发言、票型和角色职责闭环。"


def _player_evaluation(
    *,
    seat_number: int,
    role: str,
    camp: str,
    overall: int,
    evidence: tuple[str, ...],
) -> str:
    role_label = ROLE_LABELS.get(role, role)
    camp_label = "狼人阵营" if camp == "wolf" else "好人阵营"
    first = evidence[0] if evidence else "公开记录较少，主要依据终局身份和票型结果评估"
    return (
        f"{seat_number}号作为{role_label}，综合分 {overall}。"
        f"{first}，其表现更适合放在{camp_label}的整体节奏里判断，"
        "而不是用单一职责分概括。"
    )


def _player_evidence(
    *,
    seat_number: int,
    stats: dict[str, object],
    role: str,
    alive: bool,
) -> tuple[str, ...]:
    evidence: list[str] = []
    speech_text = _string_or_none(stats.get("first_speech"))
    if speech_text:
        evidence.append(f"公开发言记录：{speech_text}")
    vote_text = _string_or_none(stats.get("first_vote"))
    if vote_text:
        evidence.append(vote_text)
    if role == Role.WOLF.value and _int_value(stats.get("wolf_chat_count")) > 0:
        evidence.append(f"夜间狼聊中有 {stats.get('wolf_chat_count')} 次可见协同发言。")
    evidence.append(f"终局时{seat_number}号{'仍然存活' if alive else '已经出局'}。")
    return tuple(evidence[:3])


def _player_strengths(
    *,
    role: str,
    stats: dict[str, object],
    scores: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    top_score = max(scores, key=lambda score: _int_value(score.get("value")))
    strengths = [f"{top_score.get('label')}是本局最突出的维度。"]
    if _int_value(stats.get("vote_count")) > 0:
        strengths.append("参与公开票型，留下了可追踪的阵营选择。")
    if role == Role.VILLAGER.value:
        strengths.append("平民职责按发言、投票和站边执行评估，没有被误记为主动能力。")
    return tuple(strengths[:2])


def _player_mistakes(
    *,
    stats: dict[str, object],
    scores: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    low_score = min(scores, key=lambda score: _int_value(score.get("value")))
    mistakes = [f"{low_score.get('label')}仍有提升空间。"]
    if _int_value(stats.get("abstain_count")) > 0:
        mistakes.append("弃票会降低公开立场的可验证性。")
    if _int_value(stats.get("speech_count")) <= 0:
        mistakes.append("缺少可复盘的公开发言，赛后很难判断真实思路。")
    return tuple(mistakes[:2])


def _player_suggestions(
    *,
    role: str,
    stats: dict[str, object],
) -> tuple[str, ...]:
    duty = ROLE_DUTY_LABELS.get(role, "角色职责")
    suggestions = [f"下一局围绕{duty}明确说明行动或站边理由。"]
    if _int_value(stats.get("vote_count")) > 0:
        suggestions.append("投票前后把怀疑对象、发言矛盾和票型结果连成闭环。")
    else:
        suggestions.append("尽量在关键轮次留下明确票型，减少赛后不可解释空间。")
    return tuple(suggestions)


def _mock_key_decisions(
    *,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    decisions: list[dict[str, object]] = []
    for event in events:
        event_type = str(event.get("type") or "")
        payload = _payload_dict(event)
        if event_type == "vote_result":
            decisions.append(
                {
                    "day": _int_value(event.get("day"), default=1),
                    "phase": str(event.get("phase") or "DAY_VOTE"),
                    "seq": _int_value(event.get("seq")) or None,
                    "title": "公开票型收束",
                    "analysis": f"本轮票型为 {_format_vote_counts(payload.get('counts'), payload.get('abstain_count'))}。",
                    "impact": "票型决定白天压力集中方向，也暴露了阵营站边关系。",
                }
            )
        elif event_type == "exile":
            decisions.append(
                {
                    "day": _int_value(event.get("day"), default=1),
                    "phase": str(event.get("phase") or "DAY_EXILE"),
                    "seq": _int_value(event.get("seq")) or None,
                    "title": f"{payload.get('seat')}号被放逐",
                    "analysis": "放逐结果是公开发言和投票执行共同作用的节点。",
                    "impact": "该节点直接改变存活结构，并影响下一夜的刀口和神职空间。",
                }
            )
        if len(decisions) >= 4:
            break
    if decisions:
        return tuple(decisions)
    speech = next((row for row in narrative_rows if row.get("kind") == "speech"), None)
    return (
        {
            "day": _int_value(speech.get("day"), default=1) if speech else 1,
            "phase": str(speech.get("phase") or "DAY_SPEECH") if speech else "DAY_SPEECH",
            "seq": _int_value(speech.get("seq")) if speech else None,
            "title": "首轮公开发言定调",
            "analysis": "早期公开发言为后续站边、质疑和投票提供了第一批可验证材料。",
            "impact": "如果早期信息密度不足，后续票型更容易被情绪或身份跳法牵引。",
        },
    )


def _mock_counterfactuals(
    *,
    winner: str,
    key_decisions: tuple[dict[str, object], ...],
) -> tuple[ReviewReportCounterfactualModel, ...]:
    first_title = str(key_decisions[0].get("title") if key_decisions else "关键轮次")
    trailing_side = "好人阵营" if winner == "wolf" else "狼人阵营"
    return (
        ReviewReportCounterfactualModel(
            premise=f"如果在「{first_title}」前更早统一归因。",
            likely_outcome=f"{trailing_side}可能被迫提前暴露站边或调整节奏。",
            lesson="复盘时重点看发言理由是否能自然导向票型，而不是只看最终投给了谁。",
        ),
        ReviewReportCounterfactualModel(
            premise="如果低信息玩家在白天给出更明确的怀疑链。",
            likely_outcome="场上可验证信息会更多，夜间行动后的身份判断也会更稳定。",
            lesson="每轮发言都应至少留下一个可被投票或后续死亡验证的判断。",
        ),
    )


def _build_player_stats(
    *,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
) -> dict[int, dict[str, object]]:
    stats: dict[int, dict[str, object]] = {}
    for row in narrative_rows:
        actor = _int_value(row.get("actor"))
        if actor <= 0:
            continue
        seat_stats = stats.setdefault(actor, {})
        if row.get("kind") == "speech":
            seat_stats["speech_count"] = _int_value(seat_stats.get("speech_count")) + 1
            seat_stats.setdefault("first_speech", _trim_text(str(row.get("text") or ""), limit=72))
    for event in events:
        actor = _int_value(event.get("actor"))
        payload = _payload_dict(event)
        event_type = str(event.get("type") or "")
        if actor > 0:
            seat_stats = stats.setdefault(actor, {})
            if event_type == "speech":
                seat_stats["speech_count"] = _int_value(seat_stats.get("speech_count")) + 1
            elif event_type == "wolf_chat_message":
                seat_stats["wolf_chat_count"] = _int_value(seat_stats.get("wolf_chat_count")) + 1
            elif event_type == "vote_cast":
                seat_stats["vote_count"] = _int_value(seat_stats.get("vote_count")) + 1
                if payload.get("abstain") is True or payload.get("target") is None:
                    seat_stats["abstain_count"] = _int_value(seat_stats.get("abstain_count")) + 1
                    seat_stats.setdefault(
                        "first_vote",
                        f"第{event.get('day')}天投票阶段选择弃票。",
                    )
                else:
                    seat_stats.setdefault(
                        "first_vote",
                        f"第{event.get('day')}天投票给{payload.get('target')}号。",
                    )
    return stats


def _format_vote_counts(value: object, abstain_count: object = None) -> str:
    if not isinstance(value, dict) or not value:
        if _int_value(abstain_count) > 0:
            return f"有效票为空，弃票 {_int_value(abstain_count)} 票"
        return "暂无有效票"
    parts = [f"{seat}号 {count}票" for seat, count in sorted(value.items(), key=lambda item: int(item[0]))]
    if _int_value(abstain_count) > 0:
        parts.append(f"弃票 {_int_value(abstain_count)}票")
    return " / ".join(parts)


def _payload_dict(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _camp_for_role(role: str) -> str:
    try:
        return ROLE_TO_CAMP[Role(role)].value
    except ValueError:
        return "unknown"


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _int_value(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _payload_from_prompt(prompt: str) -> dict[str, object]:
    try:
        start = prompt.index("{")
        payload = json.loads(prompt[start:])
    except (ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _seat_presentation_from_payload(payload: object) -> dict[int, dict[str, str]]:
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("seat_presentation")
    if not isinstance(raw, dict):
        return {}
    result: dict[int, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            seat = int(key)
        except (TypeError, ValueError):
            continue
        nickname = str(value.get("nickname") or f"{seat}号")
        icon_path = str(value.get("icon_path") or "")
        result[seat] = {"nickname": nickname, "icon_path": icon_path}
    return result


def _narrative_from_payload(payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("narrative_rows")
    if not isinstance(raw, list):
        return ()
    return tuple(row for row in raw if isinstance(row, dict))


def _events_from_payload(payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("spectator_events")
    if not isinstance(raw, list):
        return ()
    return tuple(row for row in raw if isinstance(row, dict))


def _reveal_seats(reveal: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw = reveal.get("seats")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))


def _reveal_highlights(reveal: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw = reveal.get("highlights")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))


def _trim_text(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

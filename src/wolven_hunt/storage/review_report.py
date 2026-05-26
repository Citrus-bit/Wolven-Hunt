from __future__ import annotations

# ruff: noqa: RUF001
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import ROLE_TO_CAMP, Role, Seat
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider, ProviderResponse

REVIEW_REPORT_SCHEMA_VERSION: Literal["1.1"] = "1.1"
REVIEW_PROMPT_TEMPLATE = Path("configs/prompts/zh/review/report.v1.md")

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
        leaderboard=tuple(
            ReviewReportLeaderboardItemModel.model_validate(item) for item in leaderboard
        ),
        players=tuple(ReviewReportPlayerModel.model_validate(item) for item in players),
        key_decisions=tuple(
            ReviewReportDecisionModel.model_validate(item) for item in key_decisions
        ),
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
    return f"{_load_review_prompt_template()}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _load_review_prompt_template() -> str:
    path = REVIEW_PROMPT_TEMPLATE
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parents[3] / path
    if not path.exists():
        raise FileNotFoundError(f"review prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


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
        information_control=_clamp_score(
            60 + speech_count * 3 + wolf_chat_count * 3 + (4 if alive else 0)
        ),
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
            stats=stats,
            alive=alive,
        ),
        "evidence": evidence,
        "strengths": _player_strengths(
            seat_number=seat_number,
            role=role,
            stats=stats,
            scores=scores,
            alive=alive,
        ),
        "mistakes": _player_mistakes(
            seat_number=seat_number,
            role=role,
            stats=stats,
            scores=scores,
            alive=alive,
        ),
        "suggestions": _player_suggestions(seat_number=seat_number, role=role, stats=stats),
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
        return (
            winner_bonus
            + _int_value(stats.get("speech_count")) * 4
            + _int_value(stats.get("vote_count")) * 3
        )
    return winner_bonus + 8


def _leaderboard_reason(player: dict[str, object]) -> str:
    evidence = player.get("evidence")
    if isinstance(evidence, tuple | list) and evidence:
        return str(evidence[0])
    role = ROLE_LABELS.get(str(player.get("role") or ""), str(player.get("role") or "玩家"))
    return f"{player.get('seat')}号以{role}身份进入终局复盘，公开证据较少。"


def _player_evaluation(
    *,
    seat_number: int,
    role: str,
    camp: str,
    overall: int,
    evidence: tuple[str, ...],
    stats: dict[str, object],
    alive: bool,
) -> str:
    role_label = ROLE_LABELS.get(role, role)
    camp_label = "狼人阵营" if camp == "wolf" else "好人阵营"
    first = (
        evidence[0] if evidence else f"终局时{seat_number}号{'仍然存活' if alive else '已经出局'}"
    )
    second = _evaluation_focus(role=role, stats=stats, alive=alive)
    return (
        f"{seat_number}号作为{role_label}，综合分 {overall}。"
        f"{first}；{second}。"
        f"这名玩家对{camp_label}的价值主要来自这些可见节点，而不是模板化职责描述。"
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
        evidence.append(f"{_day_text(stats.get('first_speech_day'))}公开发言：{speech_text}")
    vote_text = _string_or_none(stats.get("first_vote"))
    if vote_text:
        evidence.append(vote_text)
    received_vote_text = _string_or_none(stats.get("first_received_vote"))
    if received_vote_text:
        evidence.append(received_vote_text)
    exile_day = _int_value(stats.get("exiled_day"))
    if exile_day > 0:
        evidence.append(f"第{exile_day}天被公开投票放逐。")
    night_death_day = _int_value(stats.get("night_death_day"))
    if night_death_day > 0:
        evidence.append(f"第{night_death_day}夜后被公示死亡。")
    if role == Role.WOLF.value and _int_value(stats.get("wolf_chat_count")) > 0:
        wolf_chat = _string_or_none(stats.get("first_wolf_chat"))
        if wolf_chat:
            evidence.append(
                f"夜间狼聊中有 {_int_value(stats.get('wolf_chat_count'))} 次可见协同，首句为：{wolf_chat}"
            )
        else:
            evidence.append(
                f"夜间狼聊中有 {_int_value(stats.get('wolf_chat_count'))} 次可见协同发言。"
            )
    if role == Role.VILLAGER.value and _int_value(stats.get("vote_count")) > 0:
        evidence.append("平民职责主要通过公开发言和票型站边体现。")
    evidence.append(f"终局时{seat_number}号{'仍然存活' if alive else '已经出局'}。")
    return tuple(_unique_strings(evidence)[:4])


def _player_strengths(
    *,
    seat_number: int,
    role: str,
    stats: dict[str, object],
    scores: tuple[dict[str, object], ...],
    alive: bool,
) -> tuple[str, ...]:
    top_score = max(scores, key=lambda score: _int_value(score.get("value")))
    strengths: list[str] = []
    if role == Role.WOLF.value and _int_value(stats.get("wolf_chat_count")) > 0:
        strengths.append(
            f"狼聊中留下 {_int_value(stats.get('wolf_chat_count'))} 次协同记录，能看出{seat_number}号参与夜间节奏。"
        )
    if _int_value(stats.get("vote_count")) > 0 and _int_value(stats.get("abstain_count")) == 0:
        strengths.append(f"{_string_or_none(stats.get('first_vote')) or '投票阶段给出明确目标。'}")
    speech = _string_or_none(stats.get("first_speech"))
    if speech:
        strengths.append(f"发言留下可复盘立场：{speech}")
    if alive:
        strengths.append(f"终局仍存活，{top_score.get('label')}分数主要由公开记录支撑。")
    if role == Role.VILLAGER.value and _int_value(stats.get("vote_count")) > 0:
        strengths.append(f"{seat_number}号的平民职责有公开票型可回看，没有被当成主动技能评分。")
    if not strengths:
        strengths.append(f"{seat_number}号公开暴露面较低，至少没有留下明显越权或无效信息。")
    return tuple(_unique_strings(strengths)[:2])


def _player_mistakes(
    *,
    seat_number: int,
    role: str,
    stats: dict[str, object],
    scores: tuple[dict[str, object], ...],
    alive: bool,
) -> tuple[str, ...]:
    low_score = min(scores, key=lambda score: _int_value(score.get("value")))
    mistakes: list[str] = []
    if _int_value(stats.get("abstain_count")) > 0:
        mistakes.append(
            f"{_string_or_none(stats.get('first_vote')) or '投票阶段弃票。'}这让公开站边更难被验证。"
        )
    if _int_value(stats.get("exiled_day")) > 0:
        mistakes.append(
            f"第{_int_value(stats.get('exiled_day'))}天被放逐，说明当轮自证或拆票型没有压住场上压力。"
        )
    elif _int_value(stats.get("received_vote_count")) > 0 and not alive:
        mistakes.append(
            f"出局前累计被投 {_int_value(stats.get('received_vote_count'))} 票，抗推风险没有被及时化解。"
        )
    elif _int_value(stats.get("received_vote_count")) > 0:
        mistakes.append(
            f"曾累计被投 {_int_value(stats.get('received_vote_count'))} 票，需要更早解释被怀疑的原因。"
        )
    if _int_value(stats.get("speech_count")) <= 0:
        mistakes.append(f"{seat_number}号缺少可复盘的公开发言，赛后只能依赖票型和终局状态判断。")
    if role == Role.WOLF.value and _int_value(stats.get("wolf_chat_count")) <= 0:
        mistakes.append("狼队协同缺少可见狼聊支撑，身份价值主要落在白天表演。")
    if not mistakes:
        mistakes.append(
            f"最低分落在{low_score.get('label')}，主要因为公开证据没有进一步展开到连续推理链。"
        )
    return tuple(_unique_strings(mistakes)[:2])


def _player_suggestions(
    *,
    seat_number: int,
    role: str,
    stats: dict[str, object],
) -> tuple[str, ...]:
    duty = ROLE_DUTY_LABELS.get(role, "角色职责")
    suggestions: list[str] = []
    if _int_value(stats.get("abstain_count")) > 0:
        suggestions.append(
            f"下一局如果{seat_number}号要弃票，先说明保留票的对象和触发改站边的条件。"
        )
    elif _int_value(stats.get("vote_count")) > 0:
        target = _int_value(stats.get("first_vote_target"))
        if target > 0:
            suggestions.append(f"下一局投向{target}号前后，把怀疑点和对方发言原句连起来。")
        else:
            suggestions.append("下一局投票前后把怀疑对象、发言矛盾和票型结果连成闭环。")
    else:
        suggestions.append(f"下一局至少在关键轮次留下一次明确票型，否则{duty}很难被复盘验证。")
    role_suggestion = _role_suggestion(role=role, stats=stats)
    if role_suggestion:
        suggestions.append(role_suggestion)
    return tuple(_unique_strings(suggestions)[:2])


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
            seat_stats.setdefault(
                "first_speech",
                _trim_actor_prefix(str(row.get("text") or ""), actor=actor, limit=72),
            )
            seat_stats.setdefault("first_speech_day", _int_value(row.get("day"), default=1))
    for event in events:
        actor = _int_value(event.get("actor"))
        payload = _payload_dict(event)
        event_type = str(event.get("type") or "")
        if actor > 0:
            seat_stats = stats.setdefault(actor, {})
            if event_type == "speech":
                seat_stats["speech_count"] = _int_value(seat_stats.get("speech_count")) + 1
                text = _string_or_none(payload.get("text"))
                if text:
                    seat_stats.setdefault("first_speech", _trim_text(text, limit=72))
                    seat_stats.setdefault(
                        "first_speech_day", _int_value(event.get("day"), default=1)
                    )
            elif event_type == "last_words":
                seat_stats["last_words_count"] = _int_value(seat_stats.get("last_words_count")) + 1
                text = _string_or_none(payload.get("text"))
                if text:
                    seat_stats.setdefault("last_words", _trim_text(text, limit=72))
            elif event_type == "wolf_chat_message":
                seat_stats["wolf_chat_count"] = _int_value(seat_stats.get("wolf_chat_count")) + 1
                text = _string_or_none(payload.get("text"))
                if text:
                    seat_stats.setdefault("first_wolf_chat", _trim_text(text, limit=56))
            elif event_type == "vote_cast":
                seat_stats["vote_count"] = _int_value(seat_stats.get("vote_count")) + 1
                if payload.get("abstain") is True or payload.get("target") is None:
                    seat_stats["abstain_count"] = _int_value(seat_stats.get("abstain_count")) + 1
                    seat_stats.setdefault(
                        "first_vote",
                        f"第{event.get('day')}天投票阶段选择弃票。",
                    )
                else:
                    target = _int_value(payload.get("target"))
                    seat_stats.setdefault("first_vote_target", target)
                    seat_stats.setdefault(
                        "first_vote",
                        f"第{event.get('day')}天投票给{target}号。",
                    )
                    if target > 0:
                        target_stats = stats.setdefault(target, {})
                        target_stats["received_vote_count"] = (
                            _int_value(target_stats.get("received_vote_count")) + 1
                        )
                        target_stats.setdefault(
                            "first_received_vote",
                            f"第{event.get('day')}天收到{actor}号投票。",
                        )
        if event_type == "exile":
            exiled = _int_value(payload.get("seat"))
            if exiled > 0:
                stats.setdefault(exiled, {})["exiled_day"] = _int_value(event.get("day"), default=1)
        elif event_type == "death_at_night":
            dead = _int_value(payload.get("seat"))
            if dead > 0:
                stats.setdefault(dead, {})["night_death_day"] = _int_value(
                    event.get("day"), default=1
                )
        elif event_type == "day_announce":
            deaths = payload.get("deaths")
            if isinstance(deaths, list):
                for dead_value in deaths:
                    dead = _int_value(dead_value)
                    if dead > 0:
                        stats.setdefault(dead, {}).setdefault(
                            "night_death_day",
                            _int_value(event.get("day"), default=1),
                        )
    return stats


def _evaluation_focus(*, role: str, stats: dict[str, object], alive: bool) -> str:
    vote = _string_or_none(stats.get("first_vote"))
    received = _int_value(stats.get("received_vote_count"))
    if role == Role.WOLF.value and _int_value(stats.get("wolf_chat_count")) > 0:
        return f"狼聊和白天记录共同构成主要证据，夜间协同有 {_int_value(stats.get('wolf_chat_count'))} 次可见发言"
    if vote:
        pressure = f"，同时承受过 {received} 票压力" if received > 0 else ""
        return f"关键可见动作是{vote.rstrip('。')}{pressure}"
    speech = _string_or_none(stats.get("first_speech"))
    if speech:
        return f"主要可复盘材料来自公开发言「{speech}」"
    if received > 0:
        return f"公开记录偏少，但曾被投 {received} 票，场上对其身份存在可见压力"
    return f"公开证据较少，终局{'存活' if alive else '出局'}状态成为主要复盘依据"


def _role_suggestion(*, role: str, stats: dict[str, object]) -> str:
    if role == Role.WOLF.value:
        if _int_value(stats.get("wolf_chat_count")) > 0:
            return "狼人身份下继续把夜间协同和白天站边做成同一条伪装逻辑。"
        return "狼人身份下要在狼聊里留下明确刀口分工，方便白天统一口径。"
    if role == Role.SEER.value:
        return "预言家身份下公开报查验时同步给出警戒对象和投票验证路线。"
    if role == Role.WITCH.value:
        return "女巫身份下白天发言应围绕药水收益做可公开解释，避免只靠身份威慑。"
    if role == Role.GUARD.value:
        return "守卫身份下不要暴露不可公开的守护结果，但要提前准备被推时的自证逻辑。"
    if role == Role.VILLAGER.value:
        if _int_value(stats.get("received_vote_count")) > 0:
            return "平民身份被投后要优先回应票源理由，再给出自己的反推对象。"
        return "平民身份继续把发言、怀疑链和票型连在一起，避免只做态度表态。"
    return "下一局把角色职责和公开票型放在同一条证据链里说明。"


def _day_text(value: object) -> str:
    day = _int_value(value)
    return f"第{day}天" if day > 0 else ""


def _trim_actor_prefix(value: str, *, actor: int, limit: int) -> str:
    text = " ".join(value.split())
    for prefix in (f"{actor}号：", f"{actor}号:"):
        if not text.startswith(prefix):
            continue
        text = text[len(prefix) :]
        break
    return _trim_text(text, limit=limit)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _format_vote_counts(value: object, abstain_count: object = None) -> str:
    if not isinstance(value, dict) or not value:
        if _int_value(abstain_count) > 0:
            return f"有效票为空，弃票 {_int_value(abstain_count)} 票"
        return "暂无有效票"
    parts = [
        f"{seat}号 {count}票"
        for seat, count in sorted(value.items(), key=lambda item: int(item[0]))
    ]
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
        start = prompt.rindex("\n\n{") + 2
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
    return f"{text[: limit - 1]}…"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

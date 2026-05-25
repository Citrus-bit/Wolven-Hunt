from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import ROLE_TO_CAMP, Role, Seat
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider, ProviderResponse


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


class ReviewReportPlayerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: int = Field(ge=1)
    nickname: str
    role: str
    camp: str
    alive: bool
    speech_score: int = Field(ge=0, le=100)
    vote_score: int = Field(ge=0, le=100)
    skill_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    strengths: tuple[str, ...] = ()
    mistakes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()


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

    schema_version: str = "1.0"
    game_id: str
    generated_at: str
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
            "schema_version": "1.0",
            "game_id": game_id,
            "generated_at": _now_iso(),
        }
    )
    return report.model_dump(mode="json")


def build_mock_review_report(
    *,
    game_id: str,
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    narrative_rows: tuple[dict[str, object], ...],
) -> dict[str, Any]:
    winner = str(reveal.get("winner") or "unknown")
    seats = _reveal_seats(reveal)
    players = tuple(
        _mock_player_row(seat, index=index, seat_presentation=seat_presentation)
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
            "reason": "综合表现来自公开发言、票型和技能节点的结构化评估。",
        }
        for index, player in enumerate(
            sorted(players, key=lambda item: _int_value(item.get("overall_score")), reverse=True)
        )
    )
    highlights = tuple(str(item.get("summary")) for item in _reveal_highlights(reveal))
    turning_points = tuple(item for item in highlights if item)[:3]
    speech_rows = [row for row in narrative_rows if row.get("kind") == "speech"]
    key_decisions = (
        {
            "day": _int_value(speech_rows[0].get("day"), default=1) if speech_rows else 1,
            "phase": str(speech_rows[0].get("phase") or "DAY_SPEECH") if speech_rows else "DAY_SPEECH",
            "seq": _int_value(speech_rows[0].get("seq")) if speech_rows else None,
            "title": "首个公开发言定调",
            "analysis": "早期发言决定了后续站边和票型讨论的基础。",
            "impact": "为后续阵营判断提供了可复盘的公开依据。",
        },
        {
            "day": 1,
            "phase": "GAME_END",
            "seq": None,
            "title": "终局身份揭晓",
            "analysis": "身份公开后可对照白天推理、投票和夜间技能收益。",
            "impact": "帮助玩家区分正确判断、误判和信息不足导致的选择。",
        },
    )
    return ReviewReportModel(
        game_id=game_id,
        generated_at=_now_iso(),
        summary=ReviewReportSummaryModel(
            winner=winner,
            verdict="狼人胜利" if winner == "wolf" else "好人胜利",
            turning_points=turning_points or ("终局身份揭晓完成。",),
            overall_assessment="本报告基于观众可见事件、叙事流和终局身份生成, 用于赛后复盘而非游戏事实源。",
        ),
        leaderboard=tuple(ReviewReportLeaderboardItemModel.model_validate(item) for item in leaderboard),
        players=tuple(ReviewReportPlayerModel.model_validate(item) for item in players),
        key_decisions=tuple(ReviewReportDecisionModel.model_validate(item) for item in key_decisions),
        counterfactuals=(
            ReviewReportCounterfactualModel(
                premise="如果关键轮次更早围绕票型集中归因。",
                likely_outcome="好人阵营可能更快缩小狼坑, 狼人阵营也可能被迫调整冲票节奏。",
                lesson="投票和发言需要形成闭环, 单点怀疑应尽快转化为可验证的站边依据。",
            ),
            ReviewReportCounterfactualModel(
                premise="如果神职技能信息在公开发言中表达得更克制。",
                likely_outcome="狼队更难通过发言定位神职, 好人也能保留更多夜间博弈空间。",
                lesson="技能收益不仅来自命中目标, 也来自隐藏信息与公开可信度之间的平衡。",
            ),
        ),
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
        "output_schema": {
            "summary": {
                "winner": "wolf|good",
                "verdict": "中文胜负结论",
                "turning_points": ["关键转折"],
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
                    "reason": "排序理由",
                }
            ],
            "players": [
                {
                    "seat": 1,
                    "nickname": "玩家昵称",
                    "role": "wolf|villager|seer|witch|guard",
                    "camp": "wolf|good",
                    "alive": True,
                    "speech_score": 0,
                    "vote_score": 0,
                    "skill_score": 0,
                    "overall_score": 0,
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
        "所有分数必须是 0-100 的整数; 每名玩家必须都有发言、投票、技能、综合四维评分。"
        "只返回 JSON 对象, 不要 Markdown。\n\n"
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
            ),
            ensure_ascii=False,
        )
        return ProviderResponse(content=content, model=self.model)


def _mock_report_content(
    *,
    reveal: object,
    seat_presentation: dict[int, dict[str, str]],
    narrative_rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    report = build_mock_review_report(
        game_id="mock",
        reveal=reveal if isinstance(reveal, dict) else {},
        seat_presentation=seat_presentation,
        narrative_rows=narrative_rows,
    )
    return {
        key: value
        for key, value in report.items()
        if key not in {"schema_version", "game_id", "generated_at"}
    }


def _mock_player_row(
    seat: dict[str, object],
    *,
    index: int,
    seat_presentation: dict[int, dict[str, str]],
) -> dict[str, object]:
    seat_number = _int_value(seat.get("seat"), default=index + 1)
    role = str(seat.get("role") or "villager")
    camp = _camp_for_role(role)
    speech = max(45, 78 - index * 2)
    vote = max(42, 74 - index)
    skill = _skill_score(role=role, index=index)
    overall = round(speech * 0.4 + vote * 0.3 + skill * 0.3)
    nickname = seat_presentation.get(seat_number, {}).get("nickname") or f"{seat_number}号"
    return {
        "seat": seat_number,
        "nickname": nickname,
        "role": role,
        "camp": camp,
        "alive": bool(seat.get("alive")),
        "speech_score": speech,
        "vote_score": vote,
        "skill_score": skill,
        "overall_score": overall,
        "strengths": ("公开信息利用较稳定。",),
        "mistakes": ("关键轮次可以更早给出明确站边。",),
        "suggestions": ("下一局把发言判断、票型依据和技能收益串成闭环。",),
    }


def _skill_score(*, role: str, index: int) -> int:
    if role == Role.VILLAGER.value:
        return max(40, 62 - index)
    return max(45, 76 - index * 2)


def _camp_for_role(role: str) -> str:
    try:
        return ROLE_TO_CAMP[Role(role)].value
    except ValueError:
        return "unknown"


def _int_value(value: object, *, default: int = 0) -> int:
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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

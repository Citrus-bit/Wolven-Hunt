from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import ProviderResponse
from wolven_hunt.storage import review_dossier as rd
from wolven_hunt.storage import review_report as rr

logger = logging.getLogger(__name__)

GLOBAL_PROMPT_PATH = Path("configs/prompts/zh/review/global.v1.md")
PER_SEAT_PROMPT_PATH = Path("configs/prompts/zh/review/per_seat.v1.md")


class ReviewLLMError(Exception):
    def __init__(self, stage: str, seat: int | None, raw: str) -> None:
        super().__init__(f"review LLM stage={stage} seat={seat} parse failed")
        self.stage = stage
        self.seat = seat
        self.raw = raw


def run_pipeline_sync(
    *,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    seat_agent_kinds: dict[int, str] | None = None,
    settings: Settings,
    provider: Any = None,
) -> dict[str, Any]:
    return asyncio.run(
        run_pipeline(
            game_id=game_id,
            events=events,
            narrative_rows=narrative_rows,
            reveal=reveal,
            seat_presentation=seat_presentation,
            seat_agent_kinds=seat_agent_kinds,
            settings=settings,
            provider=provider,
        )
    )


async def run_pipeline(
    *,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    seat_agent_kinds: dict[int, str] | None = None,
    settings: Settings,
    provider: Any = None,
) -> dict[str, Any]:
    if provider is None:
        provider = rr._review_provider(settings)

    try:
        global_part = await _run_review_stage_with_retries(
            lambda: run_global_stage(
                provider=provider,
                game_id=game_id,
                events=events,
                narrative_rows=narrative_rows,
                reveal=reveal,
                seat_presentation=seat_presentation,
            ),
            settings=settings,
            stage="global",
            seat=None,
        )
    except Exception as exc:
        logger.warning(
            "review global stage exhausted retries, using full mock fallback: %s",
            exc.__class__.__name__,
        )
        return rr.build_mock_review_report(
            game_id=game_id,
            reveal=reveal,
            seat_presentation=seat_presentation,
            seat_agent_kinds=seat_agent_kinds,
            narrative_rows=narrative_rows,
            events=events,
        )

    dossiers = rd.build_dossiers(
        events=events,
        narrative_rows=narrative_rows,
        reveal=reveal,
        seat_presentation=seat_presentation,
        key_decisions=tuple(global_part["key_decisions"]),
        seat_agent_kinds=seat_agent_kinds,
    )
    per_seat_results = await asyncio.gather(
        *(
            _run_review_stage_with_retries(
                lambda dossier=dossier: run_per_seat_stage(
                    provider=provider,
                    game_id=game_id,
                    dossier=dossier,
                    global_summary=global_part["summary"],
                    global_decisions=global_part["key_decisions"],
                ),
                settings=settings,
                stage="per_seat",
                seat=dossier.seat,
            )
            for dossier in dossiers
        ),
        return_exceptions=True,
    )
    return assemble_report(
        game_id=game_id,
        settings=settings,
        dossiers=dossiers,
        per_seat_results=per_seat_results,
        global_part=global_part,
        reveal=reveal,
        seat_presentation=seat_presentation,
        narrative_rows=narrative_rows,
        events=events,
        seat_agent_kinds=seat_agent_kinds,
    )


async def _run_review_stage_with_retries(
    operation: Callable[[], Awaitable[dict[str, Any]]],
    *,
    settings: Settings,
    stage: str,
    seat: int | None,
) -> dict[str, Any]:
    max_retries = settings.review_max_retries
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as exc:
            if attempt >= max_retries:
                raise
            delay = _review_retry_delay(settings, attempt)
            logger.warning(
                "review %s stage failed on attempt %d/%d for seat=%s; retrying in %.1fs: %s",
                stage,
                attempt + 1,
                max_retries + 1,
                "-" if seat is None else seat,
                delay,
                exc.__class__.__name__,
            )
            if delay > 0:
                await asyncio.sleep(delay)
    raise AssertionError("unreachable review retry loop")


def _review_retry_delay(settings: Settings, attempt: int) -> float:
    delays = settings.review_retry_backoff_delays_seconds
    if not delays:
        return 0.0
    return delays[min(attempt, len(delays) - 1)]


async def run_global_stage(
    *,
    provider: Any,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
) -> dict[str, Any]:
    template = _load_template(GLOBAL_PROMPT_PATH)
    payload = {
        "game_id": game_id,
        "spectator_events": list(events),
        "narrative_rows": list(narrative_rows),
        "role_reveal": reveal,
        "seat_presentation": {
            str(seat): presentation for seat, presentation in sorted(seat_presentation.items())
        },
    }
    prompt = f"{template}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    response: ProviderResponse = await provider.acomplete(
        seat=Seat(1),
        phase="REVIEW_GLOBAL",
        prompt=prompt,
        rng=DeterministicRNG(f"review-report:{game_id}:global"),
    )
    return _validate_global_part(_safe_json_load(response.content, stage="global", seat=None))


async def run_per_seat_stage(
    *,
    provider: Any,
    game_id: str,
    dossier: rd.PerSeatDossier,
    global_summary: dict[str, Any],
    global_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    template = _load_template(PER_SEAT_PROMPT_PATH)
    payload = {
        "global_summary": global_summary,
        "global_key_decisions": list(global_decisions),
        "dossier": json.loads(dossier.model_dump_json()),
        "agent_note": _agent_note(dossier),
    }
    prompt = f"{template}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    response: ProviderResponse = await provider.acomplete(
        seat=Seat(dossier.seat),
        phase="REVIEW_PER_SEAT",
        prompt=prompt,
        rng=DeterministicRNG(f"review-report:{game_id}:seat:{dossier.seat}"),
    )
    result = _safe_json_load(response.content, stage="per_seat", seat=dossier.seat)
    rr.ReviewReportPlayerModel.model_validate(
        _player_row_from_result(dossier=dossier, result=result)
    )
    return result


def assemble_report(
    *,
    game_id: str,
    settings: Settings,
    dossiers: tuple[rd.PerSeatDossier, ...],
    per_seat_results: list[dict[str, Any] | BaseException],
    global_part: dict[str, Any],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    narrative_rows: tuple[dict[str, object], ...],
    events: tuple[dict[str, object], ...],
    seat_agent_kinds: dict[int, str] | None = None,
) -> dict[str, Any]:
    mock_full = rr.build_mock_review_report(
        game_id=game_id,
        reveal=reveal,
        seat_presentation=seat_presentation,
        narrative_rows=narrative_rows,
        events=events,
        seat_agent_kinds=seat_agent_kinds,
    )
    mock_players_by_seat = {int(player["seat"]): player for player in mock_full["players"]}

    players: list[dict[str, Any]] = []
    leaderboard_seed: list[dict[str, Any]] = []
    personal_counterfactuals: list[dict[str, Any]] = []
    for dossier, result in zip(dossiers, per_seat_results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "review per-seat stage exhausted retries for seat=%d, using mock row: %s",
                dossier.seat,
                result.__class__.__name__,
            )
            player_row = mock_players_by_seat[dossier.seat]
            players.append(player_row)
            leaderboard_seed.append(_mock_leaderboard_seed(dossier=dossier, player_row=player_row))
            continue
        try:
            player_row = _player_row_from_result(dossier=dossier, result=result)
            rr.ReviewReportPlayerModel.model_validate(player_row)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            logger.warning(
                "review per-seat result invalid for seat=%d, using mock row: %r",
                dossier.seat,
                exc,
            )
            player_row = mock_players_by_seat[dossier.seat]
            players.append(player_row)
            leaderboard_seed.append(_mock_leaderboard_seed(dossier=dossier, player_row=player_row))
            continue
        players.append(player_row)
        personal_counterfactual = result.get("personal_counterfactual")
        if isinstance(personal_counterfactual, dict):
            personal_counterfactuals.append(
                {
                    "premise": str(personal_counterfactual.get("premise") or ""),
                    "likely_outcome": str(
                        personal_counterfactual.get("likely_outcome") or ""
                    ),
                    "lesson": str(personal_counterfactual.get("lesson") or ""),
                    "_anchor_seat": dossier.seat,
                }
            )
        leaderboard_seed.append(
            {
                "seat": dossier.seat,
                "nickname": dossier.nickname,
                "role": dossier.role,
                "camp": dossier.camp,
                "overall_score": int(result["overall_score"]),
                "reason": str(result.get("leaderboard_reason") or "缺少排序理由。"),
            }
        )

    leaderboard = [
        {**item, "rank": index + 1}
        for index, item in enumerate(
            sorted(leaderboard_seed, key=lambda item: item["overall_score"], reverse=True)
        )
    ]
    full = {
        "schema_version": rr.REVIEW_REPORT_SCHEMA_VERSION,
        "game_id": game_id,
        "generated_at": rr._now_iso(),
        "generation_mode": rr._generation_mode(settings),
        "summary": _clean_summary(global_part["summary"]),
        "leaderboard": leaderboard,
        "players": players,
        "key_decisions": [_clean_decision(decision) for decision in global_part["key_decisions"]],
        "counterfactuals": _merge_counterfactuals(
            global_cfs=global_part.get("counterfactuals", []),
            personal_cfs=personal_counterfactuals,
        ),
    }
    return rr.ReviewReportModel.model_validate(full).model_dump(mode="json")


def _safe_json_load(content: str, *, stage: str, seat: int | None) -> dict[str, Any]:
    text = _strip_json_fence(content)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        try:
            loaded = json.loads(_strip_trailing_commas(text))
        except json.JSONDecodeError as exc:
            raise ReviewLLMError(stage=stage, seat=seat, raw=content) from exc
    if not isinstance(loaded, dict):
        raise ReviewLLMError(stage=stage, seat=seat, raw=content)
    return loaded


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _load_template(path: Path) -> str:
    resolved = path
    if not resolved.is_absolute() and not resolved.exists():
        resolved = Path(__file__).resolve().parents[3] / resolved
    if not resolved.exists():
        raise FileNotFoundError(f"review prompt template not found: {resolved}")
    return resolved.read_text(encoding="utf-8").strip()


def _validate_global_part(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _clean_summary(_dict_field(payload, "summary"))
    rr.ReviewReportSummaryModel.model_validate(summary)
    decisions = [_clean_decision(item) | _actors_field(item) for item in _list_field(payload, "key_decisions")]
    for decision in decisions:
        rr.ReviewReportDecisionModel.model_validate(_clean_decision(decision))
    counterfactuals = [
        _clean_counterfactual(item) for item in _list_field(payload, "counterfactuals")
    ]
    for counterfactual in counterfactuals:
        rr.ReviewReportCounterfactualModel.model_validate(counterfactual)
    return {
        "summary": summary,
        "key_decisions": decisions,
        "counterfactuals": counterfactuals,
    }


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ReviewLLMError(stage="global", seat=None, raw=json.dumps(payload, ensure_ascii=False))
    return value


def _list_field(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ReviewLLMError(stage="global", seat=None, raw=json.dumps(payload, ensure_ascii=False))
    return value


def _clean_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "winner": str(summary.get("winner") or "unknown"),
        "verdict": str(summary.get("verdict") or ""),
        "turning_points": tuple(str(item) for item in summary.get("turning_points") or ()),
        "overall_assessment": str(summary.get("overall_assessment") or ""),
    }


def _clean_decision(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "day": _int_value(decision.get("day")),
        "phase": str(decision.get("phase") or ""),
        "seq": _int_or_none(decision.get("seq")),
        "title": str(decision.get("title") or ""),
        "analysis": str(decision.get("analysis") or ""),
        "impact": str(decision.get("impact") or ""),
    }


def _actors_field(decision: dict[str, Any]) -> dict[str, Any]:
    actors = decision.get("actors_involved")
    return {"actors_involved": actors} if isinstance(actors, dict) else {}


def _clean_counterfactual(counterfactual: dict[str, Any]) -> dict[str, Any]:
    return {
        "premise": str(counterfactual.get("premise") or ""),
        "likely_outcome": str(counterfactual.get("likely_outcome") or ""),
        "lesson": str(counterfactual.get("lesson") or ""),
    }


def _player_row_from_result(
    *, dossier: rd.PerSeatDossier, result: dict[str, Any]
) -> dict[str, Any]:
    return {
        "seat": dossier.seat,
        "nickname": dossier.nickname,
        "role": dossier.role,
        "camp": dossier.camp,
        "alive": dossier.lifecycle.alive_at_end,
        "scores": result["scores"],
        "overall_score": int(result["overall_score"]),
        "evaluation": str(result["evaluation"]),
        "evidence": tuple(str(item) for item in result.get("evidence", ())),
        "strengths": tuple(str(item) for item in result.get("strengths", ())),
        "mistakes": tuple(str(item) for item in result.get("mistakes", ())),
        "suggestions": tuple(str(item) for item in result.get("suggestions", ())),
    }


def _mock_leaderboard_seed(
    *, dossier: rd.PerSeatDossier, player_row: dict[str, Any]
) -> dict[str, Any]:
    return {
        "seat": dossier.seat,
        "nickname": dossier.nickname,
        "role": dossier.role,
        "camp": dossier.camp,
        "overall_score": int(player_row["overall_score"]),
        "reason": rr._leaderboard_reason(player_row, agent_type=dossier.agent_type),
    }


def _agent_note(dossier: rd.PerSeatDossier) -> str:
    if dossier.agent_type == "human":
        return "该座位是真人玩家。复盘措辞应直接面向真人玩家, 避免把该座位称为模型。"
    if dossier.agent_type == "mock":
        return "该座位由 mock agent 托管。"
    return "该座位由 LLM agent 托管。"


def _merge_counterfactuals(
    *,
    global_cfs: list[dict[str, Any]],
    personal_cfs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for counterfactual in [*global_cfs, *personal_cfs]:
        cleaned = _clean_counterfactual(counterfactual)
        premise = cleaned["premise"].strip()
        if not premise or premise in seen:
            continue
        seen.add(premise)
        merged.append(cleaned)
    return sorted(merged, key=_counterfactual_sort_key)[:5]


def _counterfactual_sort_key(counterfactual: dict[str, Any]) -> tuple[int, int, str]:
    premise = str(counterfactual.get("premise") or "")
    anchored = 0 if re.search(r"\d+\s*号", premise) else 1
    has_node = 0 if re.search(r"D\d+|DAY_|NIGHT_|第\d+", premise) else 1
    return (anchored, has_node, premise)


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None

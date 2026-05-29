from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wolven_hunt.config.settings import Settings
from wolven_hunt.referee.visibility import filter_spectator_events
from wolven_hunt.storage.disk import atomic_write_json
from wolven_hunt.storage.jsonl import read_events_jsonl
from wolven_hunt.storage.narrative import event_to_narrative
from wolven_hunt.storage.review_report import REVIEW_REPORT_SCHEMA_VERSION, generate_review_report

from .axes import AXES


@dataclass(frozen=True, slots=True)
class AxisScore:
    axis: str
    average: float
    sample_count: int
    mistakes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    counterfactuals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowScore:
    game_ids: tuple[str, ...]
    axis_scores: dict[str, AxisScore]
    fallback_count: int
    raw_response_count: int
    skipped_game_ids: tuple[str, ...] = ()

    @property
    def fallback_rate(self) -> float:
        return self.fallback_count / max(1, self.raw_response_count)

    def to_json(self) -> dict[str, object]:
        return {
            "game_ids": list(self.game_ids),
            "skipped_game_ids": list(self.skipped_game_ids),
            "fallback_count": self.fallback_count,
            "raw_response_count": self.raw_response_count,
            "fallback_rate": self.fallback_rate,
            "axis_scores": {
                key: {
                    "average": value.average,
                    "sample_count": value.sample_count,
                    "mistakes": list(value.mistakes),
                    "suggestions": list(value.suggestions),
                    "counterfactuals": list(value.counterfactuals),
                }
                for key, value in sorted(self.axis_scores.items())
            },
        }


def score_window(
    *,
    runs_dir: Path,
    game_ids: tuple[str, ...],
    settings: Settings,
) -> WindowScore:
    reports: list[dict[str, object]] = []
    skipped: list[str] = []
    fallback_count = 0
    raw_response_count = 0
    for game_id in game_ids:
        root = runs_dir / game_id
        report = ensure_review_report(root=root, game_id=game_id, settings=settings)
        if report is None:
            skipped.append(game_id)
            continue
        reports.append(report)
        fallback_count += _event_count(root / "events.jsonl", "agent_fallback_triggered")
        raw_response_count += _jsonl_count(root / "raw_responses.jsonl")
    return WindowScore(
        game_ids=tuple(game_id for game_id in game_ids if game_id not in skipped),
        axis_scores=_axis_scores(reports),
        fallback_count=fallback_count,
        raw_response_count=raw_response_count,
        skipped_game_ids=tuple(skipped),
    )


def ensure_review_report(
    *,
    root: Path,
    game_id: str,
    settings: Settings,
) -> dict[str, object] | None:
    report_path = root / "review_report.json"
    if report_path.exists():
        report = _read_json_object(report_path)
        if report.get("schema_version") == REVIEW_REPORT_SCHEMA_VERSION:
            return report
    manifest = _read_json_object(root / "manifest.json")
    if not manifest.get("ended_at") or not (root / "events.jsonl").exists():
        return None
    events = read_events_jsonl(root / "events.jsonl")
    reveal = _reveal_from_disk_or_events(root, events)
    if reveal is None:
        return None
    spectator_events = tuple(
        event.model_dump(mode="json") for event in filter_spectator_events(events)
    )
    report = generate_review_report(
        game_id=game_id,
        events=spectator_events,
        narrative_rows=_narrative_rows(root=root, events=events),
        reveal=reveal,
        seat_presentation=_manifest_seat_presentation(manifest),
        settings=settings,
    )
    atomic_write_json(report_path, report)
    return report


def weakest_axis(score: WindowScore) -> AxisScore:
    candidates = [
        axis_score
        for axis in AXES
        if (axis_score := score.axis_scores.get(axis.key)) is not None
        and axis_score.sample_count > 0
    ]
    if not candidates:
        raise ValueError("no scored evolution axes in window")
    return min(
        candidates,
        key=lambda item: (
            item.average,
            -item.sample_count,
            _axis_order(item.axis),
        ),
    )


def _axis_scores(reports: list[dict[str, object]]) -> dict[str, AxisScore]:
    counterfactuals = tuple(_counterfactual_text(report) for report in reports)
    result: dict[str, AxisScore] = {}
    for axis in AXES:
        values: list[int] = []
        mistakes: list[str] = []
        suggestions: list[str] = []
        for report in reports:
            for player in _players_for_role(report, axis.role.value):
                value = _score_value(player, axis.score_key)
                if value is not None:
                    values.append(value)
                mistakes.extend(_str_items(player.get("mistakes")))
                suggestions.extend(_str_items(player.get("suggestions")))
        if values:
            result[axis.key] = AxisScore(
                axis=axis.key,
                average=sum(values) / len(values),
                sample_count=len(values),
                mistakes=tuple(dict.fromkeys(mistakes))[:12],
                suggestions=tuple(dict.fromkeys(suggestions))[:12],
                counterfactuals=tuple(item for item in counterfactuals if item)[:8],
            )
    return result


def _players_for_role(report: dict[str, object], role: str) -> tuple[dict[str, object], ...]:
    players = report.get("players")
    if not isinstance(players, list):
        return ()
    return tuple(
        player
        for player in players
        if isinstance(player, dict) and str(player.get("role")) == role
    )


def _score_value(player: dict[str, object], score_key: str) -> int | None:
    scores = player.get("scores")
    if not isinstance(scores, list):
        return None
    for score in scores:
        if not isinstance(score, dict):
            continue
        if score.get("key") == score_key and isinstance(score.get("value"), int):
            return int(score["value"])
    return None


def _event_count(path: Path, event_type: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for event in read_events_jsonl(path) if event.type.value == event_type)


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _reveal_from_disk_or_events(root: Path, events: tuple[Any, ...]) -> dict[str, object] | None:
    reveal = _read_json_object(root / "final_reveal.json")
    if reveal:
        return reveal
    for event in reversed(events):
        if event.type.value == "role_reveal":
            return dict(event.payload)
    return None


def _narrative_rows(*, root: Path, events: tuple[Any, ...]) -> tuple[dict[str, object], ...]:
    narrative_path = root / "narrative.jsonl"
    rows = _read_jsonl_objects(narrative_path)
    if rows:
        return rows
    generated: list[dict[str, object]] = []
    for event in events:
        row = event_to_narrative(event)
        if row is not None:
            generated.append(row.to_dict())
    return tuple(generated)


def _read_jsonl_objects(path: Path) -> tuple[dict[str, object], ...]:
    if not path.exists():
        return ()
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return tuple(rows)


def _manifest_seat_presentation(data: dict[str, object]) -> dict[int, dict[str, str]]:
    raw = data.get("seat_presentation")
    if not isinstance(raw, dict):
        return {}
    result: dict[int, dict[str, str]] = {}
    for seat, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            seat_number = int(seat)
        except (TypeError, ValueError):
            continue
        result[seat_number] = {
            "nickname": str(value.get("nickname") or ""),
            "icon_path": str(value.get("icon_path") or ""),
        }
    return result


def _str_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _counterfactual_text(report: dict[str, object]) -> str:
    rows = report.get("counterfactuals")
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = " / ".join(
            str(row.get(key) or "")
            for key in ("premise", "likely_outcome", "lesson")
            if row.get(key)
        )
        if text:
            parts.append(text)
    return "\n".join(parts)


def _axis_order(axis_key: str) -> int:
    for index, axis in enumerate(AXES):
        if axis.key == axis_key:
            return index
    return 999

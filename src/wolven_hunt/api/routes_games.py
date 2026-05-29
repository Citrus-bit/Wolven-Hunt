from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from starlette.responses import StreamingResponse

from wolven_hunt.api.deps import get_registry
from wolven_hunt.api.schemas import (
    AckRequest,
    CreateGameRequest,
    CreateGameResponse,
    GameListItem,
    GameSummaryResponse,
    ModelTestRequest,
    ModelTestResponse,
    NarrativeRow,
    ReplayRequest,
    ReviewReportResponse,
    RoleRevealResponse,
    SpectatorEffect,
    TextActionRequest,
)
from wolven_hunt.api.sse import sse_response
from wolven_hunt.core.events import Event
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider
from wolven_hunt.llm.thinking import thinking_extra_body, thinking_reasoning_effort
from wolven_hunt.orchestration.runtime import GameRegistry, GameSession
from wolven_hunt.referee.reveal import build_role_reveal_payload
from wolven_hunt.referee.visibility import filter_spectator_events
from wolven_hunt.storage.jsonl import read_events_jsonl
from wolven_hunt.storage.narrative import event_to_narrative
from wolven_hunt.storage.replay import replay_deterministic, replay_resimulate
from wolven_hunt.storage.review_report import REVIEW_REPORT_SCHEMA_VERSION, generate_review_report
from wolven_hunt.storage.spectator_effects import events_to_spectator_effects

router = APIRouter()
REGISTRY_DEP = Depends(get_registry)
LAST_EVENT_ID_HEADER = Header(default=None, alias="Last-Event-ID")
LAST_EVENT_ID_QUERY = Query(default=None, alias="last_event_id")
LOCAL_LOBBY_ASSET_RE = re.compile(r"^/assets/lobby/[A-Za-z0-9_.-]+$")


@router.post("/games", response_model=CreateGameResponse)
async def create_game(
    request: CreateGameRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> CreateGameResponse:
    session = await registry.create_game(
        config_path=Path(request.config_path),
        seed=request.seed,
        agent_specs=request.agents,
        pacing=request.pacing,
        start_paused=request.start_paused,
        seat_presentation={
            seat: presentation.model_dump(mode="json")
            for seat, presentation in request.seat_presentation.items()
        },
        evolution_enabled=request.evolution_enabled,
    )
    return CreateGameResponse(game_id=session.game_id)


@router.get("/games", response_model=tuple[GameListItem, ...])
def list_games(registry: GameRegistry = REGISTRY_DEP) -> tuple[GameListItem, ...]:
    items: list[GameListItem] = []
    session_ids = set(registry.game_ids())
    for session in registry.sessions():
        items.append(_list_item_from_session(session))
    runs_dir = registry.settings.runs_dir
    if runs_dir.exists():
        for manifest_path in runs_dir.glob("*/manifest.json"):
            game_id = manifest_path.parent.name
            if game_id in session_ids:
                continue
            items.append(_list_item_from_manifest(game_id, manifest_path))
    return tuple(
        sorted(
            items,
            key=lambda item: item.started_at or "",
            reverse=True,
        )
    )


@router.get("/games/{game_id}", response_model=GameSummaryResponse)
def get_game(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> GameSummaryResponse:
    session = registry.get(game_id)
    if session is not None:
        return _summary(session)
    return _summary_from_manifest(registry, game_id)


@router.get("/games/{game_id}/events")
def get_events(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> tuple[dict[str, object], ...]:
    session = registry.get(game_id)
    if session is not None:
        return session.spectator_events()
    events_path = registry.settings.runs_dir / game_id / "events.jsonl"
    if not events_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    events = filter_spectator_events(read_events_jsonl(events_path))
    return tuple(event.model_dump(mode="json") for event in events)


@router.get("/games/{game_id}/narrative", response_model=tuple[NarrativeRow, ...])
def get_narrative(
    game_id: str,
    after: int = 0,
    registry: GameRegistry = REGISTRY_DEP,
) -> tuple[dict[str, object], ...]:
    session = registry.get(game_id)
    if session is not None:
        return session.narrative_rows_after(after)
    root = registry.settings.runs_dir / game_id
    events_path = root / "events.jsonl"
    if not events_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    rows = _narrative_rows_from_disk(root, read_events_jsonl(events_path))
    return tuple(row for row in rows if _row_seq(row) > after)


@router.get("/games/{game_id}/effects", response_model=tuple[SpectatorEffect, ...])
def get_effects(
    game_id: str,
    after: int = 0,
    registry: GameRegistry = REGISTRY_DEP,
) -> tuple[dict[str, object], ...]:
    session = registry.get(game_id)
    if session is not None:
        return session.effect_rows_after(after)
    events_path = registry.settings.runs_dir / game_id / "events.jsonl"
    if not events_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    return events_to_spectator_effects(read_events_jsonl(events_path), after=after)


@router.get("/games/{game_id}/reveal", response_model=RoleRevealResponse)
def get_reveal(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    session = registry.get(game_id)
    if session is None:
        return _reveal_from_disk(registry, game_id)
    if session.state.winner is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_finished", "message": "game is not finished"},
        )
    if session.final_reveal is not None:
        return session.final_reveal
    if session.store.final_reveal_path.exists():
        data = json.loads(session.store.final_reveal_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    payload = build_role_reveal_payload(session.state, session.event_log.events)
    session.final_reveal = payload
    session.store.write_final_reveal(payload)
    return payload


@router.get("/games/{game_id}/review-report", response_model=ReviewReportResponse)
def get_review_report(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    path = registry.settings.runs_dir / game_id / "review_report.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "report_not_generated", "message": "review report is not generated"},
        )
    data = _read_json_object(path)
    if not _is_current_review_report(data):
        raise HTTPException(
            status_code=404,
            detail={"code": "report_not_generated", "message": "review report is not generated"},
        )
    return data


@router.post("/games/{game_id}/review-report", response_model=ReviewReportResponse)
def generate_review_report_route(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    path = registry.settings.runs_dir / game_id / "review_report.json"
    if path.exists():
        data = _read_json_object(path)
        if _is_current_review_report(data):
            return data
    session = registry.get(game_id)
    if session is not None:
        if session.state.winner is None or session.status != "finished":
            raise HTTPException(
                status_code=404,
                detail={"code": "game_not_finished", "message": "game is not finished"},
            )
        reveal = _ensure_session_reveal(session)
        report = _generate_review_report_or_raise(
            game_id=game_id,
            events=session.spectator_events(),
            narrative_rows=session.narrative_rows(),
            reveal=reveal,
            seat_presentation=session.seat_presentation,
            registry=registry,
        )
        session.store.write_review_report(report)
        return report

    root = registry.settings.runs_dir / game_id
    manifest_path = root / "manifest.json"
    events_path = root / "events.jsonl"
    if not manifest_path.exists() or not events_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    manifest = _read_manifest(manifest_path)
    if _string_or_none(manifest.get("ended_at")) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_finished", "message": "game is not finished"},
        )
    raw_events = read_events_jsonl(events_path)
    reveal = _reveal_from_disk(registry, game_id)
    report = _generate_review_report_or_raise(
        game_id=game_id,
        events=tuple(
            event.model_dump(mode="json") for event in filter_spectator_events(raw_events)
        ),
        narrative_rows=_narrative_rows_from_disk(root, raw_events),
        reveal=reveal,
        seat_presentation=_manifest_seat_presentation(manifest),
        registry=registry,
    )
    from wolven_hunt.storage.disk import atomic_write_json

    atomic_write_json(path, report)
    return report


@router.get("/games/{game_id}/stream")
def stream_events(
    game_id: str,
    last_event_id_query: str | None = LAST_EVENT_ID_QUERY,
    last_event_id: str | None = LAST_EVENT_ID_HEADER,
    registry: GameRegistry = REGISTRY_DEP,
) -> StreamingResponse:
    return sse_response(
        _require_session(registry, game_id),
        last_event_id=last_event_id or last_event_id_query,
    )


@router.post("/games/{game_id}/run", response_model=GameSummaryResponse)
def run_game_route(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> GameSummaryResponse:
    _require_session(registry, game_id)
    return _summary(registry.run(game_id))


@router.post("/games/{game_id}/pause", response_model=GameSummaryResponse)
def pause_game(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> GameSummaryResponse:
    _require_session(registry, game_id)
    return _summary(registry.pause(game_id))


@router.post("/games/{game_id}/resume", response_model=GameSummaryResponse)
def resume_game(
    game_id: str,
    registry: GameRegistry = REGISTRY_DEP,
) -> GameSummaryResponse:
    _require_session(registry, game_id)
    return _summary(registry.resume(game_id))


@router.post("/games/{game_id}/replay")
def replay_game(
    game_id: str,
    request: ReplayRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> tuple[dict[str, object], ...]:
    session = _require_session(registry, game_id)
    if request.mode == "deterministic":
        events = replay_deterministic(read_events_jsonl(session.store.events_path))
    elif request.mode == "resimulate":
        events = replay_resimulate(session.store.events_path, session.store.raw_responses_path)
    else:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_replay_mode", "message": request.mode},
        )
    return tuple(event.model_dump(mode="json") for event in events)


@router.post("/games/{game_id}/speech")
def submit_speech(
    game_id: str,
    request: TextActionRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    rejection = registry.submit_speech(game_id=game_id, seat=Seat(request.seat), text=request.text)
    if rejection is not None:
        _raise_reject(rejection.rule_id, rejection.message)
    return {"ok": True}


@router.post("/games/{game_id}/wolf_chat")
def submit_wolf_chat(
    game_id: str,
    request: TextActionRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    rejection = registry.submit_wolf_chat(
        game_id=game_id, seat=Seat(request.seat), text=request.text
    )
    if rejection is not None:
        _raise_reject(rejection.rule_id, rejection.message)
    return {"ok": True}


@router.post("/games/{game_id}/ack")
def ack_game(
    game_id: str,
    request: AckRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> dict[str, object]:
    session = _require_session(registry, game_id)
    session.ack(
        phase=request.phase,
        event=request.event,
        client_event_id=request.client_event_id,
    )
    return {"ok": True}


@router.post("/models/test", response_model=ModelTestResponse)
def test_model(request: ModelTestRequest) -> ModelTestResponse:
    try:
        provider = (
            LiteLLMProvider(
                model=request.model,
                api_key=request.api_key,
                base_url=request.base_url,
                timeout_seconds=request.timeout_seconds,
                extra_body=thinking_extra_body(request.model, enabled=request.thinking_enabled),
                reasoning_effort=thinking_reasoning_effort(
                    request.model,
                    enabled=request.thinking_enabled,
                ),
            )
            if request.provider == "litellm"
            else MockLLMProvider(model=request.model)
        )
        provider.complete(
            seat=Seat(1),
            phase="MODEL_TEST",
            prompt='Return a minimal JSON object such as {"ok": true}.',
            rng=DeterministicRNG("model-test"),
        )
    except Exception as exc:
        return ModelTestResponse(
            ok=False,
            message=_sanitize_model_test_error(exc, api_key=request.api_key),
        )
    return ModelTestResponse(ok=True)


def _sanitize_model_test_error(exc: Exception, *, api_key: str) -> str:
    message = str(exc) or exc.__class__.__name__
    if api_key:
        message = message.replace(api_key, "[redacted]")
    message = re.sub(
        r"(?i)\b(api[_-]?key|authorization|bearer)(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[redacted]",
        message,
    )
    message = re.sub(r"\b(?:sk|tp)-[A-Za-z0-9_-]{8,}\b", "[redacted]", message)
    message = " ".join(message.split())
    if not message:
        message = "模型测试失败"
    return message[:200]


def _require_session(registry: GameRegistry, game_id: str) -> GameSession:
    try:
        return registry.require(game_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        ) from exc


def _summary(session: GameSession) -> GameSummaryResponse:
    phase, day = _published_phase_and_day(session)
    return GameSummaryResponse(
        game_id=session.game_id,
        status=session.status,
        winner=None if session.state.winner is None else session.state.winner.value,
        day=day,
        phase=phase,
        event_count=len(session.event_log.events),
        timings=session.config.rule_set.timings.model_dump(mode="json"),
        seat_presentation=session.seat_presentation,
    )


def _published_phase_and_day(session: GameSession) -> tuple[str, int]:
    events = session.event_log.events
    if not events:
        return session.state.phase, session.state.day
    last_event = events[-1]
    for event in reversed(events):
        if event.type.value == "phase_enter":
            return str(event.payload.get("phase", event.phase)), event.day
    return last_event.phase, last_event.day


def _summary_from_manifest(
    registry: GameRegistry,
    game_id: str,
) -> GameSummaryResponse:
    root = registry.settings.runs_dir / game_id
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    manifest = _read_manifest(manifest_path)
    events_path = root / "events.jsonl"
    events = read_events_jsonl(events_path) if events_path.exists() else ()
    last_event = events[-1] if events else None
    ended_at = _string_or_none(manifest.get("ended_at"))
    return GameSummaryResponse(
        game_id=game_id,
        status="finished" if ended_at else "unknown",
        winner=_string_or_none(manifest.get("winner")),
        day=last_event.day if last_event is not None else 0,
        phase=last_event.phase if last_event is not None else "UNKNOWN",
        event_count=len(events),
        timings={},
        seat_presentation=_manifest_seat_presentation(manifest),
    )


def _list_item_from_session(session: GameSession) -> GameListItem:
    return GameListItem(
        game_id=session.game_id,
        started_at=session.started_at,
        ended_at=None
        if not session.store.manifest_path.exists()
        else _manifest_value(session.store.manifest_path, "ended_at"),
        winner=None if session.state.winner is None else session.state.winner.value,
        status=session.status,
        event_count=len(session.event_log.events),
    )


def _list_item_from_manifest(game_id: str, manifest_path: Path) -> GameListItem:
    data = _read_json_object(manifest_path)
    event_count = 0
    events_path = manifest_path.with_name("events.jsonl")
    if events_path.exists():
        event_count = sum(
            1 for line in events_path.read_text(encoding="utf-8").splitlines() if line
        )
    ended_at = _string_or_none(data.get("ended_at"))
    return GameListItem(
        game_id=game_id,
        started_at=_string_or_none(data.get("started_at")),
        ended_at=ended_at,
        winner=_string_or_none(data.get("winner")),
        status="finished" if ended_at else "unknown",
        event_count=event_count,
    )


def _reveal_from_disk(registry: GameRegistry, game_id: str) -> dict[str, object]:
    root = registry.settings.runs_dir / game_id
    if not root.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "game_not_found", "message": game_id},
        )
    final_reveal_path = root / "final_reveal.json"
    if final_reveal_path.exists():
        data = _read_json_object(final_reveal_path)
        if data:
            return data
    events_path = root / "events.jsonl"
    if events_path.exists():
        for event in reversed(read_events_jsonl(events_path)):
            if event.type.value == "role_reveal":
                return dict(event.payload)
    raise HTTPException(
        status_code=404,
        detail={"code": "game_not_finished", "message": "game is not finished"},
    )


def _ensure_session_reveal(session: GameSession) -> dict[str, object]:
    if session.final_reveal is not None:
        return session.final_reveal
    if session.store.final_reveal_path.exists():
        data = _read_json_object(session.store.final_reveal_path)
        if data:
            session.final_reveal = data
            return data
    payload = build_role_reveal_payload(session.state, session.event_log.events)
    session.final_reveal = payload
    session.store.write_final_reveal(payload)
    return payload


def _generate_review_report_or_raise(
    *,
    game_id: str,
    events: tuple[dict[str, object], ...],
    narrative_rows: tuple[dict[str, object], ...],
    reveal: dict[str, object],
    seat_presentation: dict[int, dict[str, str]],
    registry: GameRegistry,
) -> dict[str, object]:
    try:
        return generate_review_report(
            game_id=game_id,
            events=events,
            narrative_rows=narrative_rows,
            reveal=reveal,
            seat_presentation=seat_presentation,
            settings=registry.settings,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "review_report_generation_failed",
                "message": _sanitize_model_test_error(
                    exc,
                    api_key=registry.settings.review_api_key,
                ),
            },
        ) from exc


def _narrative_rows_from_disk(
    root: Path,
    events: tuple[Event, ...],
) -> tuple[dict[str, object], ...]:
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


def _row_seq(row: dict[str, object]) -> int:
    seq = row.get("seq")
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str):
        try:
            return int(seq)
        except ValueError:
            return 0
    return 0


def _read_manifest(path: Path) -> dict[str, object]:
    return _read_json_object(path)


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_current_review_report(data: dict[str, object]) -> bool:
    return data.get("schema_version") == REVIEW_REPORT_SCHEMA_VERSION


def _manifest_seat_presentation(data: dict[str, object]) -> dict[int, dict[str, str]]:
    raw = data.get("seat_presentation")
    if not isinstance(raw, dict):
        return {}
    presentation: dict[int, dict[str, str]] = {}
    for seat_key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            seat = int(seat_key)
        except (TypeError, ValueError):
            continue
        nickname = value.get("nickname")
        icon_path = value.get("icon_path")
        if (
            isinstance(nickname, str)
            and 0 < len(nickname) <= 32
            and isinstance(icon_path, str)
            and LOCAL_LOBBY_ASSET_RE.fullmatch(icon_path)
        ):
            presentation[seat] = {"nickname": nickname, "icon_path": icon_path}
    return presentation


def _manifest_value(path: Path, key: str) -> str | None:
    data = _read_json_object(path)
    return _string_or_none(data.get(key))


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _raise_reject(rule_id: str, message: str) -> None:
    raise HTTPException(
        status_code=422,
        detail={"code": "action_rejected", "message": message, "details": {"rule_id": rule_id}},
    )

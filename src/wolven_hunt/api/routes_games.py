from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
    RoleRevealResponse,
    SpectatorEffect,
    TextActionRequest,
)
from wolven_hunt.api.sse import sse_response
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider
from wolven_hunt.orchestration.runtime import GameRegistry, GameSession
from wolven_hunt.referee.reveal import build_role_reveal_payload
from wolven_hunt.referee.visibility import filter_spectator_events
from wolven_hunt.storage.jsonl import read_events_jsonl
from wolven_hunt.storage.replay import replay_deterministic, replay_resimulate
from wolven_hunt.storage.spectator_effects import events_to_spectator_effects

router = APIRouter()
REGISTRY_DEP = Depends(get_registry)
LAST_EVENT_ID_HEADER = Header(default=None, alias="Last-Event-ID")
LAST_EVENT_ID_QUERY = Query(default=None, alias="last_event_id")


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
    session = _require_session(registry, game_id)
    return _summary(session)


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
    return _require_session(registry, game_id).narrative_rows_after(after)


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
    session = _require_session(registry, game_id)
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
                extra_body=_model_test_extra_body(
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


def _model_test_extra_body(model: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {}
    normalized = model.strip().lower()
    if normalized.startswith("qwen"):
        return {"enable_thinking": True}
    if normalized.startswith(("kimi", "mimo", "deepseek", "glm", "doubao")):
        return {"thinking": {"type": "enabled"}}
    if normalized.startswith("hy3"):
        return {
            "chat_template_kwargs": {
                "thinking": True,
                "reasoning_effort": "medium",
            }
        }
    if normalized.startswith("minimax"):
        return {"reasoning_effort": "medium"}
    return {}


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
    return GameSummaryResponse(
        game_id=session.game_id,
        status=session.status,
        winner=None if session.state.winner is None else session.state.winner.value,
        day=session.state.day,
        phase=session.state.phase,
        event_count=len(session.event_log.events),
        timings=session.config.rule_set.timings.model_dump(mode="json"),
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
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
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


def _manifest_value(path: Path, key: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return _string_or_none(data.get(key))


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _raise_reject(rule_id: str, message: str) -> None:
    raise HTTPException(
        status_code=422,
        detail={"code": "action_rejected", "message": message, "details": {"rule_id": rule_id}},
    )

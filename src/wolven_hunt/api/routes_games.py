from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from starlette.responses import StreamingResponse

from wolven_hunt.api.deps import get_registry
from wolven_hunt.api.schemas import (
    CreateGameRequest,
    CreateGameResponse,
    GameSummaryResponse,
    ReplayRequest,
    TextActionRequest,
)
from wolven_hunt.api.sse import sse_response
from wolven_hunt.core.seat import Seat
from wolven_hunt.orchestration.runtime import GameRegistry, GameSession
from wolven_hunt.storage.jsonl import read_events_jsonl
from wolven_hunt.storage.replay import replay_deterministic, replay_resimulate

router = APIRouter()
REGISTRY_DEP = Depends(get_registry)
LAST_EVENT_ID_HEADER = Header(default=None, alias="Last-Event-ID")


@router.post("/games", response_model=CreateGameResponse)
async def create_game(
    request: CreateGameRequest,
    registry: GameRegistry = REGISTRY_DEP,
) -> CreateGameResponse:
    session = await registry.create_game(
        config_path=Path(request.config_path),
        seed=request.seed,
        agent_specs=request.agents,
    )
    return CreateGameResponse(game_id=session.game_id)


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
    return _require_session(registry, game_id).spectator_events()


@router.get("/games/{game_id}/stream")
def stream_events(
    game_id: str,
    last_event_id: str | None = LAST_EVENT_ID_HEADER,
    registry: GameRegistry = REGISTRY_DEP,
) -> StreamingResponse:
    return sse_response(_require_session(registry, game_id), last_event_id=last_event_id)


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
    )


def _raise_reject(rule_id: str, message: str) -> None:
    raise HTTPException(
        status_code=422,
        detail={"code": "action_rejected", "message": message, "details": {"rule_id": rule_id}},
    )

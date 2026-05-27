from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from wolven_hunt.orchestration.runtime import GameSession

HEARTBEAT_SECONDS = 30.0


def sse_response(session: GameSession, *, last_event_id: str | None) -> StreamingResponse:
    start_after = _parse_last_event_id(last_event_id) or 0
    if session.is_terminal() and start_after > session.latest_event_seq():
        raise HTTPException(status_code=410, detail={"code": "event_cursor_gone"})

    async def stream() -> AsyncIterator[str]:
        cursor = start_after
        yield "event: stream_ready\ndata: {}\n\n"
        while True:
            events = session.raw_events_after(cursor)
            if events:
                for raw_event in events:
                    event_seq = raw_event.seq
                    projections = _projections_for_seq(session, event_seq)
                    for index, (event_name, payload) in enumerate(projections):
                        yield _format_event(
                            event_name,
                            event_seq,
                            payload,
                            include_id=index == len(projections) - 1,
                        )
                    cursor = event_seq
                continue
            if session.is_terminal():
                yield "event: heartbeat\ndata: {}\n\n"
                break
            try:
                await session.wait_for_event(timeout_seconds=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _parse_last_event_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_last_event_id"}) from exc


def _format_event(
    event_name: str,
    seq: int,
    data: object,
    *,
    include_id: bool = True,
) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    id_line = f"id: {seq}\n" if include_id else ""
    return f"event: {event_name}\n{id_line}data: {encoded}\n\n"


def _projections_for_seq(session: GameSession, seq: int) -> tuple[tuple[str, object], ...]:
    projections: list[tuple[str, object]] = []
    event = session.spectator_event_for_seq(seq)
    if event is not None:
        projections.append(("game_event", event))
    narrative = _narrative_for_seq(session, seq)
    if narrative is not None:
        projections.append(("narrative_row", narrative))
    projections.extend(("spectator_effect", effect) for effect in session.effect_rows_for_seq(seq))
    return tuple(projections)


def _event_seq(event: dict[str, object]) -> int:
    seq = event.get("seq")
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str):
        return int(seq)
    raise HTTPException(status_code=500, detail={"code": "event_seq_missing"})


def _narrative_for_seq(session: GameSession, seq: int) -> dict[str, object] | None:
    for row in session.narrative_rows_after(seq - 1):
        if _event_seq(row) == seq:
            return row
    return None

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
        while True:
            events = session.spectator_events_after(cursor)
            if events:
                for event in events:
                    cursor = _event_seq(event)
                    yield _format_event("game_event", cursor, event)
                    narrative = _narrative_for_seq(session, cursor)
                    if narrative is not None:
                        yield _format_event("narrative_row", cursor, narrative)
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


def _format_event(event_name: str, seq: int, data: object) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\nid: {seq}\ndata: {encoded}\n\n"


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

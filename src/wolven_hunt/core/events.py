from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from wolven_hunt.core.ids import EventId, GameId

JsonDict = dict[str, Any]
DRAFT_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


class EventType(StrEnum):
    GAME_START = "game_start"
    PHASE_ENTER = "phase_enter"
    PHASE_EXIT = "phase_exit"
    GAME_END = "game_end"
    GUARD_PROTECT = "guard_protect"
    WOLF_CHAT_MESSAGE = "wolf_chat_message"
    WOLF_KILL_VOTE = "wolf_kill_vote"
    WOLF_KILL_DECIDED = "wolf_kill_decided"
    WOLF_TIE_RANDOM = "wolf_tie_random"
    WITCH_ACTION = "witch_action"
    SEER_CHECK = "seer_check"
    SEER_CHECK_RESULT = "seer_check_result"
    NO_DEATH_TONIGHT = "no_death_tonight"
    DEATH_AT_NIGHT = "death_at_night"
    DAY_ANNOUNCE = "day_announce"
    LAST_WORDS = "last_words"
    SPEECH = "speech"
    VOTE_CAST = "vote_cast"
    VOTE_RESULT = "vote_result"
    VOTE_PK_ENTER = "vote_pk_enter"
    PEACEFUL_DAY = "peaceful_day"
    EXILE = "exile"
    WIN_CHECK = "win_check"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_INVALID_ACTION = "agent_invalid_action"
    AGENT_FALLBACK_TRIGGERED = "agent_fallback_triggered"
    AGENT_BUDGET_WARNING = "agent_budget_warning"
    LLM_CALL = "llm_call"
    ROLE_REVEAL = "role_reveal"


class Visibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    public: bool
    seats: tuple[int, ...] = ()

    @field_validator("seats")
    @classmethod
    def _seats_in_range(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        for seat in value:
            if seat < 1:
                raise ValueError(f"seat must be positive: {seat}")
        return tuple(sorted(set(value)))


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: EventId
    schema_version: Literal["1.0"] = "1.0"
    game_id: GameId
    seq: int
    phase: str
    day: int
    timestamp: datetime
    type: EventType
    actor: int | None
    visibility: Visibility
    payload: JsonDict = {}

    @field_validator("event_id", mode="before")
    @classmethod
    def _parse_event_id(cls, value: object) -> EventId:
        if isinstance(value, EventId):
            return value
        if isinstance(value, str):
            return EventId.parse(value)
        raise TypeError("event_id must be EventId or UUID string")

    @field_validator("game_id", mode="before")
    @classmethod
    def _parse_game_id(cls, value: object) -> GameId:
        if isinstance(value, GameId):
            return value
        if isinstance(value, str):
            return GameId.parse(value)
        raise TypeError("game_id must be GameId or UUID string")

    @field_serializer("event_id")
    def _serialize_event_id(self, value: EventId) -> str:
        return str(value)

    @field_serializer("game_id")
    def _serialize_game_id(self, value: GameId) -> str:
        return str(value)


def public_visibility() -> Visibility:
    return Visibility(public=True, seats=())


def seats_visibility(seats: tuple[int, ...]) -> Visibility:
    return Visibility(public=False, seats=seats)


def hidden_visibility() -> Visibility:
    return Visibility(public=False, seats=())


def draft_event(
    *,
    game_id: GameId,
    phase: str,
    day: int,
    event_type: EventType,
    actor: int | None,
    visibility: Visibility,
    payload: JsonDict | None = None,
) -> Event:
    return Event(
        event_id=EventId.deterministic("draft", 0, event_type.value),
        game_id=game_id,
        seq=0,
        phase=phase,
        day=day,
        timestamp=DRAFT_TIMESTAMP,
        type=event_type,
        actor=actor,
        visibility=visibility,
        payload={} if payload is None else payload,
    )

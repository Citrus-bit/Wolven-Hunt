from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5


@dataclass(frozen=True, slots=True)
class GameId:
    value: UUID

    @classmethod
    def new(cls) -> GameId:
        return cls(uuid4())

    @classmethod
    def deterministic(cls, seed: str) -> GameId:
        return cls(uuid5(NAMESPACE_URL, f"wolven-hunt:game:{seed}"))

    @classmethod
    def parse(cls, value: str | UUID | GameId) -> GameId:
        if isinstance(value, GameId):
            return value
        if isinstance(value, UUID):
            return cls(value)
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class EventId:
    value: UUID

    @classmethod
    def new(cls) -> EventId:
        return cls(uuid4())

    @classmethod
    def deterministic(cls, seed: str, seq: int, event_type: str) -> EventId:
        return cls(uuid5(NAMESPACE_URL, f"wolven-hunt:event:{seed}:{seq}:{event_type}"))

    @classmethod
    def parse(cls, value: str | UUID | EventId) -> EventId:
        if isinstance(value, EventId):
            return value
        if isinstance(value, UUID):
            return cls(value)
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)

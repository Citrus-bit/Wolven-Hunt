from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str = "configs/games/classic_8.yaml"
    seed: str = "api-dev-seed"
    agents: dict[int, str] = Field(default_factory=dict)


class CreateGameResponse(BaseModel):
    game_id: str


class GameSummaryResponse(BaseModel):
    game_id: str
    status: str
    winner: str | None
    day: int
    phase: str
    event_count: int


class ReplayRequest(BaseModel):
    mode: str = "deterministic"


class TextActionRequest(BaseModel):
    seat: int = Field(ge=1, le=8)
    text: str = Field(max_length=300)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None

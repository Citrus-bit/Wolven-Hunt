from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentSpecMock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["mock"] = "mock"


class AgentSpecLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["llm"] = "llm"
    provider: Literal["mock", "litellm"] = "litellm"
    model: str
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = ""
    timeout_seconds: float | None = Field(default=None, gt=0)


AgentSpec = Annotated[AgentSpecMock | AgentSpecLLM, Field(discriminator="kind")]
AgentSpecInput = AgentSpec | str


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str = "configs/games/classic_10.yaml"
    seed: str = "api-dev-seed"
    agents: dict[int, AgentSpecInput] = Field(default_factory=dict)
    pacing: Literal["live", "fast", "off"] | None = None


class CreateGameResponse(BaseModel):
    game_id: str


class GameListItem(BaseModel):
    game_id: str
    started_at: str | None = None
    ended_at: str | None = None
    winner: str | None = None
    status: str
    event_count: int = 0


class GameSummaryResponse(BaseModel):
    game_id: str
    status: str
    winner: str | None
    day: int
    phase: str
    event_count: int
    timings: dict[str, int]


class ReplayRequest(BaseModel):
    mode: str = "deterministic"


class TextActionRequest(BaseModel):
    seat: int = Field(ge=1)
    text: str = Field(max_length=300)


class AckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    event: str
    client_event_id: str = ""


class NarrativeRow(BaseModel):
    seq: int
    day: int
    phase: str
    kind: Literal["system", "speech", "action", "announce", "verdict"]
    text: str
    actor: int | None
    icon: str | None = None


class SpectatorEffect(BaseModel):
    seq: int
    day: int
    phase: str
    kind: Literal[
        "guard_shield",
        "wolf_attack",
        "seer_vision",
        "witch_potion",
        "death_reveal",
    ]
    actor: int | None
    source_seat: int | None
    target_seat: int
    asset_key: str
    duration_ms: int
    meta: dict[str, object] = Field(default_factory=dict)


class RoleRevealSeat(BaseModel):
    seat: int
    role: str
    alive: bool


class RoleRevealHighlight(BaseModel):
    seq: int
    summary: str


class RoleRevealResponse(BaseModel):
    winner: str
    seats: tuple[RoleRevealSeat, ...]
    highlights: tuple[RoleRevealHighlight, ...]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None


class ModelTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock", "litellm"] = "litellm"
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = Field(default=15.0, gt=0)
    thinking_enabled: bool = True


class ModelTestResponse(BaseModel):
    ok: bool
    message: str | None = None

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    thinking_enabled: bool = False


AgentSpec = Annotated[AgentSpecMock | AgentSpecLLM, Field(discriminator="kind")]
AgentSpecInput = AgentSpec | str


class SeatPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=32)
    icon_path: str = Field(pattern=r"^/assets/lobby/[A-Za-z0-9_.-]+$")


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str = "configs/games/classic_10.yaml"
    seed: str = "api-dev-seed"
    agents: dict[int, AgentSpecInput] = Field(default_factory=dict)
    pacing: Literal["live", "fast", "off"] | None = None
    start_paused: bool = False
    seat_presentation: dict[int, SeatPresentation] = Field(default_factory=dict)
    evolution_enabled: bool | None = None


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
    seat_presentation: dict[int, SeatPresentation] = Field(default_factory=dict)


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


class ReviewReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: str
    verdict: str
    turning_points: tuple[str, ...] = ()
    overall_assessment: str


class ReviewReportLeaderboardItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    seat: int = Field(ge=1)
    nickname: str
    role: str
    camp: str
    overall_score: int = Field(ge=0, le=100)
    reason: str


class ReviewReportScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal[
        "speech",
        "reasoning",
        "voting",
        "camp_contribution",
        "information_control",
        "role_duty",
    ]
    label: str
    value: int = Field(ge=0, le=100)


class ReviewReportPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: int = Field(ge=1)
    nickname: str
    role: str
    camp: str
    alive: bool
    scores: tuple[ReviewReportScore, ...]
    overall_score: int = Field(ge=0, le=100)
    evaluation: str
    evidence: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()
    mistakes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()

    @field_validator("scores")
    @classmethod
    def _scores_are_hex_axes(
        cls,
        value: tuple[ReviewReportScore, ...],
    ) -> tuple[ReviewReportScore, ...]:
        if tuple(score.key for score in value) != (
            "speech",
            "reasoning",
            "voting",
            "camp_contribution",
            "information_control",
            "role_duty",
        ):
            raise ValueError("review scores must contain the fixed six radar axes in order")
        return value


class ReviewReportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int
    phase: str
    seq: int | None = None
    title: str
    analysis: str
    impact: str


class ReviewReportCounterfactual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise: str
    likely_outcome: str
    lesson: str


class ReviewReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    game_id: str
    generated_at: str
    generation_mode: Literal["real_ai", "offline_mock"]
    summary: ReviewReportSummary
    leaderboard: tuple[ReviewReportLeaderboardItem, ...]
    players: tuple[ReviewReportPlayer, ...]
    key_decisions: tuple[ReviewReportDecision, ...]
    counterfactuals: tuple[ReviewReportCounterfactual, ...]


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
    thinking_enabled: bool = False


class ModelTestResponse(BaseModel):
    ok: bool
    message: str | None = None

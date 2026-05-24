from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GuardOutput(LLMOutput):
    target: int = Field(ge=1)


class WolfChatOutput(LLMOutput):
    text: str = Field(max_length=300)


class WolfKillOutput(LLMOutput):
    target: int = Field(ge=1)


class SeerOutput(LLMOutput):
    target: int = Field(ge=1)


class SpeechOutput(LLMOutput):
    text: str = Field(max_length=300)


class WitchOutput(LLMOutput):
    action: Literal["save", "poison", "skip"] = "skip"
    target: int | None = Field(default=None, ge=1)


class VoteOutput(LLMOutput):
    target: int | None = Field(ge=1)


class PkVoteOutput(LLMOutput):
    target: int | None = Field(ge=1)


class LastWordsOutput(LLMOutput):
    text: str = Field(max_length=300)


PHASE_OUTPUT_MODELS: dict[str, type[LLMOutput]] = {
    "NIGHT_GUARD": GuardOutput,
    "NIGHT_WOLF_CHAT": WolfChatOutput,
    "NIGHT_WOLF_VOTE": WolfKillOutput,
    "NIGHT_WITCH": WitchOutput,
    "NIGHT_SEER": SeerOutput,
    "DAY_SPEECH": SpeechOutput,
    "DAY_VOTE": VoteOutput,
    "DAY_VOTE_PK": PkVoteOutput,
    "DAY_LAST_WORDS": LastWordsOutput,
}

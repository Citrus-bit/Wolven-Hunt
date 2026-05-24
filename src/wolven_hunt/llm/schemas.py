from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GuardOutput(LLMOutput):
    target: int = Field(ge=1)


class WolfChatOutput(LLMOutput):
    text: str = Field(max_length=300)

    @field_validator("text")
    @classmethod
    def text_must_not_be_placeholder(cls, value: str) -> str:
        return _validate_action_text(value)


class WolfKillOutput(LLMOutput):
    target: int = Field(ge=1)


class SeerOutput(LLMOutput):
    target: int = Field(ge=1)


class SpeechOutput(LLMOutput):
    text: str = Field(max_length=300)

    @field_validator("text")
    @classmethod
    def text_must_not_be_placeholder(cls, value: str) -> str:
        return _validate_action_text(value)


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


PLACEHOLDER_TEXTS = frozenset(
    {
        "[沉默]",
        "沉默",
        "无",
        "暂无",
        "无话可说",
        "没有发言",
        "没有信息",
        "暂无信息",
        "我没有信息",
        "我不知道",
        "先观察",
        "我先观察",
        "过",
    }
)


def _validate_action_text(value: str) -> str:
    stripped = value.strip()
    normalized = "".join(stripped.split())
    if not stripped:
        raise ValueError("text must not be empty")
    if normalized in PLACEHOLDER_TEXTS:
        raise ValueError("text must not be a placeholder")
    return value

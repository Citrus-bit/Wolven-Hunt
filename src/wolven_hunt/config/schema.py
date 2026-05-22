from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RoleDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    count: int
    camp: str


class RolePack(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    name: str
    seat_numbering: str
    seat_count: int
    roles: dict[str, RoleDefinition]
    visibility: dict[str, Any]


class SpeechConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: str
    max_chars: int


class WinConditions(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_after: tuple[str, ...]
    wolf_wins_when: tuple[str, ...]
    good_wins_when: tuple[str, ...]


class SeerRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    can_check_dead: bool
    can_check_self: bool
    result_granularity: str


class GuardRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    can_guard_first_night: bool
    can_guard_self: bool
    can_guard_same_target_consecutive_nights: bool


class WolfRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    night_chat_rounds: int
    kill_vote_mode: str
    kill_decision: str
    tie_break: str
    can_no_kill: bool
    can_kill_wolf_teammate: bool


class KnightRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_uses_per_game: int
    can_act_first_day: bool
    can_act_at_night: bool
    window: str
    after_action_skip_remaining_day: bool


class VoteRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str
    public_ballot: bool
    can_abstain: bool
    can_change_vote: bool
    sheriff: bool
    can_vote_self: bool
    first_round_targets: str
    pk_round_targets: str
    pk_players_vote_in_pk_round: bool
    second_tie_result: str


class LastWordsRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: tuple[str, ...]
    denied: tuple[str, ...]


class FallbackRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_retries: int
    actions: dict[str, str]


class ReplayRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    deterministic: bool
    resimulate: bool
    random_events_record_candidates_and_selected: bool


class TimingRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    night_start_ms: int = Field(ge=0)
    night_guard_ms: int = Field(ge=0)
    night_wolf_chat_ms: int = Field(ge=0)
    night_wolf_vote_ms: int = Field(ge=0)
    night_seer_ms: int = Field(ge=0)
    day_announce_ms: int = Field(ge=0)
    day_last_words_ms: int = Field(ge=0)
    day_speech_ms: int = Field(ge=0)
    day_vote_ms: int = Field(ge=0)
    day_vote_pk_ms: int = Field(ge=0)
    knight_duel_ms: int = Field(ge=0)


class RuleSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    name: str
    first_night_can_die: bool
    first_speaker_seat: int
    speech: SpeechConfig
    win_conditions: WinConditions
    seer: SeerRules
    guard: GuardRules
    wolves: WolfRules
    knight: KnightRules
    vote: VoteRules
    last_words: LastWordsRules
    fallback: FallbackRules
    replay: ReplayRules
    timings: TimingRules


class SeatRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int
    end: int


class PromptPackRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: str
    root: str
    version_policy: str


class GameConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    name: str
    description: str
    seat_range: SeatRange
    role_pack_ref: str
    rule_set_ref: str
    model_roster_ref: str
    prompt_pack: PromptPackRef
    random_seed: dict[str, Any]
    metadata: dict[str, Any]
    role_pack: RolePack
    rule_set: RuleSet
    config_hash: str
    path: Path = Field(repr=False)
    prompt_pack_root: Path = Field(repr=False)
    model_roster_path: Path = Field(repr=False)

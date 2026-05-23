from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from wolven_hunt.core.seat import Seat


@dataclass(frozen=True, slots=True)
class GuardProtect:
    actor: Seat
    target: Seat


@dataclass(frozen=True, slots=True)
class WolfChatMessage:
    actor: Seat
    text: str


@dataclass(frozen=True, slots=True)
class WolfKillVote:
    actor: Seat
    target: Seat


@dataclass(frozen=True, slots=True)
class SeerCheck:
    actor: Seat
    target: Seat


@dataclass(frozen=True, slots=True)
class Speech:
    actor: Seat
    text: str


@dataclass(frozen=True, slots=True)
class WitchAction:
    actor: Seat
    action: Literal["save", "poison", "skip"]
    target: Seat | None


@dataclass(frozen=True, slots=True)
class Vote:
    actor: Seat
    target: Seat


@dataclass(frozen=True, slots=True)
class PkVote:
    actor: Seat
    target: Seat


@dataclass(frozen=True, slots=True)
class LastWords:
    actor: Seat
    text: str


Action: TypeAlias = (
    GuardProtect
    | WolfChatMessage
    | WolfKillVote
    | SeerCheck
    | Speech
    | WitchAction
    | Vote
    | PkVote
    | LastWords
)

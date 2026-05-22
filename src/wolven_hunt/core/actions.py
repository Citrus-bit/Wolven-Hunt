from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

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
class KnightChallenge:
    actor: Seat
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
    | KnightChallenge
    | Vote
    | PkVote
    | LastWords
)

from __future__ import annotations

from typing import Protocol

from wolven_hunt.core.actions import (
    GuardProtect,
    KnightChallenge,
    LastWords,
    PkVote,
    SeerCheck,
    Speech,
    Vote,
    WolfChatMessage,
    WolfKillVote,
)
from wolven_hunt.referee.view import PlayerView


class PlayerInterface(Protocol):
    def decide_guard(self, view: PlayerView) -> GuardProtect: ...

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage: ...

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote: ...

    def decide_seer(self, view: PlayerView) -> SeerCheck: ...

    def decide_speech(self, view: PlayerView) -> Speech: ...

    def decide_knight_challenge(self, view: PlayerView) -> KnightChallenge: ...

    def decide_vote(self, view: PlayerView) -> Vote: ...

    def decide_pk_vote(self, view: PlayerView) -> PkVote: ...

    def decide_last_words(self, view: PlayerView) -> LastWords: ...

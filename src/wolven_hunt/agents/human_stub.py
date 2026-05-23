from __future__ import annotations

from wolven_hunt.agents.interface import PlayerInterface
from wolven_hunt.core.actions import (
    GuardProtect,
    LastWords,
    PkVote,
    SeerCheck,
    Speech,
    Vote,
    WitchAction,
    WolfChatMessage,
    WolfKillVote,
)
from wolven_hunt.referee.view import PlayerView


class HumanPlayer(PlayerInterface):
    def decide_guard(self, view: PlayerView) -> GuardProtect:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_seer(self, view: PlayerView) -> SeerCheck:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_speech(self, view: PlayerView) -> Speech:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_witch(self, view: PlayerView) -> WitchAction:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_vote(self, view: PlayerView) -> Vote:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

    def decide_last_words(self, view: PlayerView) -> LastWords:
        raise NotImplementedError("HumanPlayer is reserved for STEP-06+")

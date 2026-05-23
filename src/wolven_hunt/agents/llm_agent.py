from __future__ import annotations

from typing import cast

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
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.gateway import (
    LLMCallResult,
    LLMError,
    LLMErrorType,
    LLMFallbackRequired,
    LLMGateway,
)
from wolven_hunt.llm.prompts import PromptRenderer
from wolven_hunt.llm.schemas import (
    GuardOutput,
    LastWordsOutput,
    PkVoteOutput,
    SeerOutput,
    SpeechOutput,
    VoteOutput,
    WitchOutput,
    WolfChatOutput,
    WolfKillOutput,
)
from wolven_hunt.referee.view import PlayerView


class LLMAgent(PlayerInterface):
    def __init__(
        self,
        *,
        seat: Seat,
        gateway: LLMGateway,
        prompt_renderer: PromptRenderer,
        rng: DeterministicRNG,
    ) -> None:
        self.seat = seat
        self.gateway = gateway
        self.prompt_renderer = prompt_renderer
        self.rng = rng
        self._last_call_result: LLMCallResult | None = None

    def consume_last_call_result(self) -> LLMCallResult | None:
        result = self._last_call_result
        self._last_call_result = None
        return result

    def decide_guard(self, view: PlayerView) -> GuardProtect:
        parsed = cast(GuardOutput, self._call(view, "NIGHT_GUARD", GuardOutput))
        return GuardProtect(actor=self.seat, target=Seat(parsed.target))

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        parsed = cast(WolfChatOutput, self._call(view, "NIGHT_WOLF_CHAT", WolfChatOutput))
        return WolfChatMessage(actor=self.seat, text=parsed.text)

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote:
        parsed = cast(WolfKillOutput, self._call(view, "NIGHT_WOLF_VOTE", WolfKillOutput))
        return WolfKillVote(actor=self.seat, target=Seat(parsed.target))

    def decide_seer(self, view: PlayerView) -> SeerCheck:
        parsed = cast(SeerOutput, self._call(view, "NIGHT_SEER", SeerOutput))
        return SeerCheck(actor=self.seat, target=Seat(parsed.target))

    def decide_speech(self, view: PlayerView) -> Speech:
        parsed = cast(SpeechOutput, self._call(view, "DAY_SPEECH", SpeechOutput))
        return Speech(actor=self.seat, text=parsed.text)

    def decide_witch(self, view: PlayerView) -> WitchAction:
        parsed = cast(WitchOutput, self._call(view, "NIGHT_WITCH", WitchOutput))
        target = None if parsed.target is None else Seat(parsed.target)
        return WitchAction(actor=self.seat, action=parsed.action, target=target)

    def decide_vote(self, view: PlayerView) -> Vote:
        parsed = cast(VoteOutput, self._call(view, "DAY_VOTE", VoteOutput))
        return Vote(actor=self.seat, target=Seat(parsed.target))

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        parsed = cast(PkVoteOutput, self._call(view, "DAY_VOTE_PK", PkVoteOutput))
        return PkVote(actor=self.seat, target=Seat(parsed.target))

    def decide_last_words(self, view: PlayerView) -> LastWords:
        parsed = cast(LastWordsOutput, self._call(view, "DAY_LAST_WORDS", LastWordsOutput))
        return LastWords(actor=self.seat, text=parsed.text)

    def _call(
        self,
        view: PlayerView,
        phase: str,
        output_model: type[GuardOutput]
        | type[WolfChatOutput]
        | type[WolfKillOutput]
        | type[SeerOutput]
        | type[SpeechOutput]
        | type[WitchOutput]
        | type[VoteOutput]
        | type[PkVoteOutput]
        | type[LastWordsOutput],
    ) -> object:
        prompt = self.prompt_renderer.render(
            view=view,
            phase=phase,
            schema_json=output_model.model_json_schema(),
        )
        result = self.gateway.call(
            seat=self.seat,
            phase=phase,
            prompt=prompt,
            output_model=output_model,
            rng=self.rng,
        )
        self._last_call_result = result
        if result.error is not None or result.parsed is None:
            raise LLMFallbackRequired(
                result.error
                if result.error is not None
                else LLMError(LLMErrorType.SCHEMA_VIOLATION, "LLM returned no parsed output")
            )
        return result.parsed

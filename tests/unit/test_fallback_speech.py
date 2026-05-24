from __future__ import annotations

import hashlib

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import Speech
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import apply_action, build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.cost import TokenUsage
from wolven_hunt.llm.gateway import LLMCallResult, LLMError, LLMErrorType, LLMFallbackRequired
from wolven_hunt.orchestration.fsm import _decide_with_fallback
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.view import PlayerView
from wolven_hunt.storage.event_log import EventLog


class TimeoutSpeechAgent:
    def __init__(self) -> None:
        raw_response = ""
        self.result: LLMCallResult | None = LLMCallResult(
            parsed=None,
            raw_response=raw_response,
            prompt_hash=_sha256("{}"),
            raw_response_hash=_sha256(raw_response),
            storage_ref="llm/3/DAY_SPEECH/000001",
            model="unknown",
            tokens=TokenUsage(),
            cost_usd=0.0,
            prompt_version="v1",
            error=LLMError(LLMErrorType.TIMEOUT, "too slow"),
        )

    def consume_last_call_result(self) -> LLMCallResult | None:
        result = self.result
        self.result = None
        return result

    def decide_speech(self, view: PlayerView) -> Speech:
        del view
        raise LLMFallbackRequired(LLMError(LLMErrorType.TIMEOUT, "too slow"))


def test_day_speech_timeout_fallback_uses_contextual_public_template(
    game_config: GameConfig,
) -> None:
    seed = "fallback-speech"
    rng = DeterministicRNG(seed)
    state, start_events = build_initial_state(game_config, seed)
    state = state.with_phase(Phase.DAY_SPEECH.value)
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)
    state, events = apply_action(
        state,
        Speech(actor=Seat(1), text="我怀疑2号需要解释。"),
        game_config,
        rng,
    )
    event_log.append_all(events)

    action = _decide_with_fallback(
        state,
        game_config,
        TimeoutSpeechAgent(),
        event_log,
        Seat(3),
        lambda agent, view: agent.decide_speech(view),
        rng,
    )

    assert isinstance(action, Speech)
    assert "我没有更多信息" not in action.text
    assert "1号" in action.text

    state, events = apply_action(state, action, game_config, rng)
    event_log.append_all(events)
    assert [event.type.value for event in event_log.events[-4:]] == [
        "llm_call",
        "agent_timeout",
        "agent_fallback_triggered",
        "speech",
    ]
    assert event_log.events[-1].payload["text"] == action.text


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

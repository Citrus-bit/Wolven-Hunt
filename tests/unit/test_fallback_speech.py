from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import GuardProtect, LastWords, Speech
from wolven_hunt.core.events import Event, EventType, draft_event, seats_visibility
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import apply_action, build_initial_state
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.llm.cost import TokenUsage
from wolven_hunt.llm.gateway import LLMCallResult, LLMError, LLMErrorType, LLMFallbackRequired
from wolven_hunt.orchestration.fsm import _apply_and_log, _decide_with_fallback
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.view import PlayerView
from wolven_hunt.referee.visibility import filter_spectator_events
from wolven_hunt.storage.event_log import EventLog
from wolven_hunt.storage.narrative import event_to_narrative


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


class InvalidGuardLastWordsAgent:
    def __init__(self, seat: Seat) -> None:
        self.seat = seat
        self.calls = 0

    def decide_last_words(self, view: PlayerView) -> LastWords:
        del view
        self.calls += 1
        return LastWords(
            actor=self.seat,
            text="我连续两晚守护自己成功,保证了神职安全。",
        )


class ConsecutiveGuardAgent:
    def __init__(self, seat: Seat, target: Seat) -> None:
        self.seat = seat
        self.target = target
        self.calls = 0

    def decide_guard(self, view: PlayerView) -> GuardProtect:
        del view
        self.calls += 1
        return GuardProtect(actor=self.seat, target=self.target)


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


def test_invalid_guard_last_words_falls_back_before_event_and_narrative(
    game_config: GameConfig,
) -> None:
    seed = "guard-last-words-text-fallback"
    rng = DeterministicRNG(seed)
    state, start_events = build_initial_state(game_config, seed)
    guard = state.seats_by_role(Role.GUARD)[0]
    other = _other_alive_seat(state, guard)
    state = replace(state, day=3, phase=Phase.DAY_LAST_WORDS.value)
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)
    event_log.append_all(_guard_events(state, guard, (guard, other, guard)))

    agent = InvalidGuardLastWordsAgent(guard)
    action = _decide_with_fallback(
        state,
        game_config,
        agent,
        event_log,
        guard,
        lambda player, view: player.decide_last_words(view),
        rng,
    )

    assert agent.calls == game_config.rule_set.fallback.max_retries + 1
    assert isinstance(action, LastWords)
    assert action.text == "我没有遗言"

    state = _apply_and_log(state, action, game_config, rng, event_log, None, None)
    assert state is not None
    assert any(
        event.type is EventType.AGENT_INVALID_ACTION
        and event.payload["rule_id"] == "text.guard_consecutive_claim"
        for event in event_log.events
    )
    assert any(event.type is EventType.AGENT_FALLBACK_TRIGGERED for event in event_log.events)
    assert not _events_contain(event_log.events, "连续两晚守护自己成功")
    narrative_text = "\n".join(
        row.text for row in (event_to_narrative(event) for event in event_log.events) if row
    )
    spectator_text = "\n".join(
        str(event.model_dump(mode="json"))
        for event in filter_spectator_events(event_log.events)
    )
    assert "连续两晚守护自己成功" not in narrative_text
    assert "连续两晚守护自己成功" not in spectator_text


def test_consecutive_guard_action_falls_back_to_legal_target(
    game_config: GameConfig,
) -> None:
    seed = "guard-action-fallback"
    rng = DeterministicRNG(seed)
    state, start_events = build_initial_state(game_config, seed)
    guard = state.seats_by_role(Role.GUARD)[0]
    previous = _other_alive_seat(state, guard)
    state = replace(
        state,
        phase=Phase.NIGHT_GUARD.value,
        last_guard_target=previous,
    )
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)

    action = _decide_with_fallback(
        state,
        game_config,
        ConsecutiveGuardAgent(guard, previous),
        event_log,
        guard,
        lambda player, view: player.decide_guard(view),
        rng,
    )

    assert isinstance(action, GuardProtect)
    assert action.target != previous
    state = _apply_and_log(state, action, game_config, rng, event_log, None, None)
    assert state.night_guard_target != previous
    invalids = [
        event
        for event in event_log.events
        if event.type is EventType.AGENT_INVALID_ACTION
    ]
    assert invalids
    assert {event.payload["rule_id"] for event in invalids} == {"guard.consecutive"}
    guard_events = [event for event in event_log.events if event.type is EventType.GUARD_PROTECT]
    assert len(guard_events) == 1
    assert guard_events[0].payload["target"] != previous.number


def test_apply_and_log_hard_gate_blocks_illegal_guard_action(
    game_config: GameConfig,
) -> None:
    seed = "guard-hard-gate"
    rng = DeterministicRNG(seed)
    state, start_events = build_initial_state(game_config, seed)
    guard = state.seats_by_role(Role.GUARD)[0]
    previous = _other_alive_seat(state, guard)
    state = replace(
        state,
        phase=Phase.NIGHT_GUARD.value,
        last_guard_target=previous,
    )
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)

    with pytest.raises(RuntimeError, match=r"guard\.consecutive"):
        _apply_and_log(
            state,
            GuardProtect(actor=guard, target=previous),
            game_config,
            rng,
            event_log,
            None,
            None,
        )

    assert not any(event.type is EventType.GUARD_PROTECT for event in event_log.events)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _guard_events(
    state: GameState,
    guard: Seat,
    targets: tuple[Seat, ...],
) -> tuple[Event, ...]:
    return tuple(
        draft_event(
            game_id=state.game_id,
            phase=Phase.NIGHT_GUARD.value,
            day=day,
            event_type=EventType.GUARD_PROTECT,
            actor=guard.number,
            visibility=seats_visibility((guard.number,)),
            payload={"target": target.number},
        )
        for day, target in enumerate(targets, start=1)
    )


def _other_alive_seat(state: GameState, seat: Seat) -> Seat:
    return next(player.seat for player in state.players if player.alive and player.seat != seat)


def _events_contain(events: tuple[Event, ...], text: str) -> bool:
    return any(text in str(event.payload) for event in events)

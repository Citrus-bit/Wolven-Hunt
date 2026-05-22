from __future__ import annotations

from collections.abc import Callable, Mapping

from wolven_hunt.agents.interface import PlayerInterface
from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import (
    Action,
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
from wolven_hunt.core.events import EventType, draft_event, hidden_visibility
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import (
    advance_to_next_night,
    apply_action,
    build_initial_state,
    emit_day_announce,
    emit_win_check,
    finish_pk_vote,
    finish_vote,
    phase_enter,
    phase_exit,
    resolve_night,
)
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.validate import validate_action
from wolven_hunt.referee.view import PlayerView, build_view
from wolven_hunt.storage.event_log import EventLog

AgentMap = Mapping[int, PlayerInterface]


def run_game(
    *,
    config: GameConfig,
    seed: str,
    agents: AgentMap,
    max_days: int = 20,
) -> tuple[GameState, EventLog]:
    rng = DeterministicRNG(seed)
    event_log = EventLog(seed=seed)
    state, start_events = build_initial_state(config, seed)
    event_log.append_all(start_events)

    while state.winner is None and state.day <= max_days:
        state = _run_night(state, config, agents, rng, event_log)
        if state.winner is not None:
            break
        state = _run_day(state, config, agents, rng, event_log)
        if state.winner is None:
            state = advance_to_next_night(state)
    if state.winner is None:
        # Deterministic guardrail for pathological mock strategies.
        state, win_events = emit_win_check(state, phase=Phase.GAME_END.value)
        event_log.append_all(win_events)
    return state, event_log


def _run_night(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
) -> GameState:
    state, events = phase_enter(state, Phase.NIGHT_START.value)
    event_log.append_all(events)
    event_log.append_all(phase_exit(state))

    guard_seats = state.seats_by_role(Role.GUARD, alive_only=True)
    if guard_seats:
        state = _enter_phase(state, Phase.NIGHT_GUARD, event_log)
        guard = guard_seats[0]
        action = _decide_with_fallback(
            state,
            config,
            agents[guard.number],
            event_log,
            guard,
            lambda agent, view: agent.decide_guard(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log)
        event_log.append_all(phase_exit(state))

    wolf_seats = state.wolf_seats(alive_only=True)
    if wolf_seats:
        state = _enter_phase(state, Phase.NIGHT_WOLF_CHAT, event_log)
        for wolf in wolf_seats:
            action = _decide_with_fallback(
                state,
                config,
                agents[wolf.number],
                event_log,
                wolf,
                lambda agent, view: agent.decide_wolf_chat(view),
                rng,
            )
            state = _apply_and_log(state, action, config, rng, event_log)
        event_log.append_all(phase_exit(state))

        state = _enter_phase(state, Phase.NIGHT_WOLF_VOTE, event_log)
        for wolf in wolf_seats:
            if not state.player(wolf).alive:
                continue
            action = _decide_with_fallback(
                state,
                config,
                agents[wolf.number],
                event_log,
                wolf,
                lambda agent, view: agent.decide_wolf_vote(view),
                rng,
            )
            state = _apply_and_log(state, action, config, rng, event_log)
        event_log.append_all(phase_exit(state))

    seer_seats = state.seats_by_role(Role.SEER, alive_only=True)
    if seer_seats:
        state = _enter_phase(state, Phase.NIGHT_SEER, event_log)
        seer = seer_seats[0]
        action = _decide_with_fallback(
            state,
            config,
            agents[seer.number],
            event_log,
            seer,
            lambda agent, view: agent.decide_seer(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log)
        event_log.append_all(phase_exit(state))

    state = _enter_phase(state, Phase.NIGHT_RESOLVE, event_log)
    state, events = resolve_night(state)
    event_log.append_all(events)
    event_log.append_all(phase_exit(state))
    state, events = emit_win_check(state, phase=Phase.CHECK_WIN_NIGHT.value)
    event_log.append_all(events)
    return state


def _run_day(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
) -> GameState:
    state = _enter_phase(state, Phase.DAY_ANNOUNCE, event_log)
    state, events = emit_day_announce(state)
    event_log.append_all(events)
    event_log.append_all(phase_exit(state))

    if state.day == 1 and state.first_night_deaths:
        state = _enter_phase(state, Phase.DAY_LAST_WORDS, event_log)
        for seat in state.first_night_deaths:
            action = _decide_with_fallback(
                state,
                config,
                agents[seat.number],
                event_log,
                seat,
                lambda agent, view: agent.decide_last_words(view),
                rng,
            )
            state = _apply_and_log(state, action, config, rng, event_log)
        event_log.append_all(phase_exit(state))

    state, interrupted = _maybe_knight_interrupt(state, config, agents, rng, event_log)
    if state.winner is not None or interrupted:
        return state

    state = _enter_phase(state, Phase.DAY_SPEECH, event_log)
    for seat in state.alive_seats():
        state, interrupted = _maybe_knight_interrupt(state, config, agents, rng, event_log)
        if state.winner is not None or interrupted:
            return state
        if not state.player(seat).alive:
            continue
        action = _decide_with_fallback(
            state,
            config,
            agents[seat.number],
            event_log,
            seat,
            lambda agent, view: agent.decide_speech(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log)
    event_log.append_all(phase_exit(state))

    state, interrupted = _maybe_knight_interrupt(state, config, agents, rng, event_log)
    if state.winner is not None or interrupted:
        return state

    state = _enter_phase(state, Phase.DAY_VOTE, event_log)
    for seat in state.alive_seats():
        action = _decide_with_fallback(
            state,
            config,
            agents[seat.number],
            event_log,
            seat,
            lambda agent, view: agent.decide_vote(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log)
    state, vote_events = finish_vote(state)
    event_log.append_all(vote_events)
    event_log.append_all(phase_exit(state))

    if state.pk_seats:
        state = _enter_phase(state, Phase.DAY_VOTE_PK, event_log)
        voters = tuple(seat for seat in state.alive_seats() if seat not in state.pk_seats)
        if not voters:
            state, events = finish_pk_vote(state)
            event_log.append_all(events)
        else:
            for seat in voters:
                action = _decide_with_fallback(
                    state,
                    config,
                    agents[seat.number],
                    event_log,
                    seat,
                    lambda agent, view: agent.decide_pk_vote(view),
                    rng,
                )
                state = _apply_and_log(state, action, config, rng, event_log)
            state, events = finish_pk_vote(state)
            event_log.append_all(events)
        event_log.append_all(phase_exit(state))

    state, events = emit_win_check(state, phase=Phase.CHECK_WIN_DAY.value)
    event_log.append_all(events)
    return state


def _enter_phase(state: GameState, phase: Phase, event_log: EventLog) -> GameState:
    state, events = phase_enter(state, phase.value)
    event_log.append_all(events)
    return state


def _apply_and_log(
    state: GameState,
    action: Action,
    config: GameConfig,
    rng: DeterministicRNG,
    event_log: EventLog,
) -> GameState:
    state, events = apply_action(state, action, config, rng)
    event_log.append_all(events)
    return state


def _decide_with_fallback(
    state: GameState,
    config: GameConfig,
    agent: PlayerInterface,
    event_log: EventLog,
    seat: Seat,
    decide: Callable[[PlayerInterface, PlayerView], Action],
    rng: DeterministicRNG,
) -> Action:
    view = build_view(state, event_log.events, rule_set=config.rule_set, seat=seat)
    try:
        action = decide(agent, view)
    except Exception:
        action = _fallback_for_phase(state, seat, rng)
        _record_fallback(state, seat, event_log, "exception", action)
        return action
    rejection = validate_action(state, action, config.rule_set)
    if rejection is None:
        return action
    event_log.append(
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.AGENT_INVALID_ACTION,
            actor=seat.number,
            visibility=hidden_visibility(),
            payload={"rule_id": rejection.rule_id, "message": rejection.message},
        )
    )
    reason = f"validation_failed:{rejection.rule_id}"
    action = _fallback_for_phase(state, seat, rng)
    _record_fallback(state, seat, event_log, reason, action)
    return action


def _record_fallback(
    state: GameState,
    seat: Seat,
    event_log: EventLog,
    reason: str,
    action: Action,
) -> None:
    selected = _selected_from_action(action)
    event_log.append(
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.AGENT_FALLBACK_TRIGGERED,
            actor=seat.number,
            visibility=hidden_visibility(),
            payload={
                "phase": state.phase,
                "seat": seat.number,
                "reason": reason,
                "fallback_action": action.__class__.__name__,
                "rng_stream": f"fallback:{state.phase}:seat{seat.number}:retry0",
                "candidates": [],
                "selected": selected,
            },
        )
    )


def _selected_from_action(action: Action) -> int | str | None:
    if isinstance(action, (GuardProtect, WolfKillVote, SeerCheck, Vote, PkVote)):
        return action.target.number
    if isinstance(action, KnightChallenge):
        return None if action.target is None else action.target.number
    if isinstance(action, (Speech, LastWords, WolfChatMessage)):
        return action.text


def _fallback_for_phase(state: GameState, seat: Seat, rng: DeterministicRNG) -> Action:
    stream = f"fallback:{state.phase}:seat{seat.number}:retry0"
    if state.phase == Phase.NIGHT_GUARD.value:
        candidates = tuple(
            candidate for candidate in state.alive_seats() if candidate != state.last_guard_target
        )
        return GuardProtect(actor=seat, target=rng.choice(stream, candidates))
    if state.phase == Phase.NIGHT_WOLF_CHAT.value:
        return WolfChatMessage(actor=seat, text="[沉默]")
    if state.phase == Phase.NIGHT_WOLF_VOTE.value:
        candidates = tuple(
            player.seat for player in state.alive_players() if player.role is not Role.WOLF
        )
        return WolfKillVote(actor=seat, target=rng.choice(stream, candidates))
    if state.phase == Phase.NIGHT_SEER.value:
        candidates = tuple(Seat(number) for number in range(1, 9) if number != seat.number)
        return SeerCheck(actor=seat, target=rng.choice(stream, candidates))
    if state.phase == Phase.DAY_SPEECH.value:
        return Speech(actor=seat, text="我没有更多信息")
    if state.phase == Phase.DAY_KNIGHT_INTERRUPT.value:
        return KnightChallenge(actor=seat, target=None)
    if state.phase == Phase.DAY_VOTE.value:
        return Vote(actor=seat, target=rng.choice(stream, state.alive_seats()))
    if state.phase == Phase.DAY_VOTE_PK.value:
        return PkVote(actor=seat, target=rng.choice(stream, state.pk_seats))
    if state.phase == Phase.DAY_LAST_WORDS.value:
        return LastWords(actor=seat, text="我没有遗言")
    return Speech(actor=seat, text="我没有更多信息")


def _maybe_knight_interrupt(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
) -> tuple[GameState, bool]:
    if state.knight_used:
        return state, False
    knight_seats = state.seats_by_role(Role.KNIGHT, alive_only=True)
    if not knight_seats:
        return state, False
    knight = knight_seats[0]
    previous_phase = state.phase
    challenge_state = state.with_phase(Phase.DAY_KNIGHT_INTERRUPT.value)
    action = _decide_with_fallback(
        challenge_state,
        config,
        agents[knight.number],
        event_log,
        knight,
        lambda agent, view: agent.decide_knight_challenge(view),
        rng,
    )
    if not isinstance(action, KnightChallenge) or action.target is None:
        return state.with_phase(previous_phase), False
    state = challenge_state
    state = _apply_and_log(state, action, config, rng, event_log)
    state, win_events = emit_win_check(state, phase=Phase.DAY_KNIGHT_INTERRUPT.value)
    event_log.append_all(win_events)
    if state.winner is None:
        state = advance_to_next_night(state)
    return state, True

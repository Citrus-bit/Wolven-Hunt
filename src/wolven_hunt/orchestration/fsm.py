from __future__ import annotations

from collections.abc import Callable, Mapping

from wolven_hunt.agents.interface import PlayerInterface
from wolven_hunt.config.schema import GameConfig, RuleSet
from wolven_hunt.core.actions import (
    Action,
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
from wolven_hunt.core.events import (
    Event,
    EventType,
    draft_event,
    hidden_visibility,
    public_visibility,
)
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
from wolven_hunt.llm.gateway import LLMErrorType, LLMFallbackRequired
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.validate import validate_action
from wolven_hunt.referee.view import PlayerView, build_view
from wolven_hunt.storage.event_log import EventLog

AgentMap = Mapping[int, PlayerInterface]
StateSink = Callable[[GameState], None]
ControlHook = Callable[[GameState], None]


def run_game(
    *,
    config: GameConfig,
    seed: str,
    agents: AgentMap,
    max_days: int = 20,
    event_sink: Callable[[Event], None] | None = None,
    event_log: EventLog | None = None,
    state_sink: StateSink | None = None,
    control_hook: ControlHook | None = None,
) -> tuple[GameState, EventLog]:
    rng = DeterministicRNG(seed)
    event_log = event_log if event_log is not None else EventLog(seed=seed, on_append=event_sink)
    state, start_events = build_initial_state(config, seed)
    event_log.append_all(start_events)
    _sync_runtime(state, state_sink, control_hook)

    while state.winner is None and state.day <= max_days:
        state = _run_night(
            state,
            config,
            agents,
            rng,
            event_log,
            state_sink=state_sink,
            control_hook=control_hook,
        )
        if state.winner is not None:
            break
        state = _run_day(
            state,
            config,
            agents,
            rng,
            event_log,
            state_sink=state_sink,
            control_hook=control_hook,
        )
        if state.winner is None:
            state = advance_to_next_night(state)
            _sync_runtime(state, state_sink, control_hook)
    if state.winner is None:
        # Deterministic guardrail for pathological mock strategies.
        state, win_events = emit_win_check(state, phase=Phase.GAME_END.value)
        event_log.append_all(win_events)
        _sync_runtime(state, state_sink, control_hook)
    return state, event_log


def _run_night(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
    *,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> GameState:
    state, events = phase_enter(state, Phase.NIGHT_START.value)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    event_log.append_all(phase_exit(state))

    guard_seats = state.seats_by_role(Role.GUARD, alive_only=True)
    if guard_seats:
        state = _enter_phase(state, Phase.NIGHT_GUARD, event_log, state_sink, control_hook)
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
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
        event_log.append_all(phase_exit(state))

    wolf_seats = state.wolf_seats(alive_only=True)
    if wolf_seats:
        state = _enter_phase(
            state,
            Phase.NIGHT_WOLF_CHAT,
            event_log,
            state_sink,
            control_hook,
        )
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
            state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
        event_log.append_all(phase_exit(state))

        state = _enter_phase(
            state,
            Phase.NIGHT_WOLF_VOTE,
            event_log,
            state_sink,
            control_hook,
        )
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
            state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
        event_log.append_all(phase_exit(state))

    witch_seats = state.seats_by_role(Role.WITCH, alive_only=True)
    if witch_seats and (not state.witch_antidote_used or not state.witch_poison_used):
        state = _enter_phase(state, Phase.NIGHT_WITCH, event_log, state_sink, control_hook)
        witch = witch_seats[0]
        action = _decide_with_fallback(
            state,
            config,
            agents[witch.number],
            event_log,
            witch,
            lambda agent, view: agent.decide_witch(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
        event_log.append_all(phase_exit(state))

    seer_seats = state.seats_by_role(Role.SEER, alive_only=True)
    if seer_seats:
        state = _enter_phase(state, Phase.NIGHT_SEER, event_log, state_sink, control_hook)
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
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
        event_log.append_all(phase_exit(state))

    state = _enter_phase(state, Phase.NIGHT_RESOLVE, event_log, state_sink, control_hook)
    state, events = resolve_night(state)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    event_log.append_all(phase_exit(state))
    state, events = emit_win_check(state, phase=Phase.CHECK_WIN_NIGHT.value)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    return state


def _run_day(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
    *,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> GameState:
    state = _enter_phase(state, Phase.DAY_ANNOUNCE, event_log, state_sink, control_hook)
    state, events = emit_day_announce(state)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    event_log.append_all(phase_exit(state))

    if state.day == 1 and state.first_night_deaths:
        state = _run_last_words(
            state,
            config,
            agents,
            rng,
            event_log,
            state.first_night_deaths,
            state_sink=state_sink,
            control_hook=control_hook,
        )

    state = _enter_phase(state, Phase.DAY_SPEECH, event_log, state_sink, control_hook)
    for seat in day_speech_order(state, config.rule_set):
        action = _decide_with_fallback(
            state,
            config,
            agents[seat.number],
            event_log,
            seat,
            lambda agent, view: agent.decide_speech(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
    event_log.append_all(phase_exit(state))

    state = _enter_phase(state, Phase.DAY_VOTE, event_log, state_sink, control_hook)
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
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
    state, vote_events = finish_vote(state)
    event_log.append_all(vote_events)
    _sync_runtime(state, state_sink, control_hook)
    exiled_seat = _exiled_seat_from_events(vote_events)
    event_log.append_all(phase_exit(state))

    if state.pk_seats:
        state = _enter_phase(state, Phase.DAY_VOTE_PK, event_log, state_sink, control_hook)
        exiled_seat = None
        voters = tuple(seat for seat in state.alive_seats() if seat not in state.pk_seats)
        if not voters:
            state, events = finish_pk_vote(state)
            event_log.append_all(events)
            _sync_runtime(state, state_sink, control_hook)
            exiled_seat = _exiled_seat_from_events(events)
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
                state = _apply_and_log(
                    state,
                    action,
                    config,
                    rng,
                    event_log,
                    state_sink,
                    control_hook,
                )
            state, events = finish_pk_vote(state)
            event_log.append_all(events)
            _sync_runtime(state, state_sink, control_hook)
            exiled_seat = _exiled_seat_from_events(events)
        event_log.append_all(phase_exit(state))

    if exiled_seat is not None:
        state = _run_last_words(
            state,
            config,
            agents,
            rng,
            event_log,
            (exiled_seat,),
            state_sink=state_sink,
            control_hook=control_hook,
        )

    state, events = emit_win_check(state, phase=Phase.CHECK_WIN_DAY.value)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    return state


def day_speech_order(state: GameState, rule_set: RuleSet) -> tuple[Seat, ...]:
    alive = tuple(sorted(state.alive_seats(), key=lambda seat: seat.number))
    if not alive:
        return ()
    if state.last_night_deaths:
        start_number = max(seat.number for seat in state.last_night_deaths) + 1
    else:
        start_number = rule_set.first_speaker_seat
    return tuple(seat for seat in alive if seat.number >= start_number) + tuple(
        seat for seat in alive if seat.number < start_number
    )


def _enter_phase(
    state: GameState,
    phase: Phase,
    event_log: EventLog,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> GameState:
    state, events = phase_enter(state, phase.value)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    return state


def _run_last_words(
    state: GameState,
    config: GameConfig,
    agents: AgentMap,
    rng: DeterministicRNG,
    event_log: EventLog,
    seats: tuple[Seat, ...],
    *,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> GameState:
    if not seats:
        return state
    state = _enter_phase(state, Phase.DAY_LAST_WORDS, event_log, state_sink, control_hook)
    for seat in seats:
        action = _decide_with_fallback(
            state,
            config,
            agents[seat.number],
            event_log,
            seat,
            lambda agent, view: agent.decide_last_words(view),
            rng,
        )
        state = _apply_and_log(state, action, config, rng, event_log, state_sink, control_hook)
    event_log.append_all(phase_exit(state))
    return state


def _exiled_seat_from_events(events: tuple[Event, ...]) -> Seat | None:
    for event in events:
        if event.type is not EventType.EXILE:
            continue
        seat = event.payload.get("seat")
        if isinstance(seat, bool):
            return None
        if isinstance(seat, int):
            return Seat(seat)
        if isinstance(seat, str):
            return Seat(int(seat))
    return None


def _apply_and_log(
    state: GameState,
    action: Action,
    config: GameConfig,
    rng: DeterministicRNG,
    event_log: EventLog,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> GameState:
    state, events = apply_action(state, action, config, rng)
    event_log.append_all(events)
    _sync_runtime(state, state_sink, control_hook)
    return state


def _sync_runtime(
    state: GameState,
    state_sink: StateSink | None,
    control_hook: ControlHook | None,
) -> None:
    if state_sink is not None:
        state_sink(state)
    if control_hook is not None:
        control_hook(state)


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
        _record_llm_call_if_present(state, agent, event_log, seat)
    except LLMFallbackRequired as exc:
        _record_llm_call_if_present(state, agent, event_log, seat)
        _record_llm_error(state, seat, event_log, exc)
        action = _fallback_for_phase(state, seat, rng, view)
        _record_fallback(state, seat, event_log, f"llm:{exc.error.type}", action)
        return action
    except Exception:
        _record_llm_call_if_present(state, agent, event_log, seat)
        action = _fallback_for_phase(state, seat, rng, view)
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
    action = _fallback_for_phase(state, seat, rng, view)
    _record_fallback(state, seat, event_log, reason, action)
    return action


def _record_llm_call_if_present(
    state: GameState,
    agent: PlayerInterface,
    event_log: EventLog,
    seat: Seat,
) -> None:
    consume = getattr(agent, "consume_last_call_result", None)
    if not callable(consume):
        return
    result = consume()
    if result is None:
        return
    event_log.append(
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.LLM_CALL,
            actor=seat.number,
            visibility=hidden_visibility(),
            payload=result.event_payload(),
        )
    )
    if result.budget_warning is not None:
        event_log.append(
            draft_event(
                game_id=state.game_id,
                phase=state.phase,
                day=state.day,
                event_type=EventType.AGENT_BUDGET_WARNING,
                actor=seat.number,
                visibility=public_visibility(),
                payload=result.budget_warning,
            )
        )


def _record_llm_error(
    state: GameState,
    seat: Seat,
    event_log: EventLog,
    exc: LLMFallbackRequired,
) -> None:
    timeout_like = {
        LLMErrorType.TIMEOUT,
        LLMErrorType.RATE_LIMIT,
        LLMErrorType.NETWORK,
    }
    event_type = (
        EventType.AGENT_TIMEOUT
        if exc.error.type in timeout_like
        else EventType.AGENT_INVALID_ACTION
    )
    event_log.append(
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=event_type,
            actor=seat.number,
            visibility=hidden_visibility(),
            payload={"error_type": exc.error.type.value, "message": exc.error.message},
        )
    )


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
    if isinstance(action, WitchAction):
        target = None if action.target is None else action.target.number
        return f"{action.action}:{target}"
    if isinstance(action, (Speech, LastWords, WolfChatMessage)):
        return action.text


def _fallback_for_phase(
    state: GameState,
    seat: Seat,
    rng: DeterministicRNG,
    view: PlayerView,
) -> Action:
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
    if state.phase == Phase.NIGHT_WITCH.value:
        return WitchAction(actor=seat, action="skip", target=None)
    if state.phase == Phase.NIGHT_SEER.value:
        candidates = tuple(player.seat for player in state.players if player.seat != seat)
        return SeerCheck(actor=seat, target=rng.choice(stream, candidates))
    if state.phase == Phase.DAY_SPEECH.value:
        return Speech(actor=seat, text=_contextual_public_speech(seat, view))
    if state.phase == Phase.DAY_VOTE.value:
        return Vote(actor=seat, target=rng.choice(stream, state.alive_seats()))
    if state.phase == Phase.DAY_VOTE_PK.value:
        return PkVote(actor=seat, target=rng.choice(stream, state.pk_seats))
    if state.phase == Phase.DAY_LAST_WORDS.value:
        return LastWords(actor=seat, text="我没有遗言")
    return Speech(actor=seat, text=_contextual_public_speech(seat, view))


def _contextual_public_speech(seat: Seat, view: PlayerView) -> str:
    current_day = view.rule_set_summary.get("day")
    speakers: list[int] = []
    seen: set[int] = set()
    for event in view.visible_events:
        if event.type is not EventType.SPEECH:
            continue
        if event.phase != Phase.DAY_SPEECH.value or event.day != current_day:
            continue
        if event.actor is None or event.actor == seat.number or event.actor in seen:
            continue
        speakers.append(event.actor)
        seen.add(event.actor)
    if not speakers:
        return (
            f"我是{seat.number}号。现在公开信息还少,我先关注夜晚公示和后续发言里的逻辑矛盾,"
            "投票会优先选择解释不清或强行带票的位置。"
        )
    focused = speakers[-2:]
    speaker_text = (
        f"{focused[0]}号" if len(focused) == 1 else f"{focused[0]}号和{focused[1]}号"
    )
    return (
        f"我是{seat.number}号。前面{speaker_text}的发言我会重点对照票型看,"
        "当前不报未公开信息,投票前优先找发言矛盾、跟票摇摆和解释不清的位置。"
    )

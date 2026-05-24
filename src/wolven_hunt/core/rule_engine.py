from __future__ import annotations

from collections import Counter
from dataclasses import replace

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
    public_visibility,
    seats_visibility,
)
from wolven_hunt.core.ids import GameId
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import ROLE_TO_CAMP, Role, Seat
from wolven_hunt.core.state import GameState, PlayerState
from wolven_hunt.core.win import check_winner


def build_initial_state(config: GameConfig, seed: str) -> tuple[GameState, tuple[Event, ...]]:
    rng = DeterministicRNG(seed)
    role_names: list[Role] = []
    for role_name, role_def in sorted(config.role_pack.roles.items()):
        role_names.extend([Role(role_name)] * role_def.count)
    rng.stream("role_assignment").shuffle(role_names)
    players = tuple(
        PlayerState(seat=Seat(index + 1), role=role) for index, role in enumerate(role_names)
    )
    game_id = GameId.deterministic(seed)
    state = GameState(
        game_id=game_id,
        config_hash=config.config_hash,
        seed=seed,
        players=players,
        day=1,
        phase="GAME_START",
    )
    payload = {
        "random_seed": seed,
        "config_hash": config.config_hash,
        "seat_range": {"start": config.seat_range.start, "end": config.seat_range.end},
        "role_assignment": {str(player.seat.number): player.role.value for player in players},
        "rng_stream": "role_assignment",
        "candidates": [role.value for role in role_names],
        "selected": {str(player.seat.number): player.role.value for player in players},
        "reason": "deterministic_role_shuffle",
    }
    return state, (
        draft_event(
            game_id=game_id,
            phase="GAME_START",
            day=1,
            event_type=EventType.GAME_START,
            actor=None,
            visibility=public_visibility(),
            payload=payload,
        ),
    )


def phase_enter(state: GameState, phase: str) -> tuple[GameState, tuple[Event, ...]]:
    new_state = state.with_phase(phase)
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=phase,
            day=state.day,
            event_type=EventType.PHASE_ENTER,
            actor=None,
            visibility=public_visibility(),
            payload={"phase": phase},
        ),
    )


def phase_exit(state: GameState) -> tuple[Event, ...]:
    alive_wolves, alive_good = state.alive_camp_counts()
    return (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.PHASE_EXIT,
            actor=None,
            visibility=public_visibility(),
            payload={
                "phase": state.phase,
                "alive_wolves": alive_wolves,
                "alive_good": alive_good,
                "alive_total": alive_wolves + alive_good,
            },
        ),
    )


def emit_win_check(
    state: GameState, *, phase: str, rule_set: RuleSet
) -> tuple[GameState, tuple[Event, ...]]:
    winner = check_winner(state, rule_set)
    new_state = replace(state, winner=winner)
    payload: dict[str, str | None] = {"winner": winner.value if winner is not None else None}
    events = [
        draft_event(
            game_id=state.game_id,
            phase=phase,
            day=state.day,
            event_type=EventType.WIN_CHECK,
            actor=None,
            visibility=public_visibility(),
            payload=payload,
        )
    ]
    if winner is not None:
        events.append(
            draft_event(
                game_id=state.game_id,
                phase="GAME_END",
                day=state.day,
                event_type=EventType.GAME_END,
                actor=None,
                visibility=public_visibility(),
                payload={"winner": winner.value},
            )
        )
    return new_state, tuple(events)


def apply_action(
    state: GameState,
    action: Action,
    config: GameConfig,
    rng: DeterministicRNG,
) -> tuple[GameState, tuple[Event, ...]]:
    if isinstance(action, GuardProtect):
        return _apply_guard(state, action)
    if isinstance(action, WolfChatMessage):
        return _apply_wolf_chat(state, action)
    if isinstance(action, WolfKillVote):
        return _apply_wolf_vote(state, action, rng)
    if isinstance(action, SeerCheck):
        return _apply_seer(state, action)
    if isinstance(action, Speech):
        return _apply_speech(state, action, config)
    if isinstance(action, WitchAction):
        return _apply_witch(state, action)
    if isinstance(action, Vote):
        return _apply_vote(state, action)
    if isinstance(action, PkVote):
        return _apply_pk_vote(state, action)
    if isinstance(action, LastWords):
        return _apply_last_words(state, action, config)


def resolve_night(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    events: list[Event] = []
    deaths: list[Seat] = []
    last_words_eligible: list[Seat] = []
    wolf_target = state.night_wolf_target
    witch_action = state.night_witch_action
    witch_target = state.night_witch_target

    if wolf_target is not None:
        saved_by_witch = witch_action == "save" and witch_target == wolf_target
        guarded_by_guard = state.night_guard_target == wolf_target
        if saved_by_witch and guarded_by_guard:
            deaths.append(wolf_target)
            if state.day == 1:
                last_words_eligible.append(wolf_target)
        elif saved_by_witch or guarded_by_guard:
            pass
        else:
            deaths.append(wolf_target)
            if state.day == 1:
                last_words_eligible.append(wolf_target)

    if witch_action == "poison" and witch_target is not None:
        if witch_target not in deaths:
            deaths.append(witch_target)
        if witch_target in last_words_eligible:
            last_words_eligible.remove(witch_target)

    if not deaths:
        events.append(
            draft_event(
                game_id=state.game_id,
                phase="NIGHT_RESOLVE",
                day=state.day,
                event_type=EventType.NO_DEATH_TONIGHT,
                actor=None,
                visibility=public_visibility(),
                payload={"message": "昨晚是平安夜"},
            )
        )
    else:
        for death in deaths:
            state = state.mark_dead(death, "NIGHT_RESOLVE")
            events.append(
                draft_event(
                    game_id=state.game_id,
                    phase="NIGHT_RESOLVE",
                    day=state.day,
                    event_type=EventType.DEATH_AT_NIGHT,
                    actor=None,
                    visibility=public_visibility(),
                    payload={"seat": death.number},
                )
            )
    last_night_deaths = tuple(deaths)
    first_night_deaths = tuple(last_words_eligible) if state.day == 1 else state.first_night_deaths
    new_state = replace(
        state,
        last_night_deaths=last_night_deaths,
        first_night_deaths=first_night_deaths,
        last_guard_target=state.night_guard_target,
        night_guard_target=None,
        night_wolf_votes=(),
        night_wolf_target=None,
        night_witch_action=None,
        night_witch_target=None,
    )
    return new_state, tuple(events)


def emit_day_announce(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    deaths = [seat.number for seat in state.last_night_deaths]
    message = "昨晚是平安夜" if not deaths else f"昨晚死亡玩家: {', '.join(map(str, deaths))}"
    return state, (
        draft_event(
            game_id=state.game_id,
            phase="DAY_ANNOUNCE",
            day=state.day,
            event_type=EventType.DAY_ANNOUNCE,
            actor=None,
            visibility=public_visibility(),
            payload={"deaths": deaths, "message": message},
        ),
    )


def finish_vote(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    if not state.votes:
        new_state = replace(state, votes=())
        return new_state, ()
    counts, abstentions = _vote_counts_and_abstentions(state.votes)
    tied = _tied_vote_targets(counts)
    events: list[Event] = [
        *_public_vote_cast_events(state, pk=False),
        draft_event(
            game_id=state.game_id,
            phase="DAY_VOTE",
            day=state.day,
            event_type=EventType.VOTE_RESULT,
            actor=None,
            visibility=public_visibility(),
            payload=_vote_result_payload(counts, tied, abstentions),
        ),
    ]
    if not counts:
        new_state, peaceful = _peaceful_day(state, phase="DAY_VOTE", reason="all_abstained")
        return new_state, tuple([*events, *peaceful])
    if len(tied) > 1:
        new_state = replace(state, pk_seats=tied, pk_round=1, votes=())
        events.append(
            draft_event(
                game_id=state.game_id,
                phase="DAY_VOTE_PK",
                day=state.day,
                event_type=EventType.VOTE_PK_ENTER,
                actor=None,
                visibility=public_visibility(),
                payload={"pk_seats": [seat.number for seat in tied]},
            )
        )
        return new_state, tuple(events)
    exiled = tied[0]
    new_state = state.mark_dead(exiled, "DAY_EXILE")
    new_state = replace(new_state, votes=(), pk_seats=(), pk_round=0)
    events.append(
        draft_event(
            game_id=state.game_id,
            phase="DAY_EXILE",
            day=state.day,
            event_type=EventType.EXILE,
            actor=None,
            visibility=public_visibility(),
            payload={"seat": exiled.number},
        )
    )
    return new_state, tuple(events)


def finish_pk_vote(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    if not state.pk_votes:
        return _peaceful_day(state, phase="DAY_VOTE_PK", reason="second_tie_or_no_voters")
    counts, abstentions = _vote_counts_and_abstentions(state.pk_votes)
    tied = _tied_vote_targets(counts)
    events: list[Event] = [
        *_public_vote_cast_events(state, pk=True),
        draft_event(
            game_id=state.game_id,
            phase="DAY_VOTE_PK",
            day=state.day,
            event_type=EventType.VOTE_RESULT,
            actor=None,
            visibility=public_visibility(),
            payload={
                **_vote_result_payload(counts, tied, abstentions),
                "pk_round": 2,
            },
        ),
    ]
    if not counts:
        new_state, peaceful = _peaceful_day(state, phase="DAY_VOTE_PK", reason="all_abstained")
        return new_state, tuple([*events, *peaceful])
    if len(tied) > 1:
        new_state, peaceful = _peaceful_day(
            state, phase="DAY_VOTE_PK", reason="second_tie_or_no_voters"
        )
        return new_state, tuple([*events, *peaceful])
    exiled = tied[0]
    new_state = state.mark_dead(exiled, "DAY_EXILE")
    new_state = replace(new_state, pk_votes=(), pk_seats=(), pk_round=0)
    events.append(
        draft_event(
            game_id=state.game_id,
            phase="DAY_EXILE",
            day=state.day,
            event_type=EventType.EXILE,
            actor=None,
            visibility=public_visibility(),
            payload={"seat": exiled.number},
        )
    )
    return new_state, tuple(events)


def _vote_counts_and_abstentions(
    votes: tuple[tuple[Seat, Seat | None], ...],
) -> tuple[Counter[int], tuple[Seat, ...]]:
    counts: Counter[int] = Counter()
    abstentions: list[Seat] = []
    for actor, target in votes:
        if target is None:
            abstentions.append(actor)
            continue
        counts[target.number] += 1
    return counts, tuple(sorted(abstentions, key=lambda seat: seat.number))


def _tied_vote_targets(counts: Counter[int]) -> tuple[Seat, ...]:
    if not counts:
        return ()
    max_votes = max(counts.values())
    return tuple(Seat(number) for number, count in sorted(counts.items()) if count == max_votes)


def _vote_result_payload(
    counts: Counter[int],
    tied: tuple[Seat, ...],
    abstentions: tuple[Seat, ...],
) -> dict[str, object]:
    return {
        "counts": {str(number): count for number, count in sorted(counts.items())},
        "tied": [seat.number for seat in tied],
        "abstain_count": len(abstentions),
        "abstentions": [seat.number for seat in abstentions],
    }


def _peaceful_day(
    state: GameState,
    *,
    phase: str,
    reason: str,
) -> tuple[GameState, tuple[Event, ...]]:
    new_state = replace(state, pk_votes=(), pk_seats=(), pk_round=0, votes=())
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=phase,
            day=state.day,
            event_type=EventType.PEACEFUL_DAY,
            actor=None,
            visibility=public_visibility(),
            payload={"reason": reason},
        ),
    )


def _public_vote_cast_events(state: GameState, *, pk: bool) -> tuple[Event, ...]:
    phase = "DAY_VOTE_PK" if pk else "DAY_VOTE"
    votes = state.pk_votes if pk else state.votes
    events: list[Event] = []
    for actor, target in sorted(votes, key=lambda vote: vote[0].number):
        payload: dict[str, object] = (
            {"target": None, "abstain": True}
            if target is None
            else {"target": target.number}
        )
        if pk:
            payload["pk"] = True
        events.append(
            draft_event(
                game_id=state.game_id,
                phase=phase,
                day=state.day,
                event_type=EventType.VOTE_CAST,
                actor=actor.number,
                visibility=public_visibility(),
                payload=payload,
            )
        )
    return tuple(events)


def advance_to_next_night(state: GameState) -> GameState:
    return replace(
        state,
        day=state.day + 1,
        phase="NIGHT_START",
        last_night_deaths=(),
        votes=(),
        pk_votes=(),
        pk_seats=(),
        pk_round=0,
    )


def _apply_guard(state: GameState, action: GuardProtect) -> tuple[GameState, tuple[Event, ...]]:
    new_state = replace(state, night_guard_target=action.target)
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.GUARD_PROTECT,
            actor=action.actor.number,
            visibility=seats_visibility((action.actor.number,)),
            payload={"target": action.target.number},
        ),
    )


def _apply_wolf_chat(
    state: GameState, action: WolfChatMessage
) -> tuple[GameState, tuple[Event, ...]]:
    wolves = tuple(seat.number for seat in state.wolf_seats())
    return state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.WOLF_CHAT_MESSAGE,
            actor=action.actor.number,
            visibility=seats_visibility(wolves),
            payload={"text": action.text},
        ),
    )


def _apply_wolf_vote(
    state: GameState, action: WolfKillVote, rng: DeterministicRNG
) -> tuple[GameState, tuple[Event, ...]]:
    wolves = tuple(seat.number for seat in state.wolf_seats())
    votes = (*state.night_wolf_votes, (action.actor, action.target))
    target: Seat | None = None
    events = [
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.WOLF_KILL_VOTE,
            actor=action.actor.number,
            visibility=seats_visibility(wolves),
            payload={"target": action.target.number},
        )
    ]
    alive_wolves = state.wolf_seats(alive_only=True)
    if len(votes) >= len(alive_wolves):
        counts = Counter(target.number for _, target in votes)
        max_votes = max(counts.values())
        tied = tuple(Seat(number) for number, count in sorted(counts.items()) if count == max_votes)
        if len(tied) == 1:
            target = tied[0]
        else:
            stream = f"wolf_tie:day{state.day}"
            target = rng.choice(stream, tied)
            events.append(
                draft_event(
                    game_id=state.game_id,
                    phase=state.phase,
                    day=state.day,
                    event_type=EventType.WOLF_TIE_RANDOM,
                    actor=None,
                    visibility=seats_visibility(wolves),
                    payload={
                        "rng_stream": stream,
                        "candidates": [seat.number for seat in tied],
                        "selected": target.number,
                        "reason": "wolf_kill_vote_tie",
                    },
                )
            )
        events.append(
            draft_event(
                game_id=state.game_id,
                phase=state.phase,
                day=state.day,
                event_type=EventType.WOLF_KILL_DECIDED,
                actor=None,
                visibility=seats_visibility(wolves),
                payload={"target": target.number},
            )
        )
    new_state = replace(state, night_wolf_votes=votes, night_wolf_target=target)
    return new_state, tuple(events)


def _apply_seer(state: GameState, action: SeerCheck) -> tuple[GameState, tuple[Event, ...]]:
    target = state.player(action.target)
    camp = ROLE_TO_CAMP[target.role]
    return state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.SEER_CHECK,
            actor=action.actor.number,
            visibility=seats_visibility((action.actor.number,)),
            payload={"target": action.target.number},
        ),
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.SEER_CHECK_RESULT,
            actor=action.actor.number,
            visibility=seats_visibility((action.actor.number,)),
            payload={"target": action.target.number, "camp": camp.value},
        ),
    )


def _apply_speech(
    state: GameState, action: Speech, config: GameConfig
) -> tuple[GameState, tuple[Event, ...]]:
    text = action.text[: config.rule_set.speech.max_chars]
    return state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.SPEECH,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"text": text},
        ),
    )


def _apply_witch(state: GameState, action: WitchAction) -> tuple[GameState, tuple[Event, ...]]:
    antidote_used = state.witch_antidote_used or action.action == "save"
    poison_used = state.witch_poison_used or action.action == "poison"
    new_state = replace(
        state,
        witch_antidote_used=antidote_used,
        witch_poison_used=poison_used,
        night_witch_action=action.action,
        night_witch_target=action.target,
    )
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.WITCH_ACTION,
            actor=action.actor.number,
            visibility=seats_visibility((action.actor.number,)),
            payload={
                "action": action.action,
                "target": None if action.target is None else action.target.number,
            },
        ),
    )


def _apply_vote(state: GameState, action: Vote) -> tuple[GameState, tuple[Event, ...]]:
    votes = (*state.votes, (action.actor, action.target))
    new_state = replace(state, votes=votes)
    return new_state, ()


def _apply_pk_vote(state: GameState, action: PkVote) -> tuple[GameState, tuple[Event, ...]]:
    votes = (*state.pk_votes, (action.actor, action.target))
    new_state = replace(state, pk_votes=votes)
    return new_state, ()


def _apply_last_words(
    state: GameState, action: LastWords, config: GameConfig
) -> tuple[GameState, tuple[Event, ...]]:
    text = action.text[: config.rule_set.speech.max_chars]
    return state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.LAST_WORDS,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"text": text},
        ),
    )


class RuleEngine:
    @staticmethod
    def apply(
        state: GameState,
        action: Action,
        config: GameConfig,
        rng: DeterministicRNG,
    ) -> tuple[GameState, tuple[Event, ...]]:
        return apply_action(state, action, config, rng)

    @staticmethod
    def start_game(config: GameConfig, seed: str) -> tuple[GameState, tuple[Event, ...]]:
        return build_initial_state(config, seed)


apply = apply_action

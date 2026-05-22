from __future__ import annotations

from collections import Counter
from dataclasses import replace

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


def emit_win_check(state: GameState, *, phase: str) -> tuple[GameState, tuple[Event, ...]]:
    winner = check_winner(state)
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
    if isinstance(action, KnightChallenge):
        return _apply_knight(state, action)
    if isinstance(action, Vote):
        return _apply_vote(state, action)
    if isinstance(action, PkVote):
        return _apply_pk_vote(state, action)
    if isinstance(action, LastWords):
        return _apply_last_words(state, action, config)


def resolve_night(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    events: list[Event] = []
    deaths: tuple[Seat, ...] = ()
    if state.night_wolf_target is None:
        new_state = replace(state, last_night_deaths=())
        return new_state, tuple(events)
    if state.night_guard_target == state.night_wolf_target:
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
        death = state.night_wolf_target
        deaths = (death,)
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
    first_night_deaths = deaths if state.day == 1 else state.first_night_deaths
    new_state = replace(
        state,
        last_night_deaths=deaths,
        first_night_deaths=first_night_deaths,
        last_guard_target=state.night_guard_target,
        night_guard_target=None,
        night_wolf_votes=(),
        night_wolf_target=None,
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
    counts = Counter(target.number for _, target in state.votes)
    if not counts:
        new_state = replace(state, votes=())
        return new_state, ()
    max_votes = max(counts.values())
    tied = tuple(Seat(number) for number, count in sorted(counts.items()) if count == max_votes)
    events: list[Event] = [
        draft_event(
            game_id=state.game_id,
            phase="DAY_VOTE",
            day=state.day,
            event_type=EventType.VOTE_RESULT,
            actor=None,
            visibility=public_visibility(),
            payload={
                "counts": {str(number): count for number, count in sorted(counts.items())},
                "tied": [seat.number for seat in tied],
            },
        )
    ]
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
        return _peaceful_day(state)
    counts = Counter(target.number for _, target in state.pk_votes)
    max_votes = max(counts.values())
    tied = tuple(Seat(number) for number, count in sorted(counts.items()) if count == max_votes)
    events: list[Event] = [
        draft_event(
            game_id=state.game_id,
            phase="DAY_VOTE_PK",
            day=state.day,
            event_type=EventType.VOTE_RESULT,
            actor=None,
            visibility=public_visibility(),
            payload={
                "counts": {str(number): count for number, count in sorted(counts.items())},
                "tied": [seat.number for seat in tied],
                "pk_round": 2,
            },
        )
    ]
    if len(tied) > 1:
        new_state, peaceful = _peaceful_day(state)
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


def _peaceful_day(state: GameState) -> tuple[GameState, tuple[Event, ...]]:
    new_state = replace(state, pk_votes=(), pk_seats=(), pk_round=0, votes=())
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase="DAY_VOTE_PK",
            day=state.day,
            event_type=EventType.PEACEFUL_DAY,
            actor=None,
            visibility=public_visibility(),
            payload={"reason": "second_tie_or_no_voters"},
        ),
    )


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


def _apply_knight(state: GameState, action: KnightChallenge) -> tuple[GameState, tuple[Event, ...]]:
    if action.target is None:
        return state, ()
    target = state.player(action.target)
    killed = action.target if target.role is Role.WOLF else action.actor
    result = "hit_wolf" if target.role is Role.WOLF else "hit_good"
    new_state = state.mark_dead(killed, "KNIGHT_CHALLENGE_RESOLVE")
    new_state = replace(new_state, knight_used=True)
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase="DAY_KNIGHT_INTERRUPT",
            day=state.day,
            event_type=EventType.KNIGHT_CHALLENGE,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"target": action.target.number},
        ),
        draft_event(
            game_id=state.game_id,
            phase="DAY_KNIGHT_INTERRUPT",
            day=state.day,
            event_type=EventType.KNIGHT_RESULT,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"result": result, "killed": killed.number},
        ),
    )


def _apply_vote(state: GameState, action: Vote) -> tuple[GameState, tuple[Event, ...]]:
    votes = (*state.votes, (action.actor, action.target))
    new_state = replace(state, votes=votes)
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.VOTE_CAST,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"target": action.target.number},
        ),
    )


def _apply_pk_vote(state: GameState, action: PkVote) -> tuple[GameState, tuple[Event, ...]]:
    votes = (*state.pk_votes, (action.actor, action.target))
    new_state = replace(state, pk_votes=votes)
    return new_state, (
        draft_event(
            game_id=state.game_id,
            phase=state.phase,
            day=state.day,
            event_type=EventType.VOTE_CAST,
            actor=action.actor.number,
            visibility=public_visibility(),
            payload={"target": action.target.number, "pk": True},
        ),
    )


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

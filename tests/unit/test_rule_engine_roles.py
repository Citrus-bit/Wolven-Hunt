from __future__ import annotations

from dataclasses import replace

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import (
    GuardProtect,
    LastWords,
    PkVote,
    SeerCheck,
    Speech,
    Vote,
    WitchAction,
    WolfKillVote,
)
from wolven_hunt.core.events import EventType
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import (
    apply_action,
    finish_pk_vote,
    finish_vote,
    resolve_night,
)
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.referee.validate import validate_action


def _seat_by_role(state: GameState, role: Role) -> Seat:
    return state.seats_by_role(role)[0]


def test_seer_check_result_is_camp_only(game_config: GameConfig, initial_state: GameState) -> None:
    seer = _seat_by_role(initial_state, Role.SEER)
    target = Seat(1 if seer.number != 1 else 2)
    state, events = apply_action(
        initial_state.with_phase("NIGHT_SEER"),
        SeerCheck(actor=seer, target=target),
        game_config,
        DeterministicRNG("x"),
    )
    assert state is not None
    result = next(event for event in events if event.type is EventType.SEER_CHECK_RESULT)
    assert set(result.payload) == {"target", "camp"}


def test_guard_consecutive_target_rejected(
    game_config: GameConfig, initial_state: GameState
) -> None:
    guard = _seat_by_role(initial_state, Role.GUARD)
    state = replace(initial_state, last_guard_target=Seat(1))
    rejection = validate_action(
        state, GuardProtect(actor=guard, target=Seat(1)), game_config.rule_set
    )
    assert rejection is not None
    assert rejection.rule_id == "guard.consecutive"


def test_guard_blocks_wolf_kill(game_config: GameConfig, initial_state: GameState) -> None:
    good_target = next(
        player.seat for player in initial_state.players if player.role is not Role.WOLF
    )
    state = replace(initial_state, night_guard_target=good_target, night_wolf_target=good_target)
    state, events = resolve_night(state)
    assert state.player(good_target).alive
    assert [event.type for event in events] == [EventType.NO_DEATH_TONIGHT]


def test_wolf_tie_random_event(game_config: GameConfig, initial_state: GameState) -> None:
    wolves = initial_state.wolf_seats(alive_only=True)
    targets = tuple(player.seat for player in initial_state.players if player.role is not Role.WOLF)
    state = initial_state.with_phase("NIGHT_WOLF_VOTE")
    rng = DeterministicRNG("wolf-tie")
    all_events = []
    for wolf, target in zip(wolves, targets, strict=False):
        state, events = apply_action(
            state, WolfKillVote(actor=wolf, target=target), game_config, rng
        )
        all_events.extend(events)
    tie_events = [event for event in all_events if event.type is EventType.WOLF_TIE_RANDOM]
    assert tie_events
    payload = tie_events[0].payload
    assert {"rng_stream", "candidates", "selected", "reason"} <= set(payload)


def test_wolf_cannot_kill_teammate(game_config: GameConfig, initial_state: GameState) -> None:
    wolf = initial_state.wolf_seats(alive_only=True)[0]
    teammate = initial_state.wolf_seats(alive_only=True)[1]
    rejection = validate_action(
        initial_state, WolfKillVote(actor=wolf, target=teammate), game_config.rule_set
    )
    assert rejection is not None
    assert rejection.rule_id == "wolf.target_teammate"


def test_witch_save_blocks_wolf_kill(game_config: GameConfig, initial_state: GameState) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    target = next(player.seat for player in initial_state.players if player.role is not Role.WOLF)
    state = replace(initial_state.with_phase("NIGHT_WITCH"), night_wolf_target=target)
    state, events = apply_action(
        state,
        WitchAction(actor=witch, action="save", target=target),
        game_config,
        DeterministicRNG("witch"),
    )
    assert state.witch_antidote_used
    assert events[0].type is EventType.WITCH_ACTION
    state, events = resolve_night(state)
    assert state.player(target).alive
    assert [event.type for event in events] == [EventType.NO_DEATH_TONIGHT]


def test_witch_poison_kills_and_guard_does_not_block(
    game_config: GameConfig, initial_state: GameState
) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    poison_target = next(
        player.seat
        for player in initial_state.players
        if player.role is not Role.WITCH and player.role is not Role.WOLF
    )
    state = replace(
        initial_state.with_phase("NIGHT_WITCH"),
        night_guard_target=poison_target,
    )
    state, _ = apply_action(
        state,
        WitchAction(actor=witch, action="poison", target=poison_target),
        game_config,
        DeterministicRNG("witch"),
    )
    state, events = resolve_night(state)
    assert not state.player(poison_target).alive
    assert [event.type for event in events] == [EventType.DEATH_AT_NIGHT]
    assert state.first_night_deaths == ()


def test_witch_double_heal_kills_target(game_config: GameConfig, initial_state: GameState) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    target = next(player.seat for player in initial_state.players if player.role is not Role.WOLF)
    state = replace(
        initial_state.with_phase("NIGHT_WITCH"),
        night_guard_target=target,
        night_wolf_target=target,
    )
    state, _ = apply_action(
        state,
        WitchAction(actor=witch, action="save", target=target),
        game_config,
        DeterministicRNG("witch"),
    )
    state, events = resolve_night(state)
    assert not state.player(target).alive
    assert [event.type for event in events] == [EventType.DEATH_AT_NIGHT]
    assert state.first_night_deaths == (target,)


def test_witch_same_night_poison_and_wolf_kill_two_deaths(
    game_config: GameConfig, initial_state: GameState
) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    targets = tuple(player.seat for player in initial_state.players if player.role is not Role.WOLF)
    wolf_target = targets[0]
    poison_target = next(seat for seat in targets if seat != wolf_target and seat != witch)
    state = replace(initial_state.with_phase("NIGHT_WITCH"), night_wolf_target=wolf_target)
    state, _ = apply_action(
        state,
        WitchAction(actor=witch, action="poison", target=poison_target),
        game_config,
        DeterministicRNG("witch"),
    )
    state, events = resolve_night(state)
    assert [event.payload["seat"] for event in events] == [
        wolf_target.number,
        poison_target.number,
    ]
    assert not state.player(wolf_target).alive
    assert not state.player(poison_target).alive
    assert state.first_night_deaths == (wolf_target,)


def test_witch_poison_and_wolf_kill_same_target_denies_last_words(
    game_config: GameConfig, initial_state: GameState
) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    target = next(
        player.seat
        for player in initial_state.players
        if player.role is not Role.WOLF and player.role is not Role.WITCH
    )
    state = replace(initial_state.with_phase("NIGHT_WITCH"), night_wolf_target=target)
    state, _ = apply_action(
        state,
        WitchAction(actor=witch, action="poison", target=target),
        game_config,
        DeterministicRNG("witch"),
    )
    state, events = resolve_night(state)
    assert [event.payload["seat"] for event in events] == [target.number]
    assert not state.player(target).alive
    assert state.first_night_deaths == ()


def test_witch_cannot_use_two_potions_in_same_night(
    game_config: GameConfig, initial_state: GameState
) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    save_target = next(
        player.seat for player in initial_state.players if player.role is not Role.WOLF
    )
    poison_target = next(
        player.seat
        for player in initial_state.players
        if player.role is not Role.WOLF
        and player.role is not Role.WITCH
        and player.seat != save_target
    )
    state = replace(initial_state.with_phase("NIGHT_WITCH"), night_wolf_target=save_target)
    state, _ = apply_action(
        state,
        WitchAction(actor=witch, action="save", target=save_target),
        game_config,
        DeterministicRNG("witch"),
    )
    rejection = validate_action(
        state,
        WitchAction(actor=witch, action="poison", target=poison_target),
        game_config.rule_set,
    )
    assert rejection is not None
    assert rejection.rule_id == "witch.night_limit"


def test_witch_invalid_actions_rejected(game_config: GameConfig, initial_state: GameState) -> None:
    witch = _seat_by_role(initial_state, Role.WITCH)
    target = next(player.seat for player in initial_state.players if player.role is not Role.WOLF)
    state = replace(initial_state.with_phase("NIGHT_WITCH"), night_wolf_target=target)

    save_rejection = validate_action(
        state,
        WitchAction(
            actor=witch,
            action="save",
            target=Seat(1 if target.number != 1 else 2),
        ),
        game_config.rule_set,
    )
    assert save_rejection is not None
    assert save_rejection.rule_id == "witch.save_target"

    poison_rejection = validate_action(
        state,
        WitchAction(actor=witch, action="poison", target=witch),
        game_config.rule_set,
    )
    assert poison_rejection is not None
    assert poison_rejection.rule_id == "witch.poison_self"


def test_vote_self_and_dead_target_rules(game_config: GameConfig, initial_state: GameState) -> None:
    actor = initial_state.alive_seats()[0]
    assert (
        validate_action(initial_state, Vote(actor=actor, target=actor), game_config.rule_set)
        is None
    )
    dead_state = initial_state.mark_dead(Seat(1), "test")
    rejection = validate_action(dead_state, Vote(actor=actor, target=Seat(1)), game_config.rule_set)
    assert rejection is not None


def test_vote_tie_enters_pk(game_config: GameConfig, initial_state: GameState) -> None:
    voters = initial_state.alive_seats()[:2]
    state = replace(initial_state, votes=((voters[0], Seat(1)), (voters[1], Seat(2))))
    state, events = finish_vote(state)
    assert state.pk_seats == (Seat(1), Seat(2))
    assert any(event.type is EventType.VOTE_PK_ENTER for event in events)


def test_pk_second_tie_is_peaceful(game_config: GameConfig, initial_state: GameState) -> None:
    state = replace(
        initial_state,
        pk_seats=(Seat(1), Seat(2)),
        pk_votes=((Seat(3), Seat(1)), (Seat(4), Seat(2))),
    )
    state, events = finish_pk_vote(state)
    assert state.pk_seats == ()
    assert any(event.type is EventType.PEACEFUL_DAY for event in events)


def test_text_actions_emit_public_events(game_config: GameConfig, initial_state: GameState) -> None:
    seat = initial_state.alive_seats()[0]
    _, speech = apply_action(
        initial_state.with_phase("DAY_SPEECH"),
        Speech(actor=seat, text="hello"),
        game_config,
        DeterministicRNG("text"),
    )
    _, last_words = apply_action(
        initial_state.with_phase("DAY_LAST_WORDS"),
        LastWords(actor=seat, text="bye"),
        game_config,
        DeterministicRNG("text"),
    )
    assert speech[0].type is EventType.SPEECH
    assert last_words[0].type is EventType.LAST_WORDS


def test_pk_player_cannot_vote(game_config: GameConfig, initial_state: GameState) -> None:
    state = replace(initial_state, pk_seats=(Seat(1), Seat(2)))
    rejection = validate_action(state, PkVote(actor=Seat(1), target=Seat(2)), game_config.rule_set)
    assert rejection is not None
    assert rejection.rule_id == "pk.actor_on_stage"

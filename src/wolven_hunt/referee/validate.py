from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from wolven_hunt.config.schema import RuleSet
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
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState


@dataclass(frozen=True, slots=True)
class Reject:
    rule_id: str
    message: str


ValidationResult: TypeAlias = None | Reject


def validate_action(state: GameState, action: Action, rule_set: RuleSet) -> ValidationResult:
    seat_reject = _validate_action_seats(state, action)
    if seat_reject is not None:
        return seat_reject
    if isinstance(action, GuardProtect):
        return _validate_guard(state, action, rule_set)
    if isinstance(action, WolfChatMessage):
        return _validate_text(state, action.actor, action.text, rule_set, expected_role=Role.WOLF)
    if isinstance(action, WolfKillVote):
        return _validate_wolf_vote(state, action, rule_set)
    if isinstance(action, SeerCheck):
        return _validate_seer(state, action, rule_set)
    if isinstance(action, Speech):
        return _validate_text(state, action.actor, action.text, rule_set, expected_role=None)
    if isinstance(action, WitchAction):
        return _validate_witch(state, action, rule_set)
    if isinstance(action, Vote):
        return _validate_vote(state, action, rule_set)
    if isinstance(action, PkVote):
        return _validate_pk_vote(state, action, rule_set)
    if isinstance(action, LastWords):
        return _validate_text(state, action.actor, action.text, rule_set, expected_role=None)


def _validate_action_seats(state: GameState, action: Action) -> ValidationResult:
    seats = [action.actor]
    target = getattr(action, "target", None)
    if target is not None:
        seats.append(target)
    for seat in seats:
        if not state.has_seat(seat):
            return Reject("seat.range", f"seat {seat.number} is not in this game")
    return None


def _validate_guard(state: GameState, action: GuardProtect, rule_set: RuleSet) -> ValidationResult:
    actor = state.player(action.actor)
    target = state.player(action.target)
    if actor.role is not Role.GUARD:
        return Reject("guard.actor_role", "only guard can protect")
    if not actor.alive:
        return Reject("guard.actor_alive", "dead guard cannot protect")
    if not target.alive:
        return Reject("guard.target_alive", "guard target must be alive")
    if action.actor == action.target and not rule_set.guard.can_guard_self:
        return Reject("guard.self", "guard cannot guard self")
    if (
        not rule_set.guard.can_guard_same_target_consecutive_nights
        and state.last_guard_target == action.target
    ):
        return Reject("guard.consecutive", "guard cannot protect same target consecutively")
    return None


def _validate_wolf_vote(
    state: GameState, action: WolfKillVote, rule_set: RuleSet
) -> ValidationResult:
    actor = state.player(action.actor)
    target = state.player(action.target)
    if actor.role is not Role.WOLF:
        return Reject("wolf.actor_role", "only wolf can vote to kill")
    if not actor.alive:
        return Reject("wolf.actor_alive", "dead wolf cannot vote")
    if not target.alive:
        return Reject("wolf.target_alive", "wolf kill target must be alive")
    if target.role is Role.WOLF and not rule_set.wolves.can_kill_wolf_teammate:
        return Reject("wolf.target_teammate", "wolf cannot kill wolf teammate")
    if action.actor == action.target:
        return Reject("wolf.self", "wolf cannot kill self")
    return None


def _validate_seer(state: GameState, action: SeerCheck, rule_set: RuleSet) -> ValidationResult:
    actor = state.player(action.actor)
    target = state.player(action.target)
    if actor.role is not Role.SEER:
        return Reject("seer.actor_role", "only seer can check")
    if not actor.alive:
        return Reject("seer.actor_alive", "dead seer cannot check")
    if action.actor == action.target and not rule_set.seer.can_check_self:
        return Reject("seer.self", "seer cannot check self")
    if not target.alive and not rule_set.seer.can_check_dead:
        return Reject("seer.dead", "seer cannot check dead target")
    return None


def _validate_witch(state: GameState, action: WitchAction, rule_set: RuleSet) -> ValidationResult:
    actor = state.player(action.actor)
    if actor.role is not Role.WITCH:
        return Reject("witch.actor_role", "only witch can use potions")
    if not actor.alive:
        return Reject("witch.actor_alive", "dead witch cannot use potions")
    if action.action == "skip":
        if action.target is not None:
            return Reject("witch.skip_target", "skip must not include target")
        return None
    if action.target is None:
        return Reject("witch.target_required", "witch potion action requires target")
    if rule_set.witch.max_potions_per_night <= 1 and state.night_witch_action in {
        "save",
        "poison",
    }:
        return Reject("witch.night_limit", "witch can use at most one potion per night")
    target = state.player(action.target)
    if not target.alive:
        return Reject("witch.target_alive", "witch target must be alive")
    if action.action == "save":
        if state.witch_antidote_used:
            return Reject("witch.antidote_used", "witch antidote already used")
        if action.target != state.night_wolf_target:
            return Reject("witch.save_target", "witch can only save wolf kill target")
        return None
    if action.action == "poison":
        if state.witch_poison_used:
            return Reject("witch.poison_used", "witch poison already used")
        if action.actor == action.target and not rule_set.witch.poison_can_target_self:
            return Reject("witch.poison_self", "witch cannot poison self")
        return None
    return Reject("witch.action", "unknown witch action")


def _validate_vote(state: GameState, action: Vote, rule_set: RuleSet) -> ValidationResult:
    actor = state.player(action.actor)
    if not actor.alive:
        return Reject("vote.actor_alive", "dead player cannot vote")
    if action.target is None:
        if rule_set.vote.can_abstain:
            return None
        return Reject("vote.abstain", "abstain disabled")
    target = state.player(action.target)
    if not target.alive:
        return Reject("vote.target_alive", "vote target must be alive")
    if action.actor == action.target and not rule_set.vote.can_vote_self:
        return Reject("vote.self", "self vote disabled")
    return None


def _validate_pk_vote(state: GameState, action: PkVote, rule_set: RuleSet) -> ValidationResult:
    actor = state.player(action.actor)
    if not actor.alive:
        return Reject("pk.actor_alive", "dead player cannot pk vote")
    if action.actor in state.pk_seats:
        return Reject("pk.actor_on_stage", "pk players cannot vote in pk round")
    if action.target is None:
        if rule_set.vote.can_abstain:
            return None
        return Reject("pk.abstain", "abstain disabled")
    target = state.player(action.target)
    if action.target not in state.pk_seats:
        return Reject("pk.target_not_on_stage", "pk vote target must be on stage")
    if not target.alive:
        return Reject("pk.target_alive", "pk target must be alive")
    return None


def _validate_text(
    state: GameState,
    actor_seat: Seat,
    text: str,
    rule_set: RuleSet,
    *,
    expected_role: Role | None,
) -> ValidationResult:
    actor = state.player(actor_seat)
    if expected_role is not None and actor.role is not expected_role:
        return Reject("text.actor_role", f"expected {expected_role.value}")
    if not actor.alive and state.phase != "DAY_LAST_WORDS":
        return Reject("text.actor_alive", "dead player cannot speak")
    if len(text) > rule_set.speech.max_chars:
        return Reject("text.max_chars", "text exceeds max_chars")
    return None

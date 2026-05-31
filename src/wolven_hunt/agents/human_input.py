from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, TypeVar, cast

from wolven_hunt.agents.interface import PlayerInterface
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
from wolven_hunt.core.seat import Seat
from wolven_hunt.referee.view import PlayerView

TAction = TypeVar("TAction", bound=Action)


class PendingActionQueue(Protocol):
    def pop(self, kind: str, seat: Seat, *, timeout_seconds: float) -> Action | None: ...


class TurnHooks(Protocol):
    def set_turn_request(
        self,
        *,
        seat: Seat,
        kind: str,
        deadline_ts: float,
        timeout_seconds: float,
        valid_targets: tuple[int, ...] | None,
        constraints: dict[str, object],
        phase: str,
        day: int,
    ) -> None: ...

    def clear_turn_request(self, *, seat: Seat, kind: str) -> None: ...


class HumanInputAgent:
    def __init__(
        self,
        *,
        seat: Seat,
        base: PlayerInterface,
        pending: PendingActionQueue,
        session_hooks: TurnHooks,
        timeout_seconds: float = 90.0,
    ) -> None:
        self._seat = seat
        self._base = base
        self._pending = pending
        self._hooks = session_hooks
        self._timeout_seconds = timeout_seconds

    def decide_guard(self, view: PlayerView) -> GuardProtect:
        return self._await_human(
            "guard",
            view,
            expected_type=GuardProtect,
            fallback=lambda: self._base.decide_guard(view),
        )

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        return self._await_human(
            "wolf_chat",
            view,
            expected_type=WolfChatMessage,
            fallback=lambda: self._base.decide_wolf_chat(view),
        )

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote:
        return self._await_human(
            "wolf_vote",
            view,
            expected_type=WolfKillVote,
            fallback=lambda: self._base.decide_wolf_vote(view),
        )

    def decide_seer(self, view: PlayerView) -> SeerCheck:
        return self._await_human(
            "seer",
            view,
            expected_type=SeerCheck,
            fallback=lambda: self._base.decide_seer(view),
        )

    def decide_speech(self, view: PlayerView) -> Speech:
        return self._await_human(
            "speech",
            view,
            expected_type=Speech,
            fallback=lambda: self._base.decide_speech(view),
        )

    def decide_witch(self, view: PlayerView) -> WitchAction:
        return self._await_human(
            "witch",
            view,
            expected_type=WitchAction,
            fallback=lambda: self._base.decide_witch(view),
        )

    def decide_vote(self, view: PlayerView) -> Vote:
        return self._await_human(
            "vote",
            view,
            expected_type=Vote,
            fallback=lambda: self._base.decide_vote(view),
        )

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        return self._await_human(
            "pk_vote",
            view,
            expected_type=PkVote,
            fallback=lambda: self._base.decide_pk_vote(view),
        )

    def decide_last_words(self, view: PlayerView) -> LastWords:
        return self._await_human(
            "last_words",
            view,
            expected_type=LastWords,
            fallback=lambda: self._base.decide_last_words(view),
        )

    def consume_last_call_result(self) -> object | None:
        consume = getattr(self._base, "consume_last_call_result", None)
        if not callable(consume):
            return None
        result = consume()
        if result is None:
            return None
        return cast(object, result)

    def set_retry_feedback(self, error_type: str, message: str) -> None:
        setter = getattr(self._base, "set_retry_feedback", None)
        if callable(setter):
            setter(error_type, message)

    def _await_human(
        self,
        kind: str,
        view: PlayerView,
        *,
        expected_type: type[TAction],
        fallback: Callable[[], TAction],
    ) -> TAction:
        deadline_ts = time.time() + self._timeout_seconds
        valid_targets, constraints = _turn_shape(kind, self._seat, view)
        self._hooks.set_turn_request(
            seat=self._seat,
            kind=kind,
            deadline_ts=deadline_ts,
            timeout_seconds=self._timeout_seconds,
            valid_targets=valid_targets,
            constraints=constraints,
            phase=str(view.rule_set_summary.get("phase", "")),
            day=int(view.rule_set_summary.get("day", 0)),
        )
        try:
            action = self._pending.pop(
                kind,
                self._seat,
                timeout_seconds=self._timeout_seconds,
            )
        finally:
            self._hooks.clear_turn_request(seat=self._seat, kind=kind)
        if isinstance(action, expected_type):
            return action
        return fallback()


def _turn_shape(
    kind: str,
    seat: Seat,
    view: PlayerView,
) -> tuple[tuple[int, ...] | None, dict[str, object]]:
    summary = view.rule_set_summary
    alive = tuple(int(value) for value in summary.get("alive_seats", ()))
    constraints: dict[str, object] = {}
    if kind in {"speech", "wolf_chat", "last_words"}:
        constraints["max_chars"] = int(summary.get("max_chars", 300))
        return None, constraints
    if kind == "guard":
        last_guard_target = summary.get("last_guard_target")
        return tuple(target for target in alive if target != last_guard_target), constraints
    if kind == "seer":
        seat_range = cast(dict[str, int], summary["seat_range"])
        seat_start = seat_range["start"]
        seat_end = seat_range["end"]
        return tuple(target for target in range(seat_start, seat_end + 1) if target != seat.number), constraints
    if kind == "witch":
        constraints["wolf_kill_target"] = summary.get("wolf_kill_target")
        constraints["antidote_available"] = bool(summary.get("witch_antidote_available"))
        constraints["poison_available"] = bool(summary.get("witch_poison_available"))
        return alive, constraints
    if kind == "wolf_vote":
        teammates = {teammate.number for teammate in view.teammates}
        can_kill_self = bool(summary.get("wolf_can_kill_self"))
        can_kill_teammate = bool(summary.get("wolf_can_kill_teammate"))
        constraints["can_no_kill"] = bool(summary.get("wolf_can_no_kill"))
        return tuple(
            target
            for target in alive
            if target not in teammates
            or (target == seat.number and can_kill_self)
            or (target in teammates and can_kill_teammate)
        ), constraints
    if kind == "vote":
        constraints["can_abstain"] = bool(summary.get("can_abstain"))
        constraints["can_vote_self"] = bool(summary.get("can_vote_self"))
        return alive, constraints
    if kind == "pk_vote":
        constraints["can_abstain"] = bool(summary.get("can_abstain"))
        return tuple(int(value) for value in summary.get("pk_seats", ())), constraints
    return None, constraints

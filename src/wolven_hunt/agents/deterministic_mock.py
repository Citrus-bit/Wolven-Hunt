from __future__ import annotations

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
from wolven_hunt.core.events import EventType
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.referee.view import PlayerView


class DeterministicMockAgent:
    def __init__(self, seat: Seat) -> None:
        self.seat = seat

    def decide_guard(self, view: PlayerView) -> GuardProtect:
        alive = _alive_seats(view)
        last_guard = view.rule_set_summary.get("last_guard_target")
        if view.rule_set_summary["day"] == 1 and self.seat.number in alive:
            return GuardProtect(actor=self.seat, target=self.seat)
        candidates = [seat for seat in alive if seat != last_guard]
        return GuardProtect(actor=self.seat, target=Seat(candidates[0]))

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        target = self._first_alive_non_teammate(view)
        return WolfChatMessage(
            actor=self.seat, text=f"(狼)我是 {self.seat.number} 号, 今晚刀 {target.number} 号"
        )

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote:
        return WolfKillVote(actor=self.seat, target=self._first_alive_non_teammate(view))

    def decide_seer(self, view: PlayerView) -> SeerCheck:
        checked = {
            int(event.payload["target"])
            for event in view.visible_events
            if event.type is EventType.SEER_CHECK and event.actor == self.seat.number
        }
        seats = _seat_numbers(view)
        for number in seats:
            if number != self.seat.number and number not in checked:
                return SeerCheck(actor=self.seat, target=Seat(number))
        fallback = seats[0] if self.seat.number != seats[0] else seats[min(1, len(seats) - 1)]
        return SeerCheck(actor=self.seat, target=Seat(fallback))

    def decide_speech(self, view: PlayerView) -> Speech:
        role_text = "狼人" if view.self_role is Role.WOLF else "好人"
        return Speech(actor=self.seat, text=f"我是 {self.seat.number} 号{role_text}")

    def decide_witch(self, view: PlayerView) -> WitchAction:
        return WitchAction(actor=self.seat, action="skip", target=None)

    def decide_vote(self, view: PlayerView) -> Vote:
        alive = _alive_seats(view)
        for number in alive:
            if number != self.seat.number:
                return Vote(actor=self.seat, target=Seat(number))
        return Vote(actor=self.seat, target=self.seat)

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        pk_seats = list(view.rule_set_summary["pk_seats"])
        return PkVote(actor=self.seat, target=Seat(int(pk_seats[0])))

    def decide_last_words(self, view: PlayerView) -> LastWords:
        return LastWords(actor=self.seat, text="我没有遗言")

    def _first_alive_non_teammate(self, view: PlayerView) -> Seat:
        teammate_numbers = {seat.number for seat in view.teammates}
        teammate_numbers.add(self.seat.number)
        for number in _alive_seats(view):
            if number not in teammate_numbers:
                return Seat(number)
        return self.seat


def _alive_seats(view: PlayerView) -> list[int]:
    return [int(number) for number in view.rule_set_summary["alive_seats"]]


def _seat_numbers(view: PlayerView) -> list[int]:
    seat_range = view.rule_set_summary.get("seat_range", {})
    if isinstance(seat_range, dict):
        start = _positive_int(seat_range.get("start"))
        end = _positive_int(seat_range.get("end"))
        if start > 0 and end >= start:
            return list(range(start, end + 1))
    seat_count = _positive_int(view.rule_set_summary.get("seat_count"))
    if seat_count > 0:
        return list(range(1, seat_count + 1))
    return _alive_seats(view)


def _positive_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0

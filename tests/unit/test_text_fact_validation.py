from __future__ import annotations

from dataclasses import replace

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import LastWords
from wolven_hunt.core.events import Event, EventType, draft_event, seats_visibility
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.referee.text_validate import validate_text_consistency


def test_guard_rejects_impossible_consecutive_self_claim(
    game_config: GameConfig,
    initial_state: GameState,
) -> None:
    guard = initial_state.seats_by_role(Role.GUARD)[0]
    other = _other_alive_seat(initial_state, guard)
    state = replace(initial_state, day=3, phase="DAY_LAST_WORDS")
    events = _guard_events(state, guard, (guard, other, guard))

    rejection = validate_text_consistency(
        state,
        LastWords(
            actor=guard,
            text="我连续两晚守护自己成功,保证了神职安全。",
        ),
        game_config.rule_set,
        events,
    )

    assert rejection is not None
    assert rejection.rule_id == "text.guard_consecutive_claim"


def test_guard_rejects_false_own_guard_history(
    game_config: GameConfig,
    initial_state: GameState,
) -> None:
    guard = initial_state.seats_by_role(Role.GUARD)[0]
    other = _other_alive_seat(initial_state, guard)
    state = replace(initial_state, day=3, phase="DAY_LAST_WORDS")
    events = _guard_events(state, guard, (guard, other, guard))

    rejection = validate_text_consistency(
        state,
        LastWords(actor=guard, text="我第二晚守护自己,第三晚守护自己。"),
        game_config.rule_set,
        events,
    )

    assert rejection is not None
    assert rejection.rule_id == "text.guard_history_mismatch"


def test_guard_allows_uncertain_success_language(
    game_config: GameConfig,
    initial_state: GameState,
) -> None:
    guard = initial_state.seats_by_role(Role.GUARD)[0]
    other = _other_alive_seat(initial_state, guard)
    state = replace(initial_state, day=3, phase="DAY_LAST_WORDS")
    events = _guard_events(state, guard, (guard, other, guard))

    rejection = validate_text_consistency(
        state,
        LastWords(actor=guard, text="我第三晚守护自己,可能守住了刀,但不能确定。"),
        game_config.rule_set,
        events,
    )

    assert rejection is None


def _guard_events(
    state: GameState,
    guard: Seat,
    targets: tuple[Seat, ...],
) -> tuple[Event, ...]:
    return tuple(
        draft_event(
            game_id=state.game_id,
            phase="NIGHT_GUARD",
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

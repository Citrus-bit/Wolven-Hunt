from __future__ import annotations

from dataclasses import replace

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import LastWords, Speech
from wolven_hunt.core.events import (
    Event,
    EventType,
    draft_event,
    public_visibility,
    seats_visibility,
)
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


def test_day_speech_rejects_future_speaker_not_reporting_check_claim(
    game_config: GameConfig,
    initial_state: GameState,
) -> None:
    state = replace(initial_state, day=2, phase="DAY_SPEECH")
    events = (
        _speech_event(state, seq=1, actor=Seat(1), text="我先听前置位发言。"),
        _speech_event(state, seq=2, actor=Seat(4), text="我怀疑前面票型摇摆。"),
    )

    rejection = validate_text_consistency(
        state,
        Speech(actor=Seat(4), text="6号连续两晚平安夜却一直不报第二晚查验,悍跳面进一步坐实。"),
        game_config.rule_set,
        events,
    )

    assert rejection is not None
    assert rejection.rule_id == "text.future_speaker_claim"


def test_day_speech_allows_check_claim_comment_after_target_spoke(
    game_config: GameConfig,
    initial_state: GameState,
) -> None:
    state = replace(initial_state, day=2, phase="DAY_SPEECH")
    events = (
        _speech_event(state, seq=1, actor=Seat(4), text="我怀疑前面票型摇摆。"),
        _speech_event(state, seq=2, actor=Seat(6), text="我是预言家,昨晚没有验到关键狼坑。"),
    )

    rejection = validate_text_consistency(
        state,
        Speech(actor=Seat(7), text="6号刚才没有报清第二晚查验目标,这点需要解释。"),
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


def _speech_event(state: GameState, *, seq: int, actor: Seat, text: str) -> Event:
    event = draft_event(
        game_id=state.game_id,
        phase="DAY_SPEECH",
        day=state.day,
        event_type=EventType.SPEECH,
        actor=actor.number,
        visibility=public_visibility(),
        payload={"text": text},
    )
    return event.model_copy(update={"seq": seq})


def _other_alive_seat(state: GameState, seat: Seat) -> Seat:
    return next(player.seat for player in state.players if player.alive and player.seat != seat)

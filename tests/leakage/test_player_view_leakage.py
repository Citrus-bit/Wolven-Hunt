from __future__ import annotations

import pytest
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.referee.view import PlayerView, build_view


@pytest.mark.leakage
def test_private_events_do_not_leak(game_config: GameConfig) -> None:
    state, event_log = simulate(game_config, "leakage")
    spectator = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=None)
    assert all(event.visibility.public for event in spectator.visible_events)
    assert not _has_any(
        spectator,
        {
            EventType.WOLF_CHAT_MESSAGE,
            EventType.WOLF_KILL_VOTE,
            EventType.WOLF_KILL_DECIDED,
            EventType.WOLF_TIE_RANDOM,
            EventType.SEER_CHECK,
            EventType.SEER_CHECK_RESULT,
            EventType.GUARD_PROTECT,
        },
    )

    for number in range(1, 9):
        seat = Seat(number)
        player = state.player(seat)
        view = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=seat)
        assert not _has_any(
            view,
            {
                EventType.AGENT_FALLBACK_TRIGGERED,
                EventType.AGENT_INVALID_ACTION,
                EventType.AGENT_TIMEOUT,
                EventType.LLM_CALL,
            },
        )
        game_start = view.visible_events[0]
        assert "role_assignment" not in game_start.payload
        if player.role is not Role.WOLF:
            assert not _has_any(
                view,
                {
                    EventType.WOLF_CHAT_MESSAGE,
                    EventType.WOLF_KILL_VOTE,
                    EventType.WOLF_KILL_DECIDED,
                    EventType.WOLF_TIE_RANDOM,
                },
            )
        if player.role is not Role.SEER:
            assert not _has_any(view, {EventType.SEER_CHECK, EventType.SEER_CHECK_RESULT})
        if player.role is not Role.GUARD:
            assert not _has_any(view, {EventType.GUARD_PROTECT})


def _has_any(view: PlayerView, event_types: set[EventType]) -> bool:
    return any(event.type in event_types for event in view.visible_events)

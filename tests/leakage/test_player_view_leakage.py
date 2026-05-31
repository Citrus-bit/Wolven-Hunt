from __future__ import annotations

from dataclasses import replace

import pytest
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.referee.view import PlayerView, build_view


@pytest.mark.leakage
def test_private_events_do_not_leak(game_config: GameConfig) -> None:
    state, event_log = simulate(game_config, "leakage")
    spectator = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=None)
    game_start = spectator.visible_events[0]
    assert "role_assignment" in game_start.payload
    assert "selected" not in game_start.payload
    assert "candidates" not in game_start.payload
    assert "last_guard_target" not in spectator.rule_set_summary
    assert any(event.type is EventType.WOLF_CHAT_MESSAGE for event in spectator.visible_events)
    assert not _has_any(
        spectator,
        {
            EventType.WOLF_KILL_VOTE,
            EventType.WOLF_KILL_DECIDED,
            EventType.WOLF_TIE_RANDOM,
            EventType.SEER_CHECK,
            EventType.SEER_CHECK_RESULT,
            EventType.GUARD_PROTECT,
            EventType.WITCH_ACTION,
        },
    )

    for number in range(game_config.seat_range.start, game_config.seat_range.end + 1):
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
        assert "last_guard_target" not in view.rule_set_summary
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
        if player.role is not Role.WITCH:
            assert not _has_any(view, {EventType.WITCH_ACTION})
            assert "wolf_kill_target" not in view.rule_set_summary
            assert "witch_antidote_available" not in view.rule_set_summary
            assert "witch_poison_available" not in view.rule_set_summary


@pytest.mark.leakage
def test_last_guard_target_only_visible_to_guard_during_guard_phase(
    game_config: GameConfig,
) -> None:
    state, events = build_initial_state(game_config, "last-guard-target-leakage")
    guard = state.seats_by_role(Role.GUARD)[0]
    non_guard = next(player.seat for player in state.players if player.seat != guard)
    state = replace(state, phase="NIGHT_GUARD", last_guard_target=Seat(2))

    spectator = build_view(state, events, rule_set=game_config.rule_set, seat=None)
    non_guard_view = build_view(state, events, rule_set=game_config.rule_set, seat=non_guard)
    guard_view = build_view(state, events, rule_set=game_config.rule_set, seat=guard)
    guard_day_view = build_view(
        replace(state, phase="DAY_SPEECH"),
        events,
        rule_set=game_config.rule_set,
        seat=guard,
    )

    assert "last_guard_target" not in spectator.rule_set_summary
    assert "last_guard_target" not in non_guard_view.rule_set_summary
    assert guard_view.rule_set_summary["last_guard_target"] == 2
    assert "last_guard_target" not in guard_day_view.rule_set_summary


@pytest.mark.leakage
def test_wolf_kill_target_only_visible_to_witch_during_witch_phase(
    game_config: GameConfig,
) -> None:
    state, events = build_initial_state(game_config, "witch-wolf-kill-target-leakage")
    witch = state.seats_by_role(Role.WITCH)[0]
    non_witch = next(player.seat for player in state.players if player.seat != witch)
    state = replace(state, phase="NIGHT_WITCH", night_wolf_target=Seat(2))

    spectator = build_view(state, events, rule_set=game_config.rule_set, seat=None)
    non_witch_view = build_view(state, events, rule_set=game_config.rule_set, seat=non_witch)
    witch_view = build_view(state, events, rule_set=game_config.rule_set, seat=witch)
    witch_day_view = build_view(
        replace(state, phase="DAY_SPEECH"),
        events,
        rule_set=game_config.rule_set,
        seat=witch,
    )
    private_keys = {
        "wolf_kill_target",
        "witch_antidote_available",
        "witch_poison_available",
    }

    assert private_keys.isdisjoint(spectator.rule_set_summary)
    assert private_keys.isdisjoint(non_witch_view.rule_set_summary)
    assert witch_view.rule_set_summary["wolf_kill_target"] == 2
    assert witch_view.rule_set_summary["witch_antidote_available"] is True
    assert witch_view.rule_set_summary["witch_poison_available"] is True
    assert private_keys.isdisjoint(witch_day_view.rule_set_summary)


def _has_any(view: PlayerView, event_types: set[EventType]) -> bool:
    return any(event.type in event_types for event in view.visible_events)

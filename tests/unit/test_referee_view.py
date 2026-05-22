from __future__ import annotations

from tests.conftest import simulate

from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.referee.view import build_view


def test_spectator_does_not_see_private_events(game_config: GameConfig) -> None:
    state, event_log = simulate(game_config, "ref-view")
    view = build_view(state, event_log.events, rule_set=game_config.rule_set, seat=None)
    private = {EventType.SEER_CHECK_RESULT, EventType.GUARD_PROTECT, EventType.WOLF_CHAT_MESSAGE}
    assert not any(event.type in private for event in view.visible_events)


def test_wolf_view_sees_wolf_chat(game_config: GameConfig) -> None:
    state, _ = build_initial_state(game_config, "wolf-view")
    wolf = state.wolf_seats()[0]
    agents = {seat: DeterministicMockAgent(Seat(seat)) for seat in range(1, 9)}
    final_state, log = run_game(config=game_config, seed="wolf-view", agents=agents)
    view = build_view(final_state, log.events, rule_set=game_config.rule_set, seat=wolf)
    assert any(event.type is EventType.WOLF_CHAT_MESSAGE for event in view.visible_events)


def test_player_game_start_is_sanitized(game_config: GameConfig) -> None:
    state, events = build_initial_state(game_config, "sanitize")
    seer = state.seats_by_role(Role.SEER)[0]
    view = build_view(state, events, rule_set=game_config.rule_set, seat=seer)
    payload = view.visible_events[0].payload
    assert "role_assignment" not in payload
    assert payload["self_role"] == Role.SEER.value

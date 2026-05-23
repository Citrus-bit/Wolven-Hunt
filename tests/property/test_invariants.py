from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.referee.view import build_view
from wolven_hunt.referee.visibility import SPECTATOR_VISIBLE_PRIVATE_EVENT_TYPES


@pytest.mark.property
@settings(
    max_examples=50, deadline=1500, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
        max_size=24,
    )
)
def test_simulation_invariants(game_config: GameConfig, seed_text: str) -> None:
    state, event_log = simulate(game_config, seed_text)
    events = event_log.events
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert len(state.players) == game_config.role_pack.seat_count
    assert sum(1 for event in events if event.type is EventType.GAME_END) == 1
    for event in events:
        if event.type is EventType.PHASE_EXIT:
            assert (
                event.payload["alive_wolves"] + event.payload["alive_good"]
                == event.payload["alive_total"]
            )
    spectator = build_view(state, events, rule_set=game_config.rule_set, seat=None)
    assert all(
        event.visibility.public or event.type in SPECTATOR_VISIBLE_PRIVATE_EVENT_TYPES
        for event in spectator.visible_events
    )
    assert [event.seq for event in spectator.visible_events] == sorted(
        event.seq for event in spectator.visible_events
    )

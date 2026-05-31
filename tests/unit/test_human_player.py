from __future__ import annotations

from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Role


def test_forced_role_keeps_role_counts_and_assigns_requested_role(game_config) -> None:
    expected_counts = {"wolf": 3, "villager": 4, "seer": 1, "witch": 1, "guard": 1}

    for role in Role:
        state, events = build_initial_state(
            game_config,
            f"forced-role-{role.value}",
            forced_seat_roles={7: role},
        )

        assert state.player(state.players[6].seat).role is role
        assert state.role_counts() == expected_counts
        assert events[0].payload["forced_seat_roles"] == {"7": role.value}


def test_empty_forced_roles_matches_default_initial_state(game_config) -> None:
    default_state, default_events = build_initial_state(game_config, "forced-role-random")
    forced_state, forced_events = build_initial_state(
        game_config,
        "forced-role-random",
        forced_seat_roles={},
    )

    assert forced_state == default_state
    assert forced_events[0].payload == default_events[0].payload

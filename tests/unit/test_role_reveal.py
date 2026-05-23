from __future__ import annotations

from dataclasses import replace

from wolven_hunt.core.seat import Camp
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.referee.reveal import build_role_reveal


def test_role_reveal_not_generated_before_winner(initial_state) -> None:
    assert build_role_reveal(initial_state) is None


def test_role_reveal_contains_all_seats_and_highlights(game_config, seed, mock_agents) -> None:
    state, event_log = run_game(config=game_config, seed=seed, agents=mock_agents)
    finished = replace(state, winner=Camp.WOLF)

    reveal = build_role_reveal(finished, event_log.events)

    assert reveal is not None
    assert reveal.type.value == "role_reveal"
    assert reveal.visibility.public is True
    assert reveal.payload["winner"] == "wolf"
    assert len(reveal.payload["seats"]) == game_config.role_pack.seat_count
    assert 3 <= len(reveal.payload["highlights"]) <= 5

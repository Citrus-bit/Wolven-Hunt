from __future__ import annotations

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Role
from wolven_hunt.orchestration.fsm import _wolf_fallback_kill_candidates
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.view import build_view


def test_wolf_fallback_kill_candidates_allow_self_but_exclude_teammates(
    game_config: GameConfig,
) -> None:
    state, events = build_initial_state(game_config, "wolf-fallback-candidates")
    state = state.with_phase(Phase.NIGHT_WOLF_VOTE.value)
    wolf = state.wolf_seats(alive_only=True)[0]
    teammates = set(state.wolf_seats(alive_only=True)) - {wolf}
    view = build_view(state, events, rule_set=game_config.rule_set, seat=wolf)

    candidates = _wolf_fallback_kill_candidates(state, wolf, view)

    assert wolf in candidates
    assert all(teammate not in candidates for teammate in teammates)
    assert all(state.player(candidate).alive for candidate in candidates)
    assert any(state.player(candidate).role is not Role.WOLF for candidate in candidates)

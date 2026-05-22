from __future__ import annotations

from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.events import EventType
from wolven_hunt.storage.jsonl import events_to_jsonl
from wolven_hunt.storage.replay import replay_deterministic


def test_fsm_runs_100_seeded_games(game_config: GameConfig) -> None:
    for index in range(100):
        state, event_log = simulate(game_config, f"integration-seed-{index:03d}")
        events = event_log.events
        assert state.winner is not None
        assert events[-1].type is EventType.GAME_END
        assert events[-1].payload["winner"] in {"wolf", "good"}
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        assert sum(1 for event in events if event.type is EventType.GAME_END) == 1
        for event in events:
            if event.type is EventType.PHASE_EXIT:
                assert (
                    event.payload["alive_wolves"] + event.payload["alive_good"]
                    == event.payload["alive_total"]
                )
        assert replay_deterministic(events) == events


def test_same_seed_is_byte_identical(game_config: GameConfig) -> None:
    _, first = simulate(game_config, "same-seed")
    _, second = simulate(game_config, "same-seed")
    assert events_to_jsonl(first.events) == events_to_jsonl(second.events)

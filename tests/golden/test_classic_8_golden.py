from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.storage.jsonl import events_to_jsonl

FIXTURE = Path(__file__).resolve().parent / "fixtures/classic_8_seed_001.events.jsonl"


@pytest.mark.golden
def test_classic_8_golden(game_config: GameConfig) -> None:
    _, event_log = simulate(game_config, "wolven-hunt-golden-seed-001")
    current = events_to_jsonl(event_log.events)
    if os.environ.get("WOLVEN_HUNT_UPDATE_GOLDEN") == "1":
        FIXTURE.write_text(current, encoding="utf-8")
    assert FIXTURE.read_text(encoding="utf-8") == current

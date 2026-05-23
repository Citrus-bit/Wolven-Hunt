from __future__ import annotations

from pathlib import Path

import pytest

from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
from wolven_hunt.config.loader import load_game_config
from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.storage.event_log import EventLog

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/games/classic_10.yaml"


@pytest.fixture
def game_config() -> GameConfig:
    return load_game_config(CONFIG_PATH)


@pytest.fixture(autouse=True)
def default_pacing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WH_PACING_PROFILE", "off")


@pytest.fixture
def seed() -> str:
    return "wolven-hunt-test-seed-001"


@pytest.fixture
def initial_state(game_config: GameConfig, seed: str) -> GameState:
    state, _ = build_initial_state(game_config, seed)
    return state


@pytest.fixture
def mock_agents(game_config: GameConfig) -> dict[int, DeterministicMockAgent]:
    return _mock_agents_for_config(game_config)


@pytest.fixture
def event_log(seed: str) -> EventLog:
    return EventLog(seed=seed)


def simulate(game_config: GameConfig, seed_value: str) -> tuple[GameState, EventLog]:
    agents = _mock_agents_for_config(game_config)
    return run_game(config=game_config, seed=seed_value, agents=agents)


def _mock_agents_for_config(game_config: GameConfig) -> dict[int, DeterministicMockAgent]:
    return {
        seat: DeterministicMockAgent(Seat(seat))
        for seat in range(game_config.seat_range.start, game_config.seat_range.end + 1)
    }

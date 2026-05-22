from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wolven_hunt.config.settings import Settings
from wolven_hunt.orchestration.runtime import GameRegistry


@pytest.mark.llm
def test_mock_llm_agent_runs_seeded_games(tmp_path: Path) -> None:
    registry = GameRegistry(
        settings=Settings(runs_dir=tmp_path, llm_provider="mock", pacing_profile="off")
    )

    for index in range(20):
        session = asyncio.run(
            _create_finished_session(
                registry,
                seed=f"llm-agent-seed-{index:03d}",
                agent_specs={seat: "llm:mock" for seat in range(1, 9)},
            )
        )

        assert session.state.winner is not None
        assert session.store.events_path.exists()
        assert session.store.raw_responses_path.exists()
        assert session.store.raw_responses_path.read_text(encoding="utf-8")


async def _create_finished_session(
    registry: GameRegistry,
    *,
    seed: str,
    agent_specs: dict[int, str],
):
    session = await registry.create_game(
        config_path=Path("configs/games/classic_8.yaml"),
        seed=seed,
        agent_specs=agent_specs,
    )
    assert session.task is not None
    await session.task
    return session

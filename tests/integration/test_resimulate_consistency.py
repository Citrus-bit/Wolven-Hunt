from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from wolven_hunt.config.settings import Settings
from wolven_hunt.orchestration.runtime import GameRegistry
from wolven_hunt.storage.replay import ResimulateDivergence, replay_resimulate

CONFIG_PATH = Path("configs/games/classic_10.yaml")
SEATS = range(1, 11)


@pytest.mark.llm
def test_resimulate_accepts_persisted_mock_llm_run(tmp_path: Path) -> None:
    registry = GameRegistry(
        settings=Settings(runs_dir=tmp_path, llm_provider="mock", pacing_profile="off")
    )
    session = asyncio.run(_create_finished_session(registry, seed="resimulate-seed-001"))

    events = replay_resimulate(session.store.events_path, session.store.raw_responses_path)

    assert tuple(event.seq for event in events) == tuple(
        event.seq for event in session.event_log.events
    )


@pytest.mark.llm
def test_resimulate_reports_tampered_raw_response(tmp_path: Path) -> None:
    registry = GameRegistry(
        settings=Settings(runs_dir=tmp_path, llm_provider="mock", pacing_profile="off")
    )
    session = asyncio.run(_create_finished_session(registry, seed="resimulate-seed-002"))
    lines = session.store.raw_responses_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["raw_response"] = '{"target":8}'
    lines[0] = json.dumps(first, ensure_ascii=False)
    session.store.raw_responses_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ResimulateDivergence) as exc_info:
        replay_resimulate(session.store.events_path, session.store.raw_responses_path)

    assert exc_info.value.field == "raw_response_hash"


async def _create_finished_session(registry: GameRegistry, *, seed: str):
    session = await registry.create_game(
        config_path=CONFIG_PATH,
        seed=seed,
        agent_specs={seat: "llm:mock" for seat in SEATS},
    )
    assert session.task is not None
    await session.task
    return session

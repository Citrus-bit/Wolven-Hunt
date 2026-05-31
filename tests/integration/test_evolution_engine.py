from __future__ import annotations

import json
import shutil
from pathlib import Path

from wolven_hunt.config.prompts import DEFAULT_PROMPT_VERSION
from wolven_hunt.config.settings import Settings
from wolven_hunt.evolution.engine import record_finished_game, step
from wolven_hunt.evolution.state import load_state

ROOT = Path(__file__).resolve().parents[2]


def test_mock_window_generates_challenger_snapshot(tmp_path: Path, game_config) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(game_config.prompt_pack_root, prompt_root)
    config_path = _write_config_with_prompt_root(tmp_path, prompt_root)
    settings = Settings(runs_dir=tmp_path / "runs", evolution_enabled=True)
    for index in range(5):
        game_id = f"game-{index}"
        _write_review_run(
            settings.runs_dir / game_id,
            game_id,
            prompt_version=DEFAULT_PROMPT_VERSION,
            seer_score=50,
        )
        record_finished_game(
            runs_dir=settings.runs_dir,
            game_id=game_id,
            prompt_version=DEFAULT_PROMPT_VERSION,
            window_size=5,
        )
    result = step(config_path=config_path, settings=settings, dry_run=False)
    state = load_state(settings.runs_dir)
    assert result["event"] == "challenger_generated"
    assert state.active_version == "v7"
    assert state.challenger_version == "v7"
    assert (prompt_root / "seer" / "night_action.v7.md").exists()


def test_dry_run_does_not_write_snapshot_or_state(tmp_path: Path, game_config) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(game_config.prompt_pack_root, prompt_root)
    config_path = _write_config_with_prompt_root(tmp_path, prompt_root)
    settings = Settings(runs_dir=tmp_path / "runs", evolution_enabled=True)
    for index in range(5):
        game_id = f"game-{index}"
        _write_review_run(
            settings.runs_dir / game_id,
            game_id,
            prompt_version=DEFAULT_PROMPT_VERSION,
            seer_score=50,
        )
        record_finished_game(
            runs_dir=settings.runs_dir,
            game_id=game_id,
            prompt_version=DEFAULT_PROMPT_VERSION,
            window_size=5,
        )
    result = step(config_path=config_path, settings=settings, dry_run=True)
    assert result["dry_run"] is True
    assert not (prompt_root / "seer" / "night_action.v7.md").exists()
    assert load_state(settings.runs_dir).active_version == DEFAULT_PROMPT_VERSION


def test_record_finished_game_ignores_human_player_runs(tmp_path: Path) -> None:
    settings = Settings(runs_dir=tmp_path / "runs", evolution_enabled=True)
    game_id = "human-game"
    run_root = settings.runs_dir / game_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "ended_at": "2026-01-01T00:00:00+00:00",
                "prompt_pack_version": DEFAULT_PROMPT_VERSION,
                "human_seat": 4,
                "seat_presentation": {},
            }
        ),
        encoding="utf-8",
    )

    state = record_finished_game(
        runs_dir=settings.runs_dir,
        game_id=game_id,
        prompt_version=DEFAULT_PROMPT_VERSION,
        window_size=5,
    )

    assert state.baseline_game_ids == ()
    assert state.challenger_game_ids == ()
    ledger_path = settings.runs_dir / "_evolution" / "ledger.jsonl"
    ledger_rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert ledger_rows[-1] | {"timestamp": "<ignored>"} == {
        "timestamp": "<ignored>",
        "event": "game_ignored",
        "game_id": game_id,
        "reason": "human_player",
        "human_seat": 4,
    }


def _write_config_with_prompt_root(tmp_path: Path, prompt_root: Path) -> Path:
    configs_root = tmp_path / "configs"
    shutil.copytree(ROOT / "configs/games", configs_root / "games")
    shutil.copytree(ROOT / "configs/models", configs_root / "models")
    source = configs_root / "games" / "classic_10.yaml"
    text = source.read_text(encoding="utf-8")
    text = text.replace("../prompts/zh", str(prompt_root))
    target = configs_root / "games" / "classic_10.yaml"
    target.write_text(text, encoding="utf-8")
    return target


def _write_review_run(
    root: Path,
    game_id: str,
    *,
    prompt_version: str,
    seer_score: int,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "ended_at": "2026-01-01T00:00:00+00:00",
                "prompt_pack_version": prompt_version,
                "seat_presentation": {},
            }
        ),
        encoding="utf-8",
    )
    (root / "events.jsonl").write_text("", encoding="utf-8")
    (root / "raw_responses.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "review_report.json").write_text(
        json.dumps(_review_report(game_id=game_id, seer_score=seer_score), ensure_ascii=False),
        encoding="utf-8",
    )


def _review_report(*, game_id: str, seer_score: int) -> dict[str, object]:
    roles = ["wolf", "wolf", "wolf", "villager", "villager", "villager", "villager", "seer", "witch", "guard"]
    return {
        "schema_version": "1.1",
        "game_id": game_id,
        "players": [
            {
                "seat": index,
                "role": role,
                "scores": [
                    {"key": "speech", "value": 80},
                    {"key": "reasoning", "value": 80},
                    {"key": "voting", "value": 80},
                    {"key": "camp_contribution", "value": 80},
                    {"key": "information_control", "value": 80},
                    {
                        "key": "role_duty",
                        "value": seer_score if role == "seer" else 80,
                    },
                ],
                "mistakes": ["mistake"],
                "suggestions": ["suggestion"],
            }
            for index, role in enumerate(roles, start=1)
        ],
        "counterfactuals": [],
    }

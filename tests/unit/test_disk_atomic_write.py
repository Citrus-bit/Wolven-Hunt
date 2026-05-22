from __future__ import annotations

import json
import stat

from wolven_hunt.storage.disk import GameRunStore


def test_game_run_store_writes_private_jsonl_and_manifest(tmp_path) -> None:
    store = GameRunStore(runs_dir=tmp_path, game_id="game-001")
    store.append_raw_response({"storage_ref": "llm/1", "raw_response": "{}"})
    store.write_manifest({"config_hash": "abc", "seed": "seed"})

    assert (
        json.loads(store.raw_responses_path.read_text(encoding="utf-8"))["storage_ref"] == "llm/1"
    )
    assert json.loads(store.manifest_path.read_text(encoding="utf-8"))["config_hash"] == "abc"
    assert stat.S_IMODE(store.raw_responses_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.manifest_path.stat().st_mode) == 0o600

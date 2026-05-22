from __future__ import annotations

# ruff: noqa: RUF001
import hashlib
import json
from pathlib import Path


def test_audio_manifest_contains_copied_game_media() -> None:
    manifest = json.loads(
        Path("public/assets/game/audio_manifest.json").read_text(encoding="utf-8")
    )
    expected_sources = {
        "wolf_howl": "狼嚎.mp3",
        "night_guard": "天黑了，守卫请睁眼.mp3",
        "night_wolves": "狼人请睁眼.mp3",
        "night_seer": "预言家请睁眼.mp3",
        "day_rooster": "鸡鸣.mp3",
        "day_dawn": "天,亮了.mp3",
        "day_death": "昨晚,他死了.mp3",
        "day_peaceful": "昨晚,是平安夜.mp3",
        "knight_duel": "骑士对决.mp4",
    }

    assert set(expected_sources) <= set(manifest)
    for key, source_name in expected_sources.items():
        source_hash = _sha256(Path("素材") / source_name)
        target_path = Path("public") / str(manifest[key]["path"]).removeprefix("/")
        assert manifest[key]["source_sha256"] == source_hash
        assert manifest[key]["target_sha256"] == _sha256(target_path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

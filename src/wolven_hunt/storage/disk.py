from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from wolven_hunt.core.events import Event

FILE_MODE = 0o600


class GameRunStore:
    def __init__(self, *, runs_dir: Path, game_id: str) -> None:
        self.root = runs_dir / game_id
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.events_path,
            self.raw_responses_path,
            self.cost_path,
            self.narrative_path,
        ):
            _touch_private(path)

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def raw_responses_path(self) -> Path:
        return self.root / "raw_responses.jsonl"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def cost_path(self) -> Path:
        return self.root / "cost.jsonl"

    @property
    def narrative_path(self) -> Path:
        return self.root / "narrative.jsonl"

    @property
    def final_reveal_path(self) -> Path:
        return self.root / "final_reveal.json"

    def append_event(self, event: Event) -> None:
        append_jsonl(self.events_path, event.model_dump(mode="json"))

    def append_raw_response(self, row: dict[str, object]) -> None:
        append_jsonl(self.raw_responses_path, row)

    def append_cost(self, row: dict[str, object]) -> None:
        append_jsonl(self.cost_path, row)

    def append_narrative(self, row: dict[str, object]) -> None:
        append_jsonl(self.narrative_path, row)

    def write_final_reveal(self, payload: dict[str, Any]) -> None:
        atomic_write_json(self.final_reveal_path, payload)

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        atomic_write_json(self.manifest_path, manifest)


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    _touch_private(path)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, FILE_MODE)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, FILE_MODE)
        os.replace(tmp_path, path)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    os.chmod(path, FILE_MODE)


def _touch_private(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
    os.close(fd)
    os.chmod(path, FILE_MODE)

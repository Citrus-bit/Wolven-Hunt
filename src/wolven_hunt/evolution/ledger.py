from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wolven_hunt.storage.disk import append_jsonl

from .state import evolution_root


def ledger_path(runs_dir: Path) -> Path:
    return evolution_root(runs_dir) / "ledger.jsonl"


def append_ledger(runs_dir: Path, row: dict[str, Any]) -> None:
    payload: dict[str, object] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        **row,
    }
    append_jsonl(ledger_path(runs_dir), payload)


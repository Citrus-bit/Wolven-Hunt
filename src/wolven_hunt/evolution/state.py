from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from wolven_hunt.config.prompts import DEFAULT_PROMPT_VERSION
from wolven_hunt.storage.disk import atomic_write_json

STATE_SCHEMA_VERSION = "1.0"
SEED_VERSION = DEFAULT_PROMPT_VERSION

CycleStatus = Literal["collecting_baseline", "testing_challenger"]


@dataclass(frozen=True, slots=True)
class EvolutionState:
    active_version: str = SEED_VERSION
    champion_version: str = SEED_VERSION
    challenger_version: str | None = None
    status: CycleStatus = "collecting_baseline"
    target_axis: str | None = None
    baseline_game_ids: tuple[str, ...] = ()
    challenger_game_ids: tuple[str, ...] = ()
    next_version: int = 7
    rejected_versions: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "active_version": self.active_version,
            "champion_version": self.champion_version,
            "challenger_version": self.challenger_version,
            "status": self.status,
            "target_axis": self.target_axis,
            "baseline_game_ids": list(self.baseline_game_ids),
            "challenger_game_ids": list(self.challenger_game_ids),
            "next_version": self.next_version,
            "rejected_versions": list(self.rejected_versions),
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> EvolutionState:
        return cls(
            active_version=_str_value(data.get("active_version"), SEED_VERSION),
            champion_version=_str_value(data.get("champion_version"), SEED_VERSION),
            challenger_version=_optional_str(data.get("challenger_version")),
            status=_status_value(data.get("status")),
            target_axis=_optional_str(data.get("target_axis")),
            baseline_game_ids=_str_tuple(data.get("baseline_game_ids")),
            challenger_game_ids=_str_tuple(data.get("challenger_game_ids")),
            next_version=_int_value(data.get("next_version"), 7),
            rejected_versions=_str_tuple(data.get("rejected_versions")),
        )


def evolution_root(runs_dir: Path) -> Path:
    return runs_dir / "_evolution"


def state_path(runs_dir: Path) -> Path:
    return evolution_root(runs_dir) / "state.json"


def load_state(runs_dir: Path) -> EvolutionState:
    path = state_path(runs_dir)
    if not path.exists():
        return EvolutionState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return EvolutionState()
    if not isinstance(data, dict):
        return EvolutionState()
    return EvolutionState.from_json(data)


def save_state(runs_dir: Path, state: EvolutionState) -> None:
    atomic_write_json(state_path(runs_dir), state.to_json())


def active_prompt_version(runs_dir: Path, *, enabled: bool) -> str:
    if not enabled:
        return SEED_VERSION
    return load_state(runs_dir).active_version


def _str_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _int_value(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _status_value(value: object) -> CycleStatus:
    return value if value in ("collecting_baseline", "testing_challenger") else "collecting_baseline"

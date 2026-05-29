from __future__ import annotations

import difflib
import tempfile
from dataclasses import replace
from pathlib import Path

from wolven_hunt.config.loader import ensure_prompt_version, load_game_config
from wolven_hunt.config.settings import Settings

from .axes import axis_from_key
from .evolver import evolve_prompt
from .gate import evaluate_gate
from .ledger import append_ledger
from .scoring import score_window, weakest_axis
from .snapshot import (
    create_snapshot,
    create_snapshot_in_dir,
    next_version_from_files,
    prompt_file,
    seed_char_cap,
)
from .state import EvolutionState, load_state, save_state


def record_finished_game(
    *,
    runs_dir: Path,
    game_id: str,
    prompt_version: str,
    window_size: int,
) -> EvolutionState:
    state = load_state(runs_dir)
    if prompt_version != state.active_version:
        append_ledger(
            runs_dir,
            {
                "event": "game_ignored",
                "game_id": game_id,
                "prompt_version": prompt_version,
                "active_version": state.active_version,
            },
        )
        return state
    if state.status == "testing_challenger":
        if game_id in state.challenger_game_ids:
            return state
        state = replace(
            state,
            challenger_game_ids=(*state.challenger_game_ids, game_id)[-window_size:],
        )
    else:
        if game_id in state.baseline_game_ids:
            return state
        state = replace(
            state,
            baseline_game_ids=(*state.baseline_game_ids, game_id)[-window_size:],
        )
    save_state(runs_dir, state)
    return state


def maybe_step_after_game(
    *,
    config_path: Path,
    settings: Settings,
    game_id: str,
    prompt_version: str,
) -> dict[str, object] | None:
    if not settings.evolution_enabled:
        return None
    state = record_finished_game(
        runs_dir=settings.runs_dir,
        game_id=game_id,
        prompt_version=prompt_version,
        window_size=settings.evolution_window_size,
    )
    if _window_ready(state, settings.evolution_window_size):
        return step(config_path=config_path, settings=settings, dry_run=False)
    return None


def step(
    *,
    config_path: Path,
    settings: Settings,
    dry_run: bool = False,
) -> dict[str, object]:
    config = load_game_config(config_path)
    state = load_state(settings.runs_dir)
    ensure_prompt_version(config.prompt_pack_root, state.active_version)
    if state.status == "testing_challenger":
        return _judge_challenger(
            config_path=config_path,
            prompt_root=config.prompt_pack_root,
            settings=settings,
            state=state,
            dry_run=dry_run,
        )
    return _generate_challenger(
        prompt_root=config.prompt_pack_root,
        settings=settings,
        state=state,
        dry_run=dry_run,
    )


def _generate_challenger(
    *,
    prompt_root: Path,
    settings: Settings,
    state: EvolutionState,
    dry_run: bool,
) -> dict[str, object]:
    baseline = score_window(
        runs_dir=settings.runs_dir,
        game_ids=state.baseline_game_ids,
        settings=settings,
    )
    selected = weakest_axis(baseline)
    axis = axis_from_key(selected.axis)
    target_version = f"v{max(state.next_version, next_version_from_files(prompt_root))}"
    char_cap = seed_char_cap(prompt_root, axis, settings.evolution_char_cap_ratio)
    candidate = evolve_prompt(
        prompt_root=prompt_root,
        source_version=state.champion_version,
        axis=axis,
        axis_score=selected,
        char_cap=char_cap,
        settings=settings,
    )
    diff = _diff_prompt(
        before=prompt_file(prompt_root, axis.role.value, axis.prompt_kind, state.champion_version).read_text(
            encoding="utf-8"
        ),
        after=candidate.text,
        fromfile=f"{axis.prompt_relative_path}.{state.champion_version}",
        tofile=f"{axis.prompt_relative_path}.{target_version}",
    )
    result: dict[str, object] = {
        "event": "challenger_generated",
        "dry_run": dry_run,
        "target_axis": axis.key,
        "source_version": state.champion_version,
        "target_version": target_version,
        "baseline": baseline.to_json(),
        "candidate": candidate.to_json(),
        "diff": diff,
    }
    if dry_run:
        with tempfile.TemporaryDirectory(prefix="wolven-evolution-dry-run.") as tmp_name:
            create_snapshot_in_dir(
                output_root=Path(tmp_name),
                prompt_root=prompt_root,
                source_version=state.champion_version,
                target_version=target_version,
                axis=axis,
                replacement_text=candidate.text,
            )
        return result
    append_ledger(settings.runs_dir, result)
    if not candidate.valid:
        save_state(
            settings.runs_dir,
            replace(state, next_version=int(target_version.removeprefix("v")) + 1),
        )
        return result
    create_snapshot(
        prompt_root=prompt_root,
        source_version=state.champion_version,
        target_version=target_version,
        axis=axis,
        replacement_text=candidate.text,
    )
    save_state(
        settings.runs_dir,
        replace(
            state,
            active_version=target_version,
            challenger_version=target_version,
            status="testing_challenger",
            target_axis=axis.key,
            challenger_game_ids=(),
            next_version=int(target_version.removeprefix("v")) + 1,
        ),
    )
    return result


def _judge_challenger(
    *,
    config_path: Path,
    prompt_root: Path,
    settings: Settings,
    state: EvolutionState,
    dry_run: bool,
) -> dict[str, object]:
    del config_path
    if state.target_axis is None or state.challenger_version is None:
        raise ValueError("challenger state is missing target axis or version")
    baseline = score_window(
        runs_dir=settings.runs_dir,
        game_ids=state.baseline_game_ids,
        settings=settings,
    )
    challenger = score_window(
        runs_dir=settings.runs_dir,
        game_ids=state.challenger_game_ids,
        settings=settings,
    )
    gate = evaluate_gate(
        target_axis=state.target_axis,
        baseline=baseline,
        challenger=challenger,
        min_margin=settings.evolution_min_margin,
        regression_tolerance=settings.evolution_regression_tolerance,
    )
    result: dict[str, object] = {
        "event": "challenger_judged",
        "dry_run": dry_run,
        "target_axis": state.target_axis,
        "champion_version": state.champion_version,
        "challenger_version": state.challenger_version,
        "baseline": baseline.to_json(),
        "challenger": challenger.to_json(),
        "gate": gate.to_json(),
    }
    if dry_run:
        return result
    append_ledger(settings.runs_dir, result)
    if gate.accepted:
        next_state = replace(
            state,
            active_version=state.challenger_version,
            champion_version=state.challenger_version,
            challenger_version=None,
            status="collecting_baseline",
            target_axis=None,
            baseline_game_ids=state.challenger_game_ids,
            challenger_game_ids=(),
        )
    else:
        next_state = replace(
            state,
            active_version=state.champion_version,
            challenger_version=None,
            status="collecting_baseline",
            target_axis=None,
            baseline_game_ids=state.baseline_game_ids,
            challenger_game_ids=(),
            rejected_versions=(*state.rejected_versions, state.challenger_version),
        )
    save_state(settings.runs_dir, next_state)
    if _window_ready(next_state, settings.evolution_window_size):
        return _generate_challenger(
            prompt_root=prompt_root,
            settings=settings,
            state=next_state,
            dry_run=False,
        )
    return result


def _window_ready(state: EvolutionState, window_size: int) -> bool:
    if state.status == "testing_challenger":
        return len(state.challenger_game_ids) >= window_size
    return len(state.baseline_game_ids) >= window_size


def _diff_prompt(*, before: str, after: str, fromfile: str, tofile: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )

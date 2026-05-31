from __future__ import annotations

import json
from pathlib import Path

from wolven_hunt.config.prompts import DEFAULT_PROMPT_VERSION
from wolven_hunt.core.seat import Role
from wolven_hunt.evolution.axes import AXES, axis_from_key
from wolven_hunt.evolution.gate import evaluate_gate
from wolven_hunt.evolution.ledger import append_ledger, ledger_path
from wolven_hunt.evolution.scoring import AxisScore, WindowScore
from wolven_hunt.evolution.snapshot import seed_char_cap
from wolven_hunt.evolution.state import EvolutionState, load_state, save_state


def test_axes_include_fourteen_targets_and_no_villager_role_duty() -> None:
    assert len(AXES) == 14
    assert all(
        not (axis.role is Role.VILLAGER and axis.score_key == "role_duty") for axis in AXES
    )
    assert axis_from_key("seer.role_duty").prompt_kind == "night_action"


def test_seed_char_cap_is_fixed_to_current_default_prompt_version(game_config) -> None:
    axis = axis_from_key("seer.role_duty")
    cap = seed_char_cap(game_config.prompt_pack_root, axis, 1.10)
    source = game_config.prompt_pack_root / "seer" / f"night_action.{DEFAULT_PROMPT_VERSION}.md"
    assert cap >= len(source.read_text(encoding="utf-8"))


def test_gate_rejects_margin_regression_and_fallback() -> None:
    baseline = WindowScore(
        game_ids=("a",),
        axis_scores={
            "seer.role_duty": AxisScore("seer.role_duty", 70, 5),
            "wolf.speech": AxisScore("wolf.speech", 80, 15),
        },
        fallback_count=0,
        raw_response_count=10,
    )
    challenger = WindowScore(
        game_ids=("b",),
        axis_scores={
            "seer.role_duty": AxisScore("seer.role_duty", 71, 5),
            "wolf.speech": AxisScore("wolf.speech", 76, 15),
        },
        fallback_count=1,
        raw_response_count=10,
    )
    result = evaluate_gate(
        target_axis="seer.role_duty",
        baseline=baseline,
        challenger=challenger,
        min_margin=2.0,
        regression_tolerance=3.0,
    )
    assert not result.accepted
    assert set(result.reasons) == {
        "target_margin_not_met",
        "other_axis_regression",
        "fallback_rate_increased",
    }


def test_state_atomic_write_and_ledger_append(tmp_path: Path) -> None:
    state = EvolutionState(active_version="v6", champion_version="v6", next_version=7)
    save_state(tmp_path, state)
    assert load_state(tmp_path).active_version == "v6"
    append_ledger(tmp_path, {"event": "test", "value": 1})
    append_ledger(tmp_path, {"event": "test", "value": 2})
    rows = [
        json.loads(line)
        for line in ledger_path(tmp_path).read_text(encoding="utf-8").splitlines()
    ]
    assert [row["value"] for row in rows] == [1, 2]

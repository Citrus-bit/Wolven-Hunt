from __future__ import annotations

import pytest

from wolven_hunt.llm.schemas import PHASE_OUTPUT_MODELS


@pytest.mark.llm
def test_phase_output_models_cover_step_06_contract() -> None:
    assert set(PHASE_OUTPUT_MODELS) == {
        "NIGHT_GUARD",
        "NIGHT_WOLF_CHAT",
        "NIGHT_WOLF_VOTE",
        "NIGHT_SEER",
        "DAY_SPEECH",
        "DAY_KNIGHT_INTERRUPT",
        "DAY_VOTE",
        "DAY_VOTE_PK",
        "DAY_LAST_WORDS",
    }


@pytest.mark.llm
@pytest.mark.parametrize(
    ("phase", "payload"),
    [
        ("NIGHT_GUARD", {"target": 1}),
        ("NIGHT_WOLF_CHAT", {"text": "[沉默]"}),
        ("NIGHT_WOLF_VOTE", {"target": 2}),
        ("NIGHT_SEER", {"target": 3}),
        ("DAY_SPEECH", {"text": "我没有更多信息"}),
        ("DAY_KNIGHT_INTERRUPT", {"activate": False, "target": None}),
        ("DAY_VOTE", {"target": 4}),
        ("DAY_VOTE_PK", {"target": 5}),
        ("DAY_LAST_WORDS", {"text": "我没有遗言"}),
    ],
)
def test_phase_output_models_accept_minimal_payloads(
    phase: str,
    payload: dict[str, object],
) -> None:
    assert PHASE_OUTPUT_MODELS[phase].model_validate(payload)

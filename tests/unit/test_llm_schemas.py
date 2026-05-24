from __future__ import annotations

import pytest
from pydantic import ValidationError

from wolven_hunt.llm.schemas import PHASE_OUTPUT_MODELS


@pytest.mark.llm
def test_phase_output_models_cover_step_06_contract() -> None:
    assert set(PHASE_OUTPUT_MODELS) == {
        "NIGHT_GUARD",
        "NIGHT_WOLF_CHAT",
        "NIGHT_WOLF_VOTE",
        "NIGHT_WITCH",
        "NIGHT_SEER",
        "DAY_SPEECH",
        "DAY_VOTE",
        "DAY_VOTE_PK",
        "DAY_LAST_WORDS",
    }


@pytest.mark.llm
@pytest.mark.parametrize(
    ("phase", "payload"),
    [
        ("NIGHT_GUARD", {"target": 1}),
        ("NIGHT_WOLF_CHAT", {"text": "建议统一刀口,避免狼队分票。"}),
        ("NIGHT_WOLF_VOTE", {"target": 2}),
        ("NIGHT_WITCH", {"action": "skip", "target": None}),
        ("NIGHT_SEER", {"target": 3}),
        ("DAY_SPEECH", {"text": "我先基于公开信息观察发言和票型。"}),
        ("DAY_VOTE", {"target": 4}),
        ("DAY_VOTE_PK", {"target": 5}),
        ("DAY_VOTE", {"target": None}),
        ("DAY_VOTE_PK", {"target": None}),
        ("DAY_LAST_WORDS", {"text": "我没有遗言"}),
    ],
)
def test_phase_output_models_accept_minimal_payloads(
    phase: str,
    payload: dict[str, object],
) -> None:
    assert PHASE_OUTPUT_MODELS[phase].model_validate(payload)


@pytest.mark.llm
@pytest.mark.parametrize("phase", ["DAY_VOTE", "DAY_VOTE_PK"])
def test_vote_output_models_reject_invalid_seat(phase: str) -> None:
    with pytest.raises(ValidationError):
        PHASE_OUTPUT_MODELS[phase].model_validate({"target": 0})


@pytest.mark.llm
@pytest.mark.parametrize("phase", ["NIGHT_WOLF_CHAT", "DAY_SPEECH"])
@pytest.mark.parametrize("text", ["", "   ", "[沉默]", "无话可说", "我先观察"])
def test_text_output_models_reject_placeholders(phase: str, text: str) -> None:
    with pytest.raises(ValidationError):
        PHASE_OUTPUT_MODELS[phase].model_validate({"text": text})

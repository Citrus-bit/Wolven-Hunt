from __future__ import annotations

import os

import pytest

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.gateway import LLMGateway
from wolven_hunt.llm.provider import LiteLLMProvider
from wolven_hunt.llm.schemas import SpeechOutput


@pytest.mark.llm
@pytest.mark.skipif(
    os.getenv("WH_REAL_LLM_SMOKE") != "1",
    reason="set WH_REAL_LLM_SMOKE=1 to call a real provider",
)
def test_real_llm_single_structured_call() -> None:
    api_key = os.environ["WH_LLM_API_KEY"]
    model = os.getenv("WH_LLM_MODEL") or "gpt-4o-mini"
    base_url = os.getenv("WH_LLM_BASE_URL", "")
    gateway = LLMGateway(
        provider=LiteLLMProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=30,
        ),
        max_retries=1,
    )

    result = gateway.call(
        seat=Seat(1),
        phase="DAY_SPEECH",
        prompt='Return only JSON with this schema: {"text": "short Chinese sentence"}.',
        output_model=SpeechOutput,
        rng=DeterministicRNG("real-llm-smoke"),
    )

    assert result.error is None
    assert isinstance(result.parsed, SpeechOutput)
    assert result.parsed.text

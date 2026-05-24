from __future__ import annotations

import os

import pytest

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.gateway import LLMGateway
from wolven_hunt.llm.provider import LiteLLMProvider
from wolven_hunt.llm.schemas import SpeechOutput, WolfChatOutput
from wolven_hunt.llm.thinking import thinking_extra_body


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


@pytest.mark.llm
@pytest.mark.skipif(
    os.getenv("WH_REAL_QWEN_SMOKE") != "1",
    reason="set WH_REAL_QWEN_SMOKE=1 to call a real Qwen provider",
)
def test_real_qwen_thinking_disabled_structured_call() -> None:
    api_key = os.getenv("WH_QWEN_API_KEY") or os.environ["WH_LLM_API_KEY"]
    model = os.getenv("WH_QWEN_MODEL") or "qwen3.6-flash"
    base_url = (
        os.getenv("WH_QWEN_BASE_URL")
        or os.getenv("WH_LLM_BASE_URL")
        or "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    gateway = LLMGateway(
        provider=LiteLLMProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=30,
            extra_body=thinking_extra_body(model, enabled=False),
        ),
        max_retries=0,
    )

    result = gateway.call(
        seat=Seat(4),
        phase="NIGHT_WOLF_CHAT",
        prompt='Return only JSON with this schema: {"text": "一句简短狼队夜聊建议"}.',
        output_model=WolfChatOutput,
        rng=DeterministicRNG("real-qwen-thinking-disabled-smoke"),
    )

    assert result.error is None
    assert result.model != "unknown"
    assert isinstance(result.parsed, WolfChatOutput)
    assert result.parsed.text

from __future__ import annotations

import asyncio

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import MockLLMProvider


def test_mock_provider_acomplete_returns_response() -> None:
    provider = MockLLMProvider(model="mock")
    response = asyncio.run(
        provider.acomplete(
            seat=Seat(1),
            phase="REVIEW_REPORT",
            prompt="hi",
            rng=DeterministicRNG("test"),
        )
    )

    assert response.content
    assert response.model == "mock"

from __future__ import annotations

import pytest

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.cost import CostEntry, CostTracker, TokenUsage
from wolven_hunt.llm.gateway import LLMGateway
from wolven_hunt.llm.provider import ProviderResponse
from wolven_hunt.llm.schemas import GuardOutput


class CostedProvider:
    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, prompt, rng
        return ProviderResponse(
            content='{"target":1}',
            model="mock/costed",
            usage=TokenUsage(
                prompt_tokens=8,
                completion_tokens=3,
            ),
            cost_usd=0.25,
        )


@pytest.mark.llm
def test_cost_tracker_accumulates_tokens_and_budget() -> None:
    tracker = CostTracker(budget_tokens=10)
    tracker.record(
        CostEntry(
            storage_ref="llm/1",
            model="mock",
            prompt_tokens=8,
            completion_tokens=3,
            cost_usd=0.25,
        )
    )

    assert tracker.total_tokens == 11
    assert tracker.total_cost_usd == 0.25
    assert tracker.over_budget


@pytest.mark.llm
def test_gateway_budget_warning_is_emitted_once() -> None:
    tracker = CostTracker(budget_tokens=10)
    gateway = LLMGateway(
        provider=CostedProvider(),
        max_retries=0,
        cost_tracker=tracker,
    )

    first = gateway.call(
        seat=Seat(1),
        phase="NIGHT_GUARD",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("budget-warning"),
    )
    second = gateway.call(
        seat=Seat(1),
        phase="NIGHT_GUARD",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("budget-warning"),
    )

    assert first.budget_warning is not None
    assert first.budget_warning["budget_tokens"] == 10
    assert first.budget_warning["used_tokens"] == 11
    assert second.budget_warning is None

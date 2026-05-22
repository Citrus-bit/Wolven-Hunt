from __future__ import annotations

import pytest

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.gateway import LLMErrorType, LLMGateway
from wolven_hunt.llm.provider import ProviderResponse
from wolven_hunt.llm.schemas import GuardOutput


class FlakyProvider:
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, prompt, rng
        self.calls += 1
        return ProviderResponse(
            content="not json" if self.calls == 1 else '{"target":1}',
            model="mock/flaky",
        )


class TimeoutProvider:
    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, prompt, rng
        raise TimeoutError("too slow")


@pytest.mark.llm
def test_gateway_retries_invalid_json_then_parses() -> None:
    rows: list[dict[str, object]] = []
    provider = FlakyProvider()
    gateway = LLMGateway(provider=provider, max_retries=1, raw_response_sink=rows.append)

    result = gateway.call(
        seat=Seat(1),
        phase="NIGHT_GUARD",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("gateway"),
    )

    assert isinstance(result.parsed, GuardOutput)
    assert result.parsed.target == 1
    assert provider.calls == 2
    assert len(rows) == 2
    assert rows[0]["error"] == "invalid_json"
    assert "raw_response" not in result.event_payload()


@pytest.mark.llm
def test_gateway_maps_timeout_error() -> None:
    gateway = LLMGateway(provider=TimeoutProvider(), max_retries=0)

    result = gateway.call(
        seat=Seat(1),
        phase="NIGHT_GUARD",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("gateway-timeout"),
    )

    assert result.error is not None
    assert result.error.type is LLMErrorType.TIMEOUT

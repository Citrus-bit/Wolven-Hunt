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


class TimeoutThenSuccessProvider:
    def __init__(self, *, failures: int) -> None:
        self.failures = failures
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
        if self.calls <= self.failures:
            raise TimeoutError("too slow")
        return ProviderResponse(content='{"target":1}', model="mock/recovered")


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
def test_gateway_phase_retry_override_can_disable_retries() -> None:
    provider = FlakyProvider()
    gateway = LLMGateway(
        provider=provider,
        max_retries=1,
        phase_max_retries={"DAY_SPEECH": 0},
    )

    result = gateway.call(
        seat=Seat(1),
        phase="DAY_SPEECH",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("gateway-phase-retry"),
    )

    assert provider.calls == 1
    assert result.error is not None
    assert result.error.type is LLMErrorType.INVALID_JSON


@pytest.mark.llm
def test_gateway_exponential_backoff_before_success() -> None:
    rows: list[dict[str, object]] = []
    delays: list[float] = []
    provider = TimeoutThenSuccessProvider(failures=2)
    gateway = LLMGateway(
        provider=provider,
        max_retries=2,
        retry_backoff_base_seconds=1,
        retry_backoff_multiplier=2,
        retry_backoff_max_seconds=8,
        sleep_fn=delays.append,
        raw_response_sink=rows.append,
    )

    result = gateway.call(
        seat=Seat(1),
        phase="DAY_SPEECH",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("gateway-backoff-success"),
    )

    assert isinstance(result.parsed, GuardOutput)
    assert provider.calls == 3
    assert delays == [1, 2]
    assert [row["error"] for row in rows] == ["timeout", "timeout", None]


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


@pytest.mark.llm
def test_gateway_records_each_attempt_when_retries_exhausted() -> None:
    rows: list[dict[str, object]] = []
    delays: list[float] = []
    gateway = LLMGateway(
        provider=TimeoutProvider(),
        max_retries=2,
        retry_backoff_base_seconds=1,
        retry_backoff_multiplier=2,
        retry_backoff_max_seconds=8,
        sleep_fn=delays.append,
        raw_response_sink=rows.append,
    )

    result = gateway.call(
        seat=Seat(1),
        phase="DAY_SPEECH",
        prompt="{}",
        output_model=GuardOutput,
        rng=DeterministicRNG("gateway-backoff-exhausted"),
    )

    assert result.error is not None
    assert result.error.type is LLMErrorType.TIMEOUT
    assert delays == [1, 2]
    assert [row["attempt"] for row in rows] == [0, 1, 2]
    assert [row["error"] for row in rows] == ["timeout", "timeout", "timeout"]

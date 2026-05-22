from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.cost import TokenUsage


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    content: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse: ...


class MockLLMProvider:
    def __init__(self, *, model: str = "mock/deterministic") -> None:
        self.model = model

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del prompt
        content_by_phase: dict[str, dict[str, object]] = {
            "NIGHT_GUARD": {"target": seat.number},
            "NIGHT_WOLF_CHAT": {"text": "[沉默]"},
            "NIGHT_WOLF_VOTE": {"target": _cycle_target(seat)},
            "NIGHT_SEER": {"target": _cycle_target(seat)},
            "DAY_SPEECH": {"text": f"我是 {seat.number} 号, 我没有更多信息"},
            "DAY_KNIGHT_INTERRUPT": {"activate": False, "target": None},
            "DAY_VOTE": {"target": _cycle_target(seat)},
            "DAY_VOTE_PK": {"target": 1},
            "DAY_LAST_WORDS": {"text": "我没有遗言"},
        }
        stream = f"mock_llm_tokens:{phase}:seat{seat.number}"
        usage = TokenUsage(
            prompt_tokens=20 + rng.stream(stream).randint(0, 5),
            completion_tokens=5,
        )
        return ProviderResponse(
            content=json.dumps(
                content_by_phase.get(phase, {"text": "我没有更多信息"}), ensure_ascii=False
            ),
            model=self.model,
            usage=usage,
        )


class LiteLLMProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, rng
        litellm = importlib.import_module("litellm")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            "response_format": {"type": "json_object"},
        }
        if self.base_url:
            kwargs["api_base"] = self.base_url
        response = litellm.completion(**kwargs)
        choice = response["choices"][0]
        message = choice["message"]
        usage_raw = response.get("usage") or {}
        usage = TokenUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
        )
        cost_usd = float(response.get("_hidden_params", {}).get("response_cost") or 0.0)
        return ProviderResponse(
            content=str(message.get("content") or ""),
            model=str(response.get("model") or self.model),
            usage=usage,
            cost_usd=cost_usd,
        )


class ReplayLLMProvider:
    def __init__(self, raw_responses: tuple[dict[str, object], ...]) -> None:
        self._responses = list(raw_responses)

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, phase, prompt, rng
        if not self._responses:
            raise RuntimeError("replay raw response exhausted")
        row = self._responses.pop(0)
        return ProviderResponse(
            content=str(row.get("raw_response", "")),
            model=str(row.get("model", "replay/raw")),
            usage=TokenUsage(
                prompt_tokens=_int_value(row.get("prompt_tokens")),
                completion_tokens=_int_value(row.get("completion_tokens")),
            ),
            cost_usd=_float_value(row.get("cost_usd")),
        )


def _cycle_target(seat: Seat) -> int:
    return 1 if seat.number == 8 else seat.number + 1


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0

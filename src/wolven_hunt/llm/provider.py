from __future__ import annotations

import importlib
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.cost import TokenUsage
from wolven_hunt.llm.provider_map import ProviderConfig, ProviderMap
from wolven_hunt.llm.thinking import thinking_extra_body


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
        seat_numbers = _seat_numbers_from_prompt(prompt)
        cycled_target = _cycle_target(seat, seat_numbers)
        content_by_phase: dict[str, dict[str, object]] = {
            "NIGHT_GUARD": {"target": seat.number},
            "NIGHT_WOLF_CHAT": {"text": f"{seat.number}号建议统一刀口,避免狼队分票。"},
            "NIGHT_WOLF_VOTE": {"target": cycled_target},
            "NIGHT_WITCH": {"action": "skip", "target": None},
            "NIGHT_SEER": {"target": cycled_target},
            "DAY_SPEECH": {
                "text": (
                    f"我是 {seat.number} 号。我先关注公开发言里的逻辑矛盾,"
                    "投票会优先选择解释不清的位置。"
                )
            },
            "DAY_VOTE": {"target": cycled_target},
            "DAY_VOTE_PK": {"target": 1},
            "DAY_LAST_WORDS": {"text": "我没有遗言"},
        }
        stream = f"mock_llm_tokens:{phase}:seat{seat.number}"
        usage = TokenUsage(
            prompt_tokens=20 + rng.randint(stream, 0, 5),
            completion_tokens=5,
        )
        return ProviderResponse(
            content=json.dumps(
                content_by_phase.get(
                    phase,
                    {"text": "我先基于公开信息观察发言和票型。"},
                ),
                ensure_ascii=False,
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
        extra_body: dict[str, Any] | None = None,
        phase_timeout_seconds: dict[str, float] | None = None,
    ) -> None:
        self.model = normalize_litellm_model(model=model, base_url=base_url)
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.extra_body = dict(extra_body or {})
        self.phase_timeout_seconds = dict(phase_timeout_seconds or {})

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del seat, rng
        litellm = _litellm_module()
        timeout_seconds = self.phase_timeout_seconds.get(phase, self.timeout_seconds)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": self.api_key,
            "timeout": timeout_seconds,
            "response_format": {"type": "json_object"},
        }
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if self.extra_body:
            kwargs["extra_body"] = dict(self.extra_body)
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


def _litellm_module() -> Any:
    _force_litellm_direct_env()
    litellm = importlib.import_module("litellm")
    _configure_litellm_direct_network(litellm)
    return litellm


def _force_litellm_direct_env() -> None:
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
    os.environ["AIOHTTP_TRUST_ENV"] = "false"
    os.environ["DISABLE_AIOHTTP_TRUST_ENV"] = "true"


def _configure_litellm_direct_network(litellm: Any) -> None:
    litellm.aiohttp_trust_env = False
    litellm.disable_aiohttp_trust_env = True
    client_session = getattr(litellm, "client_session", None)
    if not _is_direct_httpx_client(client_session):
        close = getattr(client_session, "close", None)
        if callable(close):
            close()
        litellm.client_session = httpx.Client(trust_env=False)
    aclient_session = getattr(litellm, "aclient_session", None)
    if not _is_direct_httpx_client(aclient_session):
        litellm.aclient_session = httpx.AsyncClient(trust_env=False)


def _is_direct_httpx_client(client: object) -> bool:
    return isinstance(client, (httpx.Client, httpx.AsyncClient)) and (
        getattr(client, "_trust_env", True) is False
    )


def normalize_litellm_model(*, model: str, base_url: str = "") -> str:
    normalized = model.strip()
    if base_url.strip() and "/" not in normalized:
        return f"custom_openai/{normalized}"
    return normalized


class ReplayLLMProvider:
    def __init__(self, raw_responses: tuple[dict[str, object], ...]) -> None:
        self._lock = threading.Lock()
        self._responses = [
            row
            for row in raw_responses
            if _int_value(row.get("seat")) <= 0 or not str(row.get("phase") or "")
        ]
        self._responses_by_key: dict[tuple[int, str], list[dict[str, object]]] = {}
        for row in raw_responses:
            seat_number = _int_value(row.get("seat"))
            phase = str(row.get("phase") or "")
            if seat_number <= 0 or not phase:
                continue
            self._responses_by_key.setdefault((seat_number, phase), []).append(row)

    def complete(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        rng: DeterministicRNG,
    ) -> ProviderResponse:
        del prompt, rng
        with self._lock:
            bucket = self._responses_by_key.get((seat.number, phase))
            if bucket:
                row = bucket.pop(0)
            elif self._responses:
                row = self._responses.pop(0)
            else:
                raise RuntimeError("replay raw response exhausted")
        return ProviderResponse(
            content=str(row.get("raw_response", "")),
            model=str(row.get("model", "replay/raw")),
            usage=TokenUsage(
                prompt_tokens=_int_value(row.get("prompt_tokens")),
                completion_tokens=_int_value(row.get("completion_tokens")),
            ),
            cost_usd=_float_value(row.get("cost_usd")),
        )


def build_provider_from_config(
    config: ProviderConfig,
    *,
    phase_timeout_seconds: dict[str, float] | None = None,
) -> LLMProvider:
    if config.provider == "litellm":
        return LiteLLMProvider(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            extra_body=thinking_extra_body(config.model, enabled=config.thinking_enabled),
            phase_timeout_seconds=phase_timeout_seconds,
        )
    return MockLLMProvider(model=config.model)


def build_provider_for_seat(seat: Seat, provider_map: ProviderMap) -> LLMProvider:
    return build_provider_from_config(provider_map.for_seat(seat))


def _cycle_target(seat: Seat, seat_numbers: tuple[int, ...]) -> int:
    if not seat_numbers:
        return seat.number + 1
    for number in seat_numbers:
        if number > seat.number:
            return number
    return seat_numbers[0]


def _seat_numbers_from_prompt(prompt: str) -> tuple[int, ...]:
    marker = "以下 JSON payload 是你本次决策唯一可用的结构化上下文:"
    if marker not in prompt:
        return ()
    raw_payload = prompt.rsplit(marker, 1)[-1].strip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw_payload)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict):
        return ()
    summary = payload.get("rule_set_summary")
    if not isinstance(summary, dict):
        return ()
    seat_range = summary.get("seat_range")
    if isinstance(seat_range, dict):
        start = _int_value(seat_range.get("start"))
        end = _int_value(seat_range.get("end"))
        if start > 0 and end >= start:
            return tuple(range(start, end + 1))
    seat_count = _int_value(summary.get("seat_count"))
    if seat_count > 0:
        return tuple(range(1, seat_count + 1))
    return ()


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0

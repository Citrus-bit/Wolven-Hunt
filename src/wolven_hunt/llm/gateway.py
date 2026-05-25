from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.cost import CostEntry, CostTracker, TokenUsage
from wolven_hunt.llm.provider import LLMProvider, ProviderResponse

TModel = TypeVar("TModel", bound=BaseModel)


class LLMErrorType(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    INVALID_JSON = "invalid_json"
    SCHEMA_VIOLATION = "schema_violation"
    ILLEGAL_ACTION = "illegal_action"


@dataclass(frozen=True, slots=True)
class LLMError:
    type: LLMErrorType
    message: str


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: BaseModel | None
    raw_response: str
    prompt_hash: str
    raw_response_hash: str
    storage_ref: str
    model: str
    tokens: TokenUsage
    cost_usd: float
    prompt_version: str
    error: LLMError | None = None
    budget_warning: dict[str, object] | None = None

    def event_payload(self) -> dict[str, object]:
        return {
            "prompt_hash": self.prompt_hash,
            "raw_response_hash": self.raw_response_hash,
            "storage_ref": self.storage_ref,
            "model": self.model,
            "prompt_tokens": self.tokens.prompt_tokens,
            "completion_tokens": self.tokens.completion_tokens,
            "cost_usd": self.cost_usd,
            "prompt_version": self.prompt_version,
        }


class LLMFallbackRequired(RuntimeError):
    def __init__(self, error: LLMError) -> None:
        super().__init__(f"{error.type}: {error.message}")
        self.error = error


RawResponseSink = Callable[[dict[str, object]], None]
SleepFn = Callable[[float], None]


class LLMGateway:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        max_retries: int,
        phase_max_retries: Mapping[str, int] | None = None,
        retry_backoff_delays_seconds: Sequence[float] | None = None,
        retry_backoff_base_seconds: float = 0.0,
        retry_backoff_multiplier: float = 2.0,
        retry_backoff_max_seconds: float = 0.0,
        retry_backoff_jitter: bool = False,
        sleep_fn: SleepFn | None = None,
        prompt_version: str = "v4",
        cost_tracker: CostTracker | None = None,
        raw_response_sink: RawResponseSink | None = None,
    ) -> None:
        if retry_backoff_base_seconds < 0:
            raise ValueError("retry_backoff_base_seconds must be non-negative")
        if retry_backoff_multiplier < 1:
            raise ValueError("retry_backoff_multiplier must be at least 1")
        if retry_backoff_max_seconds < 0:
            raise ValueError("retry_backoff_max_seconds must be non-negative")
        if retry_backoff_jitter:
            raise ValueError("retry_backoff_jitter must be false for deterministic retries")
        retry_backoff_delays = tuple(float(delay) for delay in (retry_backoff_delays_seconds or ()))
        if any(delay < 0 for delay in retry_backoff_delays):
            raise ValueError("retry_backoff_delays_seconds must be non-negative")
        self.provider = provider
        self.max_retries = max_retries
        self.phase_max_retries = dict(phase_max_retries or {})
        self.retry_backoff_delays_seconds = retry_backoff_delays
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.retry_backoff_max_seconds = retry_backoff_max_seconds
        self.sleep_fn = time.sleep if sleep_fn is None else sleep_fn
        self.prompt_version = prompt_version
        self.cost_tracker = cost_tracker
        self.raw_response_sink = raw_response_sink
        self._counter = 0
        self._counter_lock = threading.Lock()

    def call(
        self,
        *,
        seat: Seat,
        phase: str,
        prompt: str,
        output_model: type[TModel],
        rng: DeterministicRNG,
    ) -> LLMCallResult:
        last_result: LLMCallResult | None = None
        current_prompt = prompt
        max_retries = self.phase_max_retries.get(phase, self.max_retries)
        for attempt in range(max_retries + 1):
            storage_ref = self._next_storage_ref(seat=seat, phase=phase)
            prompt_hash = _sha256(current_prompt)
            response = ProviderResponse(content="", model="unknown")
            try:
                response = self.provider.complete(
                    seat=seat, phase=phase, prompt=current_prompt, rng=rng
                )
                parsed_json = json.loads(response.content)
                parsed = output_model.model_validate(parsed_json)
                result = LLMCallResult(
                    parsed=parsed,
                    raw_response=response.content,
                    prompt_hash=prompt_hash,
                    raw_response_hash=_sha256(response.content),
                    storage_ref=storage_ref,
                    model=response.model,
                    tokens=response.usage,
                    cost_usd=response.cost_usd,
                    prompt_version=self.prompt_version,
                )
                warning = self._record(result, seat=seat, phase=phase, attempt=attempt)
                return replace(result, budget_warning=warning)
            except json.JSONDecodeError as exc:
                error = LLMError(LLMErrorType.INVALID_JSON, str(exc))
                raw_response = response.content
            except ValidationError as exc:
                error = LLMError(LLMErrorType.SCHEMA_VIOLATION, str(exc))
                raw_response = response.content
            except TimeoutError as exc:
                error = LLMError(LLMErrorType.TIMEOUT, str(exc))
                raw_response = ""
            except Exception as exc:
                error = LLMError(_classify_exception(exc), str(exc))
                raw_response = ""

            last_result = LLMCallResult(
                parsed=None,
                raw_response=raw_response,
                prompt_hash=prompt_hash,
                raw_response_hash=_sha256(raw_response),
                storage_ref=storage_ref,
                model=response.model,
                tokens=response.usage,
                cost_usd=response.cost_usd,
                prompt_version=self.prompt_version,
                error=error,
            )
            warning = self._record(last_result, seat=seat, phase=phase, attempt=attempt)
            last_result = replace(last_result, budget_warning=warning)
            if attempt < max_retries:
                current_prompt = (
                    f"{prompt}\n\n上一次输出未被接受: {error.type}: "
                    f"{error.message}。请只返回符合 schema 的 JSON。"
                )
                delay = self._retry_delay(attempt)
                if delay > 0:
                    self.sleep_fn(delay)
        assert last_result is not None
        return last_result

    def _retry_delay(self, attempt: int) -> float:
        if self.retry_backoff_delays_seconds:
            return self.retry_backoff_delays_seconds[
                min(attempt, len(self.retry_backoff_delays_seconds) - 1)
            ]
        if self.retry_backoff_base_seconds <= 0 or self.retry_backoff_max_seconds <= 0:
            return 0.0
        delay = self.retry_backoff_base_seconds * (self.retry_backoff_multiplier**attempt)
        return min(delay, self.retry_backoff_max_seconds)

    def _next_storage_ref(self, *, seat: Seat, phase: str) -> str:
        with self._counter_lock:
            self._counter += 1
            counter = self._counter
        return f"llm/{seat.number}/{phase}/{counter:06d}"

    def _record(
        self,
        result: LLMCallResult,
        *,
        seat: Seat,
        phase: str,
        attempt: int,
    ) -> dict[str, object] | None:
        warning: dict[str, object] | None = None
        if self.cost_tracker is not None:
            self.cost_tracker.record(
                CostEntry(
                    storage_ref=result.storage_ref,
                    model=result.model,
                    prompt_tokens=result.tokens.prompt_tokens,
                    completion_tokens=result.tokens.completion_tokens,
                    cost_usd=result.cost_usd,
                )
            )
            warning = self.cost_tracker.consume_budget_warning()
        if self.raw_response_sink is None:
            return warning
        self.raw_response_sink(
            {
                "storage_ref": result.storage_ref,
                "seat": seat.number,
                "phase": phase,
                "day": None,
                "seq": None,
                "attempt": attempt,
                "model": result.model,
                "prompt_hash": result.prompt_hash,
                "raw_response_hash": result.raw_response_hash,
                "raw_response": result.raw_response,
                "prompt_tokens": result.tokens.prompt_tokens,
                "completion_tokens": result.tokens.completion_tokens,
                "cost_usd": result.cost_usd,
                "prompt_version": result.prompt_version,
                "error": None if result.error is None else result.error.type.value,
            }
        )
        return warning


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _classify_exception(exc: Exception) -> LLMErrorType:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "rate" in name or "rate" in message:
        return LLMErrorType.RATE_LIMIT
    if "timeout" in name or "timeout" in message:
        return LLMErrorType.TIMEOUT
    return LLMErrorType.NETWORK

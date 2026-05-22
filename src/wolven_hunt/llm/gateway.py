from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
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


class LLMGateway:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        max_retries: int,
        prompt_version: str = "v1",
        cost_tracker: CostTracker | None = None,
        raw_response_sink: RawResponseSink | None = None,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self.prompt_version = prompt_version
        self.cost_tracker = cost_tracker
        self.raw_response_sink = raw_response_sink
        self._counter = 0

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
        for attempt in range(self.max_retries + 1):
            self._counter += 1
            storage_ref = f"llm/{seat.number}/{phase}/{self._counter:06d}"
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
            if attempt < self.max_retries:
                current_prompt = (
                    f"{prompt}\n\n上一次输出未被接受: {error.type}: "
                    f"{error.message}。请只返回符合 schema 的 JSON。"
                )
        assert last_result is not None
        return last_result

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

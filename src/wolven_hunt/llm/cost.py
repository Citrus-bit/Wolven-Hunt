from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class CostEntry:
    storage_ref: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class CostTracker:
    def __init__(self, *, budget_tokens: int) -> None:
        self._budget_tokens = budget_tokens
        self._entries: list[CostEntry] = []
        self._warning_emitted = False
        self._lock = threading.Lock()

    @property
    def entries(self) -> tuple[CostEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self._total_tokens_unlocked()

    @property
    def total_cost_usd(self) -> float:
        with self._lock:
            return self._total_cost_usd_unlocked()

    @property
    def over_budget(self) -> bool:
        return self.total_tokens > self._budget_tokens

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens

    def record(self, entry: CostEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def consume_budget_warning(self) -> dict[str, object] | None:
        with self._lock:
            total_tokens = self._total_tokens_unlocked()
            if total_tokens <= self._budget_tokens or self._warning_emitted:
                return None
            self._warning_emitted = True
            total_cost_usd = self._total_cost_usd_unlocked()
        return {
            "budget_tokens": self._budget_tokens,
            "used_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "message": (f"LLM token budget exceeded: {total_tokens} > {self._budget_tokens}"),
        }

    def _total_tokens_unlocked(self) -> int:
        return sum(entry.prompt_tokens + entry.completion_tokens for entry in self._entries)

    def _total_cost_usd_unlocked(self) -> float:
        return sum(entry.cost_usd for entry in self._entries)

from __future__ import annotations

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

    @property
    def entries(self) -> tuple[CostEntry, ...]:
        return tuple(self._entries)

    @property
    def total_tokens(self) -> int:
        return sum(entry.prompt_tokens + entry.completion_tokens for entry in self._entries)

    @property
    def total_cost_usd(self) -> float:
        return sum(entry.cost_usd for entry in self._entries)

    @property
    def over_budget(self) -> bool:
        return self.total_tokens > self._budget_tokens

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens

    def record(self, entry: CostEntry) -> None:
        self._entries.append(entry)

    def consume_budget_warning(self) -> dict[str, object] | None:
        if not self.over_budget or self._warning_emitted:
            return None
        self._warning_emitted = True
        return {
            "budget_tokens": self._budget_tokens,
            "used_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "message": (f"LLM token budget exceeded: {self.total_tokens} > {self._budget_tokens}"),
        }

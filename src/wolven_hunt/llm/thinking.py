from __future__ import annotations

from typing import Any, Literal

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "default"]


def thinking_extra_body(model: str, *, enabled: bool) -> dict[str, Any]:
    normalized = model.strip().lower()
    if normalized.startswith("qwen"):
        return {"enable_thinking": enabled}
    if not enabled:
        return {}
    if normalized.startswith("gpt"):
        return {}
    if normalized.startswith(("kimi", "mimo", "deepseek", "glm", "doubao")):
        return {"thinking": {"type": "enabled"}}
    if normalized.startswith("hy3"):
        return {
            "chat_template_kwargs": {
                "thinking": True,
                "reasoning_effort": "medium",
            }
        }
    if normalized.startswith("minimax"):
        return {"reasoning_effort": "medium"}
    return {}


def thinking_reasoning_effort(model: str, *, enabled: bool) -> ReasoningEffort | None:
    if not enabled:
        return None
    normalized = model.strip().lower()
    if normalized.startswith("gpt"):
        return "xhigh"
    return None

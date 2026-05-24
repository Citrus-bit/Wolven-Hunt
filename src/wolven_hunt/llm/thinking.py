from __future__ import annotations

from typing import Any


def thinking_extra_body(model: str, *, enabled: bool) -> dict[str, Any]:
    normalized = model.strip().lower()
    if normalized.startswith("qwen"):
        return {"enable_thinking": enabled}
    if not enabled:
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

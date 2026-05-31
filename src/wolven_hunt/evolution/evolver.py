from __future__ import annotations

# ruff: noqa: RUF001
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from wolven_hunt.config.settings import Settings
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.seat import Seat
from wolven_hunt.llm.provider import LiteLLMProvider, ProviderResponse
from wolven_hunt.llm.thinking import thinking_extra_body, thinking_reasoning_effort

from .axes import EvolutionAxis, anchors_for_axis, validate_invariants
from .scoring import AxisScore
from .snapshot import prompt_file


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    text: str
    char_count: int
    char_cap: int
    missing_anchors: tuple[str, ...]
    valid: bool
    model: str
    raw_response: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "char_count": self.char_count,
            "char_cap": self.char_cap,
            "missing_anchors": list(self.missing_anchors),
            "valid": self.valid,
            "model": self.model,
        }


def evolve_prompt(
    *,
    prompt_root: Path,
    source_version: str,
    axis: EvolutionAxis,
    axis_score: AxisScore,
    char_cap: int,
    settings: Settings,
) -> EvolutionCandidate:
    source_text = prompt_file(prompt_root, axis.role.value, axis.prompt_kind, source_version).read_text(
        encoding="utf-8"
    )
    if settings.review_provider != "litellm":
        return _mock_candidate(
            source_text=source_text,
            axis=axis,
            axis_score=axis_score,
            char_cap=char_cap,
            model=settings.review_model,
        )
    provider = LiteLLMProvider(
        model=settings.review_model,
        api_key=settings.review_api_key,
        base_url=settings.review_base_url,
        timeout_seconds=settings.review_timeout_seconds,
        extra_body=thinking_extra_body(settings.review_model, enabled=True),
        reasoning_effort=thinking_reasoning_effort(settings.review_model, enabled=True),
    )
    prompt = _build_evolution_prompt(
        source_text=source_text,
        axis=axis,
        axis_score=axis_score,
        char_cap=char_cap,
    )
    response = provider.complete(
        seat=Seat(1),
        phase="PROMPT_EVOLUTION",
        prompt=prompt,
        rng=DeterministicRNG(f"prompt-evolution:{axis.key}:{source_version}"),
    )
    text = _candidate_text_from_response(response)
    return _validate_candidate(
        text=text,
        axis=axis,
        char_cap=char_cap,
        model=response.model,
        raw_response=response.content,
    )


def _mock_candidate(
    *,
    source_text: str,
    axis: EvolutionAxis,
    axis_score: AxisScore,
    char_cap: int,
    model: str,
) -> EvolutionCandidate:
    marker = f"\n\n<!-- evolution:{axis.key}:score={axis_score.average:.1f} -->"
    text = source_text if len(source_text) + len(marker) > char_cap else source_text + marker
    return _validate_candidate(text=text, axis=axis, char_cap=char_cap, model=model)


def _validate_candidate(
    *,
    text: str,
    axis: EvolutionAxis,
    char_cap: int,
    model: str,
    raw_response: str = "",
) -> EvolutionCandidate:
    missing = validate_invariants(axis, text)
    valid = len(text) <= char_cap and not missing
    return EvolutionCandidate(
        text=text,
        char_count=len(text),
        char_cap=char_cap,
        missing_anchors=missing,
        valid=valid,
        model=model,
        raw_response=raw_response,
    )


def _build_evolution_prompt(
    *,
    source_text: str,
    axis: EvolutionAxis,
    axis_score: AxisScore,
    char_cap: int,
) -> str:
    payload = {
        "axis": axis.key,
        "role": axis.role.value,
        "score_key": axis.score_key,
        "prompt_kind": axis.prompt_kind,
        "average_score": axis_score.average,
        "sample_count": axis_score.sample_count,
        "mistakes": list(axis_score.mistakes),
        "suggestions": list(axis_score.suggestions),
        "counterfactuals": list(axis_score.counterfactuals),
        "char_cap": char_cap,
        "required_anchors": list(anchors_for_axis(axis)),
        "source_prompt": source_text,
    }
    return (
        "你是 Wolven Hunt 的提示词维护器。只改进给定的单个 Markdown 提示词文件。"
        "必须精炼；新增一条策略时删除或压缩一条弱策略。"
        "必须保留 required_anchors 中的全部原文子串。"
        "只返回 JSON object: {\"prompt\": \"新的完整 Markdown 文件内容\"}。\n\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _candidate_text_from_response(response: ProviderResponse) -> str:
    data = json.loads(response.content)
    if not isinstance(data, dict) or not isinstance(data.get("prompt"), str):
        raise ValueError("prompt evolution response must contain string field 'prompt'")
    return cast(str, data["prompt"])

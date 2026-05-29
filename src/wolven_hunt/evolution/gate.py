from __future__ import annotations

from dataclasses import dataclass

from .scoring import WindowScore


@dataclass(frozen=True, slots=True)
class GateResult:
    accepted: bool
    reasons: tuple[str, ...]
    target_delta: float
    max_regression: float
    baseline_fallback_rate: float
    challenger_fallback_rate: float

    def to_json(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "target_delta": self.target_delta,
            "max_regression": self.max_regression,
            "baseline_fallback_rate": self.baseline_fallback_rate,
            "challenger_fallback_rate": self.challenger_fallback_rate,
        }


def evaluate_gate(
    *,
    target_axis: str,
    baseline: WindowScore,
    challenger: WindowScore,
    min_margin: float,
    regression_tolerance: float,
    generation_valid: bool = True,
) -> GateResult:
    reasons: list[str] = []
    baseline_target = baseline.axis_scores.get(target_axis)
    challenger_target = challenger.axis_scores.get(target_axis)
    if baseline_target is None or challenger_target is None:
        target_delta = 0.0
        reasons.append("missing_target_axis_score")
    else:
        target_delta = challenger_target.average - baseline_target.average
        if target_delta < min_margin:
            reasons.append("target_margin_not_met")

    max_regression = 0.0
    for axis_key, base_axis in baseline.axis_scores.items():
        if axis_key == target_axis:
            continue
        challenge_axis = challenger.axis_scores.get(axis_key)
        if challenge_axis is None:
            continue
        regression = base_axis.average - challenge_axis.average
        max_regression = max(max_regression, regression)
        if regression > regression_tolerance:
            reasons.append("other_axis_regression")
            break

    if challenger.fallback_rate > baseline.fallback_rate:
        reasons.append("fallback_rate_increased")
    if not generation_valid:
        reasons.append("generation_invalid")

    return GateResult(
        accepted=not reasons,
        reasons=tuple(reasons),
        target_delta=target_delta,
        max_regression=max_regression,
        baseline_fallback_rate=baseline.fallback_rate,
        challenger_fallback_rate=challenger.fallback_rate,
    )


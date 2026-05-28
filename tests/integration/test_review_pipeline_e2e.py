from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_review_pipeline import _StubProvider

from wolven_hunt.config.settings import Settings
from wolven_hunt.storage import review_pipeline


@pytest.fixture
def e2e_inputs() -> dict[str, Any]:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "review_e2e_events.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def e2e_report(e2e_inputs: dict[str, Any]) -> dict[str, Any]:
    settings = Settings(review_provider="litellm", review_api_key="x")
    provider = _StubProvider()
    return review_pipeline.run_pipeline_sync(
        game_id="e2e",
        events=tuple(e2e_inputs["events"]),
        narrative_rows=tuple(e2e_inputs["narrative_rows"]),
        reveal=e2e_inputs["reveal"],
        seat_presentation={
            int(seat): value for seat, value in e2e_inputs["seat_presentation"].items()
        },
        settings=settings,
        provider=provider,
    )


def test_multi_dimension_scoring(e2e_report: dict[str, Any]) -> None:
    score_keys = (
        "speech",
        "reasoning",
        "voting",
        "camp_contribution",
        "information_control",
        "role_duty",
    )
    role_duty_labels = {
        "wolf": "狼队协同",
        "villager": "平民职责",
        "seer": "查验价值",
        "witch": "药水决策",
        "guard": "守护判断",
    }
    for player in e2e_report["players"]:
        scores = player["scores"]
        assert tuple(score["key"] for score in scores) == score_keys
        assert all(0 <= score["value"] <= 100 for score in scores)
        assert scores[5]["label"] == role_duty_labels[player["role"]]
        values = [score["value"] for score in scores]
        assert len(set(values)) >= 3, f"seat {player['seat']} scores too flat: {values}"


def test_key_decisions_structure(e2e_report: dict[str, Any]) -> None:
    decisions = e2e_report["key_decisions"]
    assert 1 <= len(decisions) <= 4
    for decision in decisions:
        assert decision["title"] and decision["title"] != decision["phase"]
        assert len(decision["analysis"]) >= 20
        assert len(decision["impact"]) >= 20
        assert "actors_involved" not in decision


def test_counterfactuals_anchored_and_diverse(e2e_report: dict[str, Any]) -> None:
    counterfactuals = e2e_report["counterfactuals"]
    assert 2 <= len(counterfactuals) <= 5
    for counterfactual in counterfactuals:
        assert "号" in counterfactual["premise"]
        assert any(
            verb in counterfactual["premise"]
            for verb in ("改投", "解释", "弃票", "查验", "守护", "起跳", "保留", "回应", "改做")
        )
        assert any(
            keyword in counterfactual["likely_outcome"]
            for keyword in ("票型", "放逐", "夜间", "局势", "站边", "胜负")
        )
        assert "多沟通" not in counterfactual["lesson"]
        assert "更谨慎" not in counterfactual["lesson"]
    assert len({counterfactual["premise"] for counterfactual in counterfactuals}) == len(
        counterfactuals
    )


def test_structured_report_schema(e2e_report: dict[str, Any]) -> None:
    assert e2e_report["schema_version"] == "1.1"
    assert set(e2e_report.keys()) >= {
        "schema_version",
        "game_id",
        "generated_at",
        "generation_mode",
        "summary",
        "leaderboard",
        "players",
        "key_decisions",
        "counterfactuals",
    }
    assert set(e2e_report["summary"].keys()) >= {
        "winner",
        "verdict",
        "turning_points",
        "overall_assessment",
    }
    assert len(e2e_report["players"]) == 10
    assert '"label": "技能"' not in json.dumps(e2e_report, ensure_ascii=False)


def test_leaderboard_sorted_and_facets_present(e2e_report: dict[str, Any]) -> None:
    leaderboard = e2e_report["leaderboard"]
    assert len(leaderboard) == 10
    scores = [item["overall_score"] for item in leaderboard]
    assert scores == sorted(scores, reverse=True)
    assert [item["rank"] for item in leaderboard] == list(range(1, 11))
    for item in leaderboard:
        assert len(item["reason"]) >= 50, f"seat {item['seat']} reason too short"
        for banned in (
            "公开信息利用较稳定",
            "排序理由",
            "综合表现来自公开发言、票型和技能节点的结构化评估",
        ):
            assert banned not in item["reason"]


def test_personalization_no_duplication(e2e_report: dict[str, Any]) -> None:
    evaluations = [player["evaluation"] for player in e2e_report["players"]]
    assert len(set(evaluations)) == len(evaluations)
    strengths = [tuple(player["strengths"]) for player in e2e_report["players"]]
    assert len(set(strengths)) == len(strengths)

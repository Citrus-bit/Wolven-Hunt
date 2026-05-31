from __future__ import annotations

import json

import pytest

from wolven_hunt.config.settings import Settings
from wolven_hunt.storage import review_report


def test_mock_review_report_uses_distinct_player_wording() -> None:
    report = review_report.build_mock_review_report(
        game_id="game-review-distinct",
        reveal={
            "winner": "good",
            "seats": [
                {"seat": 1, "role": "wolf", "alive": False},
                {"seat": 2, "role": "villager", "alive": True},
                {"seat": 3, "role": "seer", "alive": False},
            ],
            "highlights": [{"seq": 9, "summary": "第1天放逐 1 号玩家"}],
        },
        seat_presentation={},
        narrative_rows=(
            {
                "seq": 2,
                "day": 1,
                "phase": "DAY_SPEECH",
                "kind": "speech",
                "actor": 2,
                "text": "2号: 1号视角太满, 我会重点看他。",
            },
            {
                "seq": 3,
                "day": 1,
                "phase": "DAY_SPEECH",
                "kind": "speech",
                "actor": 3,
                "text": "3号: 我查验2号是好人。",
            },
        ),
        events=(
            {
                "seq": 1,
                "day": 1,
                "phase": "NIGHT_WOLF_CHAT",
                "type": "wolf_chat_message",
                "actor": 1,
                "payload": {"text": "先打3号预言家压力。"},
            },
            {
                "seq": 4,
                "day": 1,
                "phase": "DAY_VOTE",
                "type": "vote_cast",
                "actor": 2,
                "payload": {"target": 1},
            },
            {
                "seq": 5,
                "day": 1,
                "phase": "DAY_VOTE",
                "type": "vote_cast",
                "actor": 3,
                "payload": {"target": 1},
            },
            {
                "seq": 6,
                "day": 1,
                "phase": "DAY_EXILE",
                "type": "exile",
                "actor": None,
                "payload": {"seat": 1},
            },
            {
                "seq": 8,
                "day": 2,
                "phase": "NIGHT_RESOLVE",
                "type": "death_at_night",
                "actor": None,
                "payload": {"seat": 3},
            },
        ),
    )

    players = report["players"]
    evaluations = {player["evaluation"] for player in players}
    strengths = {tuple(player["strengths"]) for player in players}
    suggestions = {tuple(player["suggestions"]) for player in players}

    assert len(evaluations) == len(players)
    assert len(strengths) == len(players)
    assert len(suggestions) == len(players)
    assert all("本局以" in item["reason"] for item in report["leaderboard"])
    assert all("排名主要来自" in item["reason"] for item in report["leaderboard"])
    assert all("短板是" in item["reason"] for item in report["leaderboard"])
    assert all("公开" in item["analysis"] for item in report["key_decisions"])
    assert all(
        any(keyword in item["likely_outcome"] for keyword in ("票型", "局势", "站边", "夜死"))
        for item in report["counterfactuals"]
    )
    assert any("狼聊" in item for item in players[0]["evidence"])
    assert "技能" not in json.dumps(report, ensure_ascii=False)


def test_mock_review_report_marks_human_player_wording() -> None:
    report = review_report.build_mock_review_report(
        game_id="game-human-review",
        reveal={
            "winner": "good",
            "seats": [{"seat": 2, "role": "villager", "alive": True}],
            "highlights": [],
        },
        seat_presentation={2: {"nickname": "你自己", "icon_path": "/assets/lobby/human_player.png"}},
        seat_agent_kinds={2: "human"},
        narrative_rows=(),
        events=(),
    )

    assert "真人玩家" in report["players"][0]["evaluation"]
    assert "真人玩家" in report["leaderboard"][0]["reason"]


def test_generate_review_report_routes_litellm_to_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.test_review_pipeline import _StubProvider

    from wolven_hunt.storage import review_report as rr

    stub = _StubProvider()
    monkeypatch.setattr(rr, "_review_provider", lambda settings: stub)
    settings = Settings(review_provider="litellm", review_api_key="x")

    report = rr.generate_review_report(
        game_id="g1",
        events=(
            {
                "seq": 1,
                "day": 1,
                "phase": "DAY_SPEECH",
                "type": "speech",
                "actor": 1,
                "payload": {"text": "我"},
            },
        ),
        narrative_rows=(),
        reveal={
            "winner": "good",
            "seats": [{"seat": 1, "role": "wolf", "alive": False}],
        },
        seat_presentation={1: {"nickname": "A", "icon_path": ""}},
        settings=settings,
    )

    assert report["generation_mode"] == "real_ai"
    assert len(report["players"]) == 1
    assert len(stub.calls) == 2


def test_review_provider_omits_reasoning_effort_for_custom_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wolven_hunt.storage import review_report as rr

    captured: dict[str, object] = {}

    class FakeReviewProvider:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(rr, "LiteLLMProvider", FakeReviewProvider)

    provider = rr._review_provider(
        Settings(
            review_provider="litellm",
            review_api_key="x",
            review_base_url="https://yunwu.ai/v1",
            review_model="gpt-5.5",
        )
    )

    assert isinstance(provider, FakeReviewProvider)
    assert captured["model"] == "gpt-5.5"
    assert captured["base_url"] == "https://yunwu.ai/v1"
    assert captured["reasoning_effort"] is None

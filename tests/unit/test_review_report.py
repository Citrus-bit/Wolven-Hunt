from __future__ import annotations

import json

import pytest

from wolven_hunt.storage import review_report


def test_build_review_prompt_loads_review_template_and_payload() -> None:
    prompt = review_report.build_review_prompt(
        game_id="game-review-template",
        events=(
            {
                "seq": 7,
                "day": 1,
                "phase": "DAY_VOTE",
                "type": "vote_cast",
                "actor": 2,
                "payload": {"target": 5},
            },
        ),
        narrative_rows=(
            {
                "seq": 3,
                "day": 1,
                "phase": "DAY_SPEECH",
                "kind": "speech",
                "actor": 2,
                "text": "2号: 我怀疑5号的票型。",
            },
        ),
        reveal={
            "winner": "good",
            "seats": [{"seat": 2, "role": "villager", "alive": True}],
            "highlights": [],
        },
        seat_presentation={2: {"nickname": "测试玩家", "icon_path": "/assets/lobby/a.png"}},
    )

    assert "Wolven Hunt 赛后复盘评审 v1" in prompt
    assert (
        "每名玩家的 evaluation、evidence、strengths、mistakes、suggestions 都必须围绕该玩家独有的公开证据写"
        in prompt
    )
    assert "禁止无事实支撑地复用泛化句式" in prompt
    assert "leaderboard.reason 必须是一段话概括该模型/玩家本局整体表现" in prompt
    assert "不要引用 raw response、provider、API key、prompt" in prompt

    payload = json.loads(prompt[prompt.rindex("\n\n{") + 2 :])
    assert payload["game_id"] == "game-review-template"
    assert payload["spectator_events"][0]["type"] == "vote_cast"
    assert payload["seat_presentation"]["2"]["nickname"] == "测试玩家"
    assert payload["score_axes"][-1]["label_by_role"]["villager"] == "平民职责"


def test_build_review_prompt_fails_when_template_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(review_report, "REVIEW_PROMPT_TEMPLATE", tmp_path / "missing.md")

    with pytest.raises(FileNotFoundError):
        review_report.build_review_prompt(
            game_id="game-review-missing-template",
            events=(),
            narrative_rows=(),
            reveal={"winner": "good", "seats": [], "highlights": []},
            seat_presentation={},
        )


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
    assert any("狼聊" in item for item in players[0]["evidence"])
    assert "技能" not in json.dumps(report, ensure_ascii=False)

from __future__ import annotations

# ruff: noqa: RUF001
import json
from typing import Any

from wolven_hunt.config.settings import Settings
from wolven_hunt.llm.provider import MockLLMProvider, ProviderResponse
from wolven_hunt.storage import review_pipeline


class _StubProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(model="stub")
        self.calls: list[str] = []

    async def acomplete(self, *, seat: Any, phase: str, prompt: str, rng: Any) -> ProviderResponse:
        del seat, phase, rng
        self.calls.append(prompt)
        if "Wolven Hunt 全局复盘" in prompt:
            payload = {
                "summary": {
                    "winner": "good",
                    "verdict": "好人靠 D1 集火放逐 1 号狼赢下。",
                    "turning_points": [
                        "D1 DAY_VOTE(seq=5) 1号收票被放逐",
                        "D2 NIGHT_RESOLVE 后狼队目标空间被压缩",
                    ],
                    "overall_assessment": (
                        "好人阵营通过首日公开发言和集中票型建立优势，狼人没能把压力转移到外置位。"
                        "关键节点来自 D1 票型收束与后续夜间目标空间变化，信息缺口主要在早期身份自证不足。"
                    ),
                },
                "key_decisions": [
                    {
                        "day": 1,
                        "phase": "DAY_VOTE",
                        "seq": 5,
                        "title": "1号被集火放逐",
                        "analysis": "2、3号把白天怀疑落实到 1 号票型，1 号承受主要压力并暴露狼队抗推空间不足。",
                        "impact": "这个公开票型直接改变存活结构，也压缩了狼人夜间目标空间和第二天站边余地。",
                        "actors_involved": {"actor": [2, 3], "target": [1], "voter": [2, 3]},
                    },
                    {
                        "day": 2,
                        "phase": "DAY_SPEECH",
                        "seq": 8,
                        "title": "4号补充查验链带动站边",
                        "analysis": "4号用公开发言补足查验链，8号成为被保护的好人锚点，场上压力转向狼坑。",
                        "impact": "该节点让好人后续票型更容易集中，狼人很难继续把放逐目标推回强好人位置。",
                        "actors_involved": {"actor": [4], "target": [8], "voter": []},
                    },
                ],
                "counterfactuals": [
                    {
                        "premise": "如果 1 号在 D1 DAY_SPEECH(seq=2) 解释票型来源",
                        "anchor_seat": 1,
                        "anchor_decision_day": 1,
                        "likely_outcome": "D1 票型可能分散到 3 号，放逐对象和后续站边会更摇摆。",
                        "lesson": "狼人首日要预留可被公开发言验证的辩解口径。",
                    },
                    {
                        "premise": "如果 2 号在 D1 DAY_VOTE 改投 3 号",
                        "anchor_seat": 2,
                        "anchor_decision_day": 1,
                        "likely_outcome": "首日放逐可能延后，夜间目标空间会重新打开。",
                        "lesson": "投票前要让怀疑链自然导向目标，避免被反向复盘票型。",
                    },
                ],
            }
        else:
            prompt_payload = _payload_from_prompt(prompt)
            dossier = prompt_payload["dossier"]
            seat_number = int(dossier["seat"])
            role = str(dossier["role"])
            role_label = str(dossier["role_duty_label"])
            speech_rank = int(dossier["ranking"]["speech_char_rank"])
            received_votes = int(dossier["ranking"]["received_votes_total"])
            base = min(88, 54 + seat_number)
            payload = {
                "scores": [
                    {"key": "speech", "label": "发言质量", "value": base + 8},
                    {"key": "reasoning", "label": "推理逻辑", "value": base + 2},
                    {"key": "voting", "label": "票型执行", "value": base + 5},
                    {"key": "camp_contribution", "label": "阵营贡献", "value": base - 1},
                    {"key": "information_control", "label": "信息控制", "value": base + 11},
                    {"key": "role_duty", "label": role_label, "value": base + 4},
                ],
                "score_rationales": {
                    "speech": f"{seat_number}号发言字数排第 {speech_rank}，有明确原句可回看。",
                    "reasoning": f"{seat_number}号围绕自己的公开节点形成了可追踪判断。",
                    "voting": f"{seat_number}号投票和被投记录共 {received_votes} 次压力。",
                    "camp_contribution": f"{seat_number}号结合胜负和关键节点评估阵营贡献。",
                    "information_control": f"{seat_number}号身份暴露节奏主要看公开发言和狼聊。",
                    "role_duty": f"{seat_number}号按 {role_label} 评估角色职责。",
                },
                "overall_score": base + 5,
                "evaluation": (
                    f"{seat_number}号作为{role}，本局引用「具体引语{seat_number}」形成个人证据。"
                    f"全局发言字数排第 {speech_rank}，被投 {received_votes} 次，评价锚点来自自己的发言、票型和终局状态。"
                ),
                "evidence": [
                    f"D1 DAY_SPEECH(seq={seat_number}) 发言「具体引语{seat_number}」",
                    f"D1 DAY_VOTE {seat_number}号投票记录",
                    f"终局 {seat_number}号角色为 {role}",
                ],
                "strengths": [f"{seat_number}号能把公开发言落到票型", f"{seat_number}号保留了个人证据"],
                "mistakes": [f"{seat_number}号主要短板是关键节点解释不足"],
                "suggestions": [f"{seat_number}号下一局先声明怀疑链", f"{seat_number}号投票后补充验证条件"],
                "personal_counterfactual": {
                    "premise": f"如果 {seat_number}号在 D1 DAY_SPEECH 改做回应被投压力",
                    "likely_outcome": "公开票型和站边可能出现结构变化。",
                    "lesson": "被压座位要先回应票源理由，再给出反推对象。",
                },
                "leaderboard_reason": (
                    f"{seat_number}号本局以{role}身份参与对局，关键证据包括发言「具体引语{seat_number}」"
                    f"和 D1 票型记录。排名核心原因是综合分来自个人证据而非模板描述。"
                    f"主要短板是关键节点解释不够充分，需要下一局补足验证链。 leaderboard 理由"
                ),
            }
        return ProviderResponse(content=json.dumps(payload, ensure_ascii=False), model="stub")


def test_pipeline_assembles_full_report_from_two_stages() -> None:
    settings = Settings(review_provider="mock")
    provider = _StubProvider()

    report = review_pipeline.run_pipeline_sync(
        game_id="game-1",
        events=(
            {
                "seq": 2,
                "day": 1,
                "phase": "DAY_SPEECH",
                "type": "speech",
                "actor": 1,
                "payload": {"text": "我没事"},
            },
            {
                "seq": 3,
                "day": 1,
                "phase": "DAY_SPEECH",
                "type": "speech",
                "actor": 2,
                "payload": {"text": "我投1号"},
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
                "phase": "DAY_EXILE",
                "type": "exile",
                "actor": None,
                "payload": {"seat": 1},
            },
        ),
        narrative_rows=(),
        reveal={
            "winner": "good",
            "seats": [
                {"seat": 1, "role": "wolf", "alive": False},
                {"seat": 2, "role": "villager", "alive": True},
            ],
        },
        seat_presentation={
            1: {"nickname": "A", "icon_path": ""},
            2: {"nickname": "B", "icon_path": ""},
        },
        seat_agent_kinds={2: "human"},
        settings=settings,
        provider=provider,
    )

    assert report["schema_version"] == "1.1"
    assert len(report["players"]) == 2
    assert len(report["leaderboard"]) == 2
    scores = [player["overall_score"] for player in report["leaderboard"]]
    assert scores == sorted(scores, reverse=True)
    assert len(provider.calls) == 3
    assert all("leaderboard 理由" in item["reason"] for item in report["leaderboard"])
    assert all("actors_involved" not in item for item in report["key_decisions"])
    human_prompt = next(
        prompt for prompt in provider.calls if '"agent_type": "human"' in prompt
    )
    human_payload = _payload_from_prompt(human_prompt)
    assert human_payload["dossier"]["agent_type"] == "human"
    assert "真人玩家" in human_payload["agent_note"]


def test_global_stage_retries_before_real_report_success() -> None:
    settings = Settings(
        review_provider="litellm",
        review_api_key="x",
        review_max_retries=2,
        review_retry_backoff_delays_seconds=(),
    )
    provider = _FlakyReviewProvider(fail_global_attempts=1)

    report = review_pipeline.run_pipeline_sync(
        **_sample_pipeline_kwargs(),
        settings=settings,
        provider=provider,
    )

    assert report["generation_mode"] == "real_ai"
    assert provider.global_attempts == 2


def test_per_seat_stage_retries_before_mock_row_fallback() -> None:
    settings = Settings(
        review_provider="litellm",
        review_api_key="x",
        review_max_retries=2,
        review_retry_backoff_delays_seconds=(),
    )
    provider = _FlakyReviewProvider(fail_per_seat_attempts={2: 1})

    report = review_pipeline.run_pipeline_sync(
        **_sample_pipeline_kwargs(),
        settings=settings,
        provider=provider,
    )

    assert report["generation_mode"] == "real_ai"
    assert provider.per_seat_attempts[2] == 2
    seat_2 = next(player for player in report["players"] if player["seat"] == 2)
    assert "具体引语2" in seat_2["evaluation"]


def test_per_seat_schema_failure_retries_before_success() -> None:
    settings = Settings(
        review_provider="litellm",
        review_api_key="x",
        review_max_retries=2,
        review_retry_backoff_delays_seconds=(),
    )
    provider = _InvalidFirstPerSeatProvider(invalid_seat=2)

    report = review_pipeline.run_pipeline_sync(
        **_sample_pipeline_kwargs(),
        settings=settings,
        provider=provider,
    )

    assert report["generation_mode"] == "real_ai"
    assert provider.per_seat_attempts[2] == 2
    seat_2 = next(player for player in report["players"] if player["seat"] == 2)
    assert "具体引语2" in seat_2["evaluation"]


def test_global_stage_exhaustion_uses_offline_report_after_retries() -> None:
    settings = Settings(
        review_provider="litellm",
        review_api_key="x",
        review_max_retries=2,
        review_retry_backoff_delays_seconds=(),
    )
    provider = _FlakyReviewProvider(fail_global_attempts=3)

    report = review_pipeline.run_pipeline_sync(
        **_sample_pipeline_kwargs(),
        settings=settings,
        provider=provider,
    )

    assert report["generation_mode"] == "offline_mock"
    assert provider.global_attempts == 3


class _FlakyReviewProvider(_StubProvider):
    def __init__(
        self,
        *,
        fail_global_attempts: int = 0,
        fail_per_seat_attempts: dict[int, int] | None = None,
    ) -> None:
        super().__init__()
        self.fail_global_attempts = fail_global_attempts
        self.fail_per_seat_attempts = dict(fail_per_seat_attempts or {})
        self.global_attempts = 0
        self.per_seat_attempts: dict[int, int] = {}

    async def acomplete(self, *, seat: Any, phase: str, prompt: str, rng: Any) -> ProviderResponse:
        if phase == "REVIEW_GLOBAL":
            self.global_attempts += 1
            if self.global_attempts <= self.fail_global_attempts:
                raise RuntimeError("temporary global review failure")
        if phase == "REVIEW_PER_SEAT":
            seat_number = int(seat.number)
            attempt = self.per_seat_attempts.get(seat_number, 0) + 1
            self.per_seat_attempts[seat_number] = attempt
            if attempt <= self.fail_per_seat_attempts.get(seat_number, 0):
                raise RuntimeError("temporary per-seat review failure")
        return await super().acomplete(seat=seat, phase=phase, prompt=prompt, rng=rng)


class _InvalidFirstPerSeatProvider(_StubProvider):
    def __init__(self, *, invalid_seat: int) -> None:
        super().__init__()
        self.invalid_seat = invalid_seat
        self.per_seat_attempts: dict[int, int] = {}

    async def acomplete(self, *, seat: Any, phase: str, prompt: str, rng: Any) -> ProviderResponse:
        if phase == "REVIEW_PER_SEAT":
            seat_number = int(seat.number)
            attempt = self.per_seat_attempts.get(seat_number, 0) + 1
            self.per_seat_attempts[seat_number] = attempt
            if seat_number == self.invalid_seat and attempt == 1:
                return ProviderResponse(
                    content=json.dumps({"scores": []}, ensure_ascii=False),
                    model="stub",
                )
        return await super().acomplete(seat=seat, phase=phase, prompt=prompt, rng=rng)


def _sample_pipeline_kwargs() -> dict[str, Any]:
    return {
        "game_id": "game-retry",
        "events": (
            {
                "seq": 2,
                "day": 1,
                "phase": "DAY_SPEECH",
                "type": "speech",
                "actor": 1,
                "payload": {"text": "我没事"},
            },
            {
                "seq": 3,
                "day": 1,
                "phase": "DAY_SPEECH",
                "type": "speech",
                "actor": 2,
                "payload": {"text": "我投1号"},
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
                "phase": "DAY_EXILE",
                "type": "exile",
                "actor": None,
                "payload": {"seat": 1},
            },
        ),
        "narrative_rows": (),
        "reveal": {
            "winner": "good",
            "seats": [
                {"seat": 1, "role": "wolf", "alive": False},
                {"seat": 2, "role": "villager", "alive": True},
            ],
        },
        "seat_presentation": {
            1: {"nickname": "A", "icon_path": ""},
            2: {"nickname": "B", "icon_path": ""},
        },
        "seat_agent_kinds": {2: "human"},
    }


def _payload_from_prompt(prompt: str) -> dict[str, Any]:
    return json.loads(prompt[prompt.rindex("\n\n{") + 2 :])

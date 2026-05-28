from __future__ import annotations

import json
from time import sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings
from wolven_hunt.core.seat import Role

CONFIG_PATH = "configs/games/classic_10.yaml"
SEATS = range(1, 11)


def test_api_healthz(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not any(tmp_path.iterdir())


def test_api_creates_game_and_returns_spectator_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-seed-001",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        events_json = _wait_for_events(client, game_id)
        event_types = {event["type"] for event in events_json}
        assert "game_start" in event_types
        game_start = next(event for event in events_json if event["type"] == "game_start")
        assert "role_assignment" in game_start["payload"]

        _wait_until_finished(client, game_id)
        events_json = client.get(f"/games/{game_id}/events").json()
        event_types = {event["type"] for event in events_json}
        assert "llm_call" not in event_types
        assert "seer_check_result" not in event_types
        assert "guard_protect" not in event_types
        assert "wolf_kill_vote" not in event_types
        assert "wolf_kill_decided" not in event_types
        assert "wolf_chat_message" in event_types
        rejected = client.post(
            f"/games/{game_id}/speech",
            json={"seat": 1, "text": "hello"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "action_rejected"


def test_api_accepts_new_agent_specs_without_timeout(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-agent-spec-001",
                "agents": {
                    str(seat): {
                        "kind": "llm",
                        "provider": "mock",
                        "model": "mock/deterministic",
                    }
                    for seat in SEATS
                },
                "pacing": "off",
            },
        )
        assert created.status_code == 200

        _wait_until_finished(client, created.json()["game_id"])


def test_api_game_agent_spec_passes_thinking_enabled_to_provider(
    monkeypatch,
    tmp_path,
) -> None:
    import wolven_hunt.orchestration.runtime as runtime_module
    from wolven_hunt.llm.provider import MockLLMProvider

    captured: list[object] = []

    def fake_build_provider(config, *, phase_timeout_seconds=None):
        del phase_timeout_seconds
        captured.append(config)
        return MockLLMProvider(model="mock/deterministic")

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setattr(runtime_module, "build_provider_from_config", fake_build_provider)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-thinking-enabled",
                "agents": {
                    "1": {
                        "kind": "llm",
                        "provider": "litellm",
                        "model": "qwen3.6-flash",
                        "api_key": "test-secret",
                        "thinking_enabled": True,
                    }
                },
                "pacing": "off",
            },
        )
        assert created.status_code == 200

    assert any(
        getattr(config, "model", "") == "qwen3.6-flash"
        and getattr(config, "thinking_enabled", False) is True
        for config in captured
    )


def test_api_persists_spectator_safe_seat_presentation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-seat-presentation-001",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
                "pacing": "off",
                "seat_presentation": {
                    "1": {
                        "nickname": "GPT",
                        "icon_path": "/assets/lobby/model_icon_gpt.png",
                    }
                },
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        summary = client.get(f"/games/{game_id}").json()

    manifest_text = (tmp_path / game_id / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert summary["seat_presentation"]["1"] == {
        "nickname": "GPT",
        "icon_path": "/assets/lobby/model_icon_gpt.png",
    }
    assert manifest["prompt_pack_version"] == "v5"
    assert "seat_presentation" in manifest_text
    assert "api_key" not in manifest_text
    assert "base_url" not in manifest_text
    assert "mock/deterministic" not in manifest_text


def test_api_returns_narrative_for_offline_run(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-offline-narrative",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
                "pacing": "off",
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        get_registry()._sessions.pop(game_id)

        narrative = client.get(f"/games/{game_id}/narrative").json()
        assert any(row["kind"] == "speech" for row in narrative)
        after = int(narrative[0]["seq"])
        incremental = client.get(f"/games/{game_id}/narrative?after={after}").json()
        assert all(int(row["seq"]) > after for row in incremental)


def test_api_rejects_remote_seat_presentation_icons(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-seat-presentation-bad",
                "seat_presentation": {
                    "1": {
                        "nickname": "remote",
                        "icon_path": "https://example.test/avatar.png",
                    }
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert not any(tmp_path.iterdir())


def test_model_test_mock_does_not_write_run_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/models/test",
            json={"provider": "mock", "model": "mock/deterministic"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": None}
    assert not any(tmp_path.iterdir())


def test_model_test_litellm_receives_thinking_extra_body(monkeypatch, tmp_path) -> None:
    from wolven_hunt.llm.provider import _litellm_module

    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7897")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7897")
    litellm = _litellm_module()
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "model": kwargs["model"],
            "usage": {},
        }

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(litellm, "completion", fake_completion)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/models/test",
            json={
                "provider": "litellm",
                "model": "qwen3.6-flash",
                "base_url": "https://example.test/v1",
                "api_key": "test-secret",
                "thinking_enabled": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": None}
    assert captured["model"] == "custom_openai/qwen3.6-flash"
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["extra_body"] == {"enable_thinking": True}
    assert litellm.client_session._trust_env is False
    assert litellm.aclient_session._trust_env is False
    assert not any(tmp_path.iterdir())


def test_model_test_litellm_defaults_qwen_thinking_off(monkeypatch, tmp_path) -> None:
    from wolven_hunt.llm.provider import _litellm_module

    litellm = _litellm_module()
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "model": kwargs["model"],
            "usage": {},
        }

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(litellm, "completion", fake_completion)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/models/test",
            json={
                "provider": "litellm",
                "model": "qwen3.6-flash",
                "base_url": "https://example.test/v1",
                "api_key": "test-secret",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": None}
    assert captured["extra_body"] == {"enable_thinking": False}
    assert not any(tmp_path.iterdir())


def test_model_test_litellm_applies_gpt_max_reasoning(monkeypatch, tmp_path) -> None:
    from wolven_hunt.llm.provider import _litellm_module

    litellm = _litellm_module()
    captured: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "model": kwargs["model"],
            "usage": {},
        }

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(litellm, "completion", fake_completion)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/models/test",
            json={
                "provider": "litellm",
                "model": "gpt-5.5",
                "base_url": "https://example.test/v1",
                "api_key": "test-secret",
                "thinking_enabled": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": None}
    assert captured["model"] == "custom_openai/gpt-5.5"
    assert captured["reasoning_effort"] == "xhigh"
    assert "extra_body" not in captured
    assert not any(tmp_path.iterdir())


def test_model_test_litellm_failure_message_is_sanitized(monkeypatch, tmp_path) -> None:
    import litellm

    def fake_completion(**kwargs: object) -> dict[str, object]:
        raise RuntimeError(f"upstream rejected api_key={kwargs['api_key']} sk-1234567890")

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(litellm, "completion", fake_completion)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/models/test",
            json={
                "provider": "litellm",
                "model": "mimo-v2.5-pro",
                "api_key": "secret-token",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "secret-token" not in body["message"]
    assert "sk-1234567890" not in body["message"]
    assert "[redacted]" in body["message"]
    assert len(body["message"]) <= 200
    assert not any(tmp_path.iterdir())


def test_review_report_requires_finished_game(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-unfinished",
                "pacing": "off",
                "start_paused": True,
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        missing = client.get(f"/games/{game_id}/review-report")
        assert missing.status_code == 404
        assert missing.json()["code"] == "report_not_generated"

        response = client.post(f"/games/{game_id}/review-report")
        assert response.status_code == 404
        assert response.json()["code"] == "game_not_finished"
        assert not (tmp_path / game_id / "review_report.json").exists()


def test_review_report_generation_is_cached_and_spectator_safe(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-finished",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
                "seat_presentation": {
                    "1": {
                        "nickname": "GPT",
                        "icon_path": "/assets/lobby/model_icon_gpt.png",
                    }
                },
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        events_path = tmp_path / game_id / "events.jsonl"
        before_events = events_path.read_text(encoding="utf-8")
        response = client.post(f"/games/{game_id}/review-report")
        assert response.status_code == 200
        report = response.json()
        assert report["schema_version"] == "1.1"
        assert report["generation_mode"] == "offline_mock"
        assert report["game_id"] == game_id
        assert len(report["players"]) == 10
        assert len(report["leaderboard"]) == 10
        assert len(report["players"][0]["scores"]) == 6
        assert [score["key"] for score in report["players"][0]["scores"]] == [
            "speech",
            "reasoning",
            "voting",
            "camp_contribution",
            "information_control",
            "role_duty",
        ]
        assert report["players"][0]["evaluation"]
        assert report["players"][0]["evidence"]
        villager = next(player for player in report["players"] if player["role"] == "villager")
        assert villager["scores"][-1]["label"] == "平民职责"
        assert "技能" not in json.dumps(villager, ensure_ascii=False)
        assert _unique_count(player["evaluation"] for player in report["players"]) >= 8
        assert _unique_count(tuple(player["strengths"]) for player in report["players"]) >= 6
        assert _unique_count(tuple(player["mistakes"]) for player in report["players"]) >= 6
        assert _unique_count(tuple(player["suggestions"]) for player in report["players"]) >= 6
        assert all("本局以" in item["reason"] for item in report["leaderboard"])
        assert all("排名主要来自" in item["reason"] for item in report["leaderboard"])
        assert all("短板是" in item["reason"] for item in report["leaderboard"])

        report_path = tmp_path / game_id / "review_report.json"
        assert report_path.exists()
        report_text = report_path.read_text(encoding="utf-8")
        assert "raw_response" not in report_text
        assert "api_key" not in report_text
        assert "prompt" not in report_text
        assert events_path.read_text(encoding="utf-8") == before_events

        cached = client.post(f"/games/{game_id}/review-report")
        assert cached.status_code == 200
        assert cached.json() == report
        fetched = client.get(f"/games/{game_id}/review-report")
        assert fetched.status_code == 200
        assert fetched.json() == report


def test_review_report_v1_cache_is_expired_and_regenerated(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-v1-cache",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        report_path = tmp_path / game_id / "review_report.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "game_id": game_id,
                    "generated_at": "2026-01-01T00:00:00Z",
                    "summary": {
                        "winner": "good",
                        "verdict": "旧报告",
                        "turning_points": [],
                        "overall_assessment": "旧 schema",
                    },
                    "leaderboard": [],
                    "players": [],
                    "key_decisions": [],
                    "counterfactuals": [],
                }
            ),
            encoding="utf-8",
        )

        missing = client.get(f"/games/{game_id}/review-report")
        assert missing.status_code == 404
        assert missing.json()["code"] == "report_not_generated"

        regenerated = client.post(f"/games/{game_id}/review-report")
        assert regenerated.status_code == 200
        assert regenerated.json()["schema_version"] == "1.1"
        assert json.loads(report_path.read_text(encoding="utf-8"))["schema_version"] == "1.1"


def test_review_report_litellm_provider_is_used_without_mock_downgrade(
    monkeypatch,
    tmp_path,
) -> None:
    import wolven_hunt.storage.review_report as review_report_module

    captured: list[dict[str, object]] = []

    class FakeReviewProvider:
        def __init__(
            self,
            *,
            model: str,
            api_key: str,
            base_url: str = "",
            timeout_seconds: float = 30.0,
            extra_body: dict[str, object] | None = None,
            reasoning_effort: str | None = None,
        ) -> None:
            captured.append(
                {
                    "model": model,
                    "api_key": api_key,
                    "base_url": base_url,
                    "timeout_seconds": timeout_seconds,
                    "extra_body": extra_body,
                    "reasoning_effort": reasoning_effort,
                }
            )

        def complete(self, *, seat, phase, prompt, rng):
            del seat, phase, rng
            assert "Wolven Hunt 赛后复盘评审 v1" in prompt
            assert "独有的公开证据" in prompt
            assert "leaderboard.reason 必须是一段话概括该模型/玩家本局整体表现" in prompt
            assert "key_decisions 选择 2-4 个最关键公开节点" in prompt
            assert "counterfactuals 必须基于 key_decisions 或公开证据" in prompt
            payload = json.loads(prompt[prompt.rindex("\n\n{") + 2 :])
            seat_presentation = {
                int(seat): value for seat, value in payload["seat_presentation"].items()
            }
            report = review_report_module.build_mock_review_report(
                game_id="fake",
                reveal=payload["role_reveal"],
                seat_presentation=seat_presentation,
                narrative_rows=tuple(payload["narrative_rows"]),
                events=tuple(payload["spectator_events"]),
            )
            content = {
                key: value
                for key, value in report.items()
                if key not in {"schema_version", "game_id", "generated_at", "generation_mode"}
            }
            from wolven_hunt.llm.provider import ProviderResponse

            return ProviderResponse(content=json.dumps(content, ensure_ascii=False), model="fake")

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "litellm")
    monkeypatch.setenv("WH_REVIEW_API_KEY", "review-secret")
    monkeypatch.setenv("WH_REVIEW_MODEL", "review-model")
    monkeypatch.setattr(review_report_module, "LiteLLMProvider", FakeReviewProvider)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-real-provider",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        response = client.post(f"/games/{game_id}/review-report")
        assert response.status_code == 200
        assert captured and captured[0]["api_key"] == "review-secret"
        assert captured[0]["model"] == "review-model"
        assert captured[0]["reasoning_effort"] is None
        assert response.json()["generation_mode"] == "real_ai"


def test_review_report_gpt55_uses_max_reasoning_effort(
    monkeypatch,
    tmp_path,
) -> None:
    import wolven_hunt.storage.review_report as review_report_module

    captured: list[dict[str, object]] = []

    class FakeReviewProvider:
        def __init__(self, **kwargs: object) -> None:
            captured.append(dict(kwargs))

        def complete(self, *, seat, phase, prompt, rng):
            del seat, phase, rng
            payload = json.loads(prompt[prompt.rindex("\n\n{") + 2 :])
            report = review_report_module.build_mock_review_report(
                game_id="fake",
                reveal=payload["role_reveal"],
                seat_presentation={
                    int(seat): value for seat, value in payload["seat_presentation"].items()
                },
                narrative_rows=tuple(payload["narrative_rows"]),
                events=tuple(payload["spectator_events"]),
            )
            content = {
                key: value
                for key, value in report.items()
                if key not in {"schema_version", "game_id", "generated_at", "generation_mode"}
            }
            from wolven_hunt.llm.provider import ProviderResponse

            return ProviderResponse(content=json.dumps(content, ensure_ascii=False), model="fake")

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "litellm")
    monkeypatch.setenv("WH_REVIEW_API_KEY", "review-secret")
    monkeypatch.setenv("WH_REVIEW_MODEL", "gpt-5.5")
    monkeypatch.setattr(review_report_module, "LiteLLMProvider", FakeReviewProvider)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-gpt55-max-reasoning",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        response = client.post(f"/games/{game_id}/review-report")

    assert response.status_code == 200
    assert captured and captured[0]["model"] == "gpt-5.5"
    assert captured[0]["reasoning_effort"] == "xhigh"
    assert captured[0]["extra_body"] == {}


def test_review_report_real_provider_failure_does_not_write_report(
    monkeypatch,
    tmp_path,
) -> None:
    import wolven_hunt.storage.review_report as review_report_module

    class FailingReviewProvider:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def complete(self, *, seat, phase, prompt, rng):
            del seat, phase, prompt, rng
            raise RuntimeError("provider failed with review-secret")

    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_REVIEW_PROVIDER", "litellm")
    monkeypatch.setenv("WH_REVIEW_API_KEY", "review-secret")
    monkeypatch.setattr(review_report_module, "LiteLLMProvider", FailingReviewProvider)
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "api-review-real-failure",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        _wait_until_finished(client, game_id)

        events_path = tmp_path / game_id / "events.jsonl"
        before_events = events_path.read_text(encoding="utf-8")
        response = client.post(f"/games/{game_id}/review-report")

        assert response.status_code == 502
        assert response.json()["code"] == "review_report_generation_failed"
        assert "review-secret" not in response.json()["message"]
        assert not (tmp_path / game_id / "review_report.json").exists()
        assert events_path.read_text(encoding="utf-8") == before_events


def test_api_queues_pending_speech_and_rejects_non_wolf_chat(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={"config_path": CONFIG_PATH, "seed": "api-live-001"},
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        client.post(f"/games/{game_id}/pause")

        session = get_registry().require(game_id)
        alive_seats = [player.seat.number for player in session.state.players if player.alive]
        non_wolf = next(
            player.seat.number for player in session.state.players if player.role is not Role.WOLF
        )
        rejected = client.post(
            f"/games/{game_id}/wolf_chat",
            json={"seat": non_wolf, "text": "not a wolf"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["details"]["rule_id"] == "text.actor_role"

        for seat in alive_seats:
            response = client.post(
                f"/games/{game_id}/speech",
                json={"seat": seat, "text": f"pending speech {seat}"},
            )
            assert response.status_code == 200

        client.post(f"/games/{game_id}/resume")

        for _ in range(100):
            events = client.get(f"/games/{game_id}/events").json()
            if any(
                event["type"] == "speech"
                and str(event["payload"].get("text", "")).startswith("pending speech")
                for event in events
            ):
                break
            sleep(0.02)
        else:
            raise AssertionError("pending speech was not consumed")


def _wait_until_finished(client: TestClient, game_id: str) -> None:
    for _ in range(250):
        summary = client.get(f"/games/{game_id}").json()
        if summary["status"] == "finished":
            return
        sleep(0.02)
    raise AssertionError("game did not finish")


def _wait_for_events(client: TestClient, game_id: str) -> list[dict[str, object]]:
    for _ in range(100):
        response = client.get(f"/games/{game_id}/events")
        assert response.status_code == 200
        events = response.json()
        if events:
            return events
        sleep(0.02)
    raise AssertionError("game did not emit events")


def _unique_count(values) -> int:
    return len(set(values))


def test_api_game_not_found_error_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/games/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "game_not_found"

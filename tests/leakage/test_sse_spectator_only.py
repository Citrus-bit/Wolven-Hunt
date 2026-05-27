from __future__ import annotations

from time import sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings

CONFIG_PATH = "configs/games/classic_10.yaml"
SEATS = range(1, 11)


def test_spectator_api_and_sse_hide_private_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "leakage-sse-seed",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        ).json()["game_id"]

        events = _wait_for_spectator_god_view_events(client, game_id)
        event_types = {event["type"] for event in events}
        assert {
            "llm_call",
            "guard_protect",
            "seer_check_result",
            "wolf_kill_vote",
            "wolf_kill_decided",
            "wolf_tie_random",
            "witch_action",
        }.isdisjoint(event_types)
        assert "wolf_chat_message" in event_types
        game_start = next(event for event in events if event["type"] == "game_start")
        assert "role_assignment" in game_start["payload"]
        assert "selected" not in game_start["payload"]
        assert "candidates" not in game_start["payload"]

        with client.stream("GET", f"/games/{game_id}/stream") as response:
            body = response.read().decode("utf-8")

        assert "llm_call" not in body
        assert "event: spectator_effect" in body
        assert "wolf_chat_message" in body
        assert "role_assignment" in body
        assert "seer_check_result" not in body
        assert "guard_protect" not in body
        assert "wolf_kill_vote" not in body
        assert "wolf_kill_decided" not in body
        assert "witch_action" not in body


def test_spectator_effects_are_private_event_projections_not_raw_event_leaks(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_PACING_PROFILE", "off")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "spectator-effects-are-projections",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
                "pacing": "off",
            },
        ).json()["game_id"]

        events = _wait_for_spectator_god_view_events(client, game_id)
        event_types = {event["type"] for event in events}
        assert {
            "guard_protect",
            "seer_check",
            "witch_action",
            "wolf_kill_decided",
        }.isdisjoint(event_types)

        effects = _wait_for_spectator_effect_kinds(
            client,
            game_id,
            {"guard_shield", "seer_vision", "wolf_attack"},
        )
        effect_kinds = {effect["kind"] for effect in effects}
        assert {"guard_shield", "seer_vision", "wolf_attack"}.issubset(effect_kinds)
        assert all("payload" not in effect for effect in effects)
        assert all("raw_response" not in str(effect) for effect in effects)


def _wait_for_spectator_god_view_events(
    client: TestClient, game_id: str
) -> list[dict[str, object]]:
    for _ in range(100):
        response = client.get(f"/games/{game_id}/events")
        assert response.status_code == 200
        events = response.json()
        event_types = {event["type"] for event in events}
        if "game_start" in event_types and "wolf_chat_message" in event_types:
            return events
        sleep(0.02)
    raise AssertionError("spectator god-view events did not include roles and wolf chat")


def _wait_for_spectator_effect_kinds(
    client: TestClient,
    game_id: str,
    expected_kinds: set[str],
) -> list[dict[str, object]]:
    for _ in range(100):
        response = client.get(f"/games/{game_id}/effects")
        assert response.status_code == 200
        effects = response.json()
        if expected_kinds.issubset({effect["kind"] for effect in effects}):
            return effects
        sleep(0.02)
    raise AssertionError("spectator-only effect projections were not published")

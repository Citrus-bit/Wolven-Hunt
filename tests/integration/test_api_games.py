from __future__ import annotations

from time import sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings
from wolven_hunt.core.seat import Role


def test_api_creates_game_and_returns_spectator_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": "configs/games/classic_8.yaml",
                "seed": "api-seed-001",
                "agents": {str(seat): "llm:mock" for seat in range(1, 9)},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        events_json = _wait_for_events(client, game_id)
        event_types = {event["type"] for event in events_json}
        assert "game_start" in event_types
        assert "llm_call" not in event_types
        assert "seer_check_result" not in event_types
        assert "wolf_chat_message" not in event_types

        _wait_until_finished(client, game_id)
        rejected = client.post(
            f"/games/{game_id}/speech",
            json={"seat": 1, "text": "hello"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "action_rejected"


def test_api_queues_pending_speech_and_rejects_non_wolf_chat(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={"config_path": "configs/games/classic_8.yaml", "seed": "api-live-001"},
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
    for _ in range(100):
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


def test_api_game_not_found_error_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/games/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "game_not_found"

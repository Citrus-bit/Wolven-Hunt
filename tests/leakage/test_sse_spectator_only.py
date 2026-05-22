from __future__ import annotations

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings


def test_spectator_api_and_sse_hide_private_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={
                "config_path": "configs/games/classic_8.yaml",
                "seed": "leakage-sse-seed",
                "agents": {str(seat): "llm:mock" for seat in range(1, 9)},
            },
        ).json()["game_id"]

        events = client.get(f"/games/{game_id}/events").json()
        event_types = {event["type"] for event in events}
        assert {
            "llm_call",
            "wolf_chat_message",
            "guard_protect",
            "seer_check_result",
        }.isdisjoint(event_types)

        with client.stream("GET", f"/games/{game_id}/stream") as response:
            body = response.read().decode("utf-8")

        assert "llm_call" not in body
        assert "wolf_chat_message" not in body
        assert "seer_check_result" not in body
        assert "guard_protect" not in body

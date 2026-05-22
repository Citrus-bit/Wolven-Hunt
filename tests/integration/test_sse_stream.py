from __future__ import annotations

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings


def test_sse_stream_replays_events_and_resume(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={"config_path": "configs/games/classic_8.yaml", "seed": "sse-seed"},
        ).json()["game_id"]

        with client.stream("GET", f"/games/{game_id}/stream") as response:
            body = response.read().decode("utf-8")

        assert response.status_code == 200
        assert "event: game_event" in body
        assert "id: 1" in body
        assert "event: heartbeat" in body

        with client.stream(
            "GET",
            f"/games/{game_id}/stream",
            headers={"Last-Event-ID": "5"},
        ) as resumed:
            resumed_body = resumed.read().decode("utf-8")

        assert resumed.status_code == 200
        assert "id: 5\n" not in resumed_body
        assert "id: 6\n" in resumed_body

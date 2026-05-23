from __future__ import annotations

from time import sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings

CONFIG_PATH = "configs/games/classic_10.yaml"
SEATS = range(1, 11)


def test_spectator_mvp_stream_narrative_and_reveal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_PACING_PROFILE", "off")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "spectator-mvp",
                "pacing": "off",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        unfinished = client.get(f"/games/{game_id}/reveal")
        assert unfinished.status_code == 404
        assert unfinished.json()["code"] == "game_not_finished"

        _wait_until_finished(client, game_id)

        events = client.get(f"/games/{game_id}/events").json()
        assert events[-1]["type"] == "role_reveal"

        narrative = client.get(f"/games/{game_id}/narrative").json()
        assert any(row["kind"] == "speech" for row in narrative)

        effects = client.get(f"/games/{game_id}/effects").json()
        assert any(effect["kind"] == "guard_shield" for effect in effects)
        assert client.get(f"/games/{game_id}/effects?after={effects[0]['seq']}").status_code == 200

        reveal = client.get(f"/games/{game_id}/reveal")
        assert reveal.status_code == 200
        assert len(reveal.json()["seats"]) == 10

        with client.stream("GET", f"/games/{game_id}/stream") as response:
            body = response.read().decode("utf-8")
        assert "event: game_event" in body
        assert "event: narrative_row" in body
        assert "event: spectator_effect" in body
        assert "role_reveal" in body


def _wait_until_finished(client: TestClient, game_id: str) -> None:
    for _ in range(150):
        summary = client.get(f"/games/{game_id}").json()
        if summary["status"] == "finished":
            return
        sleep(0.02)
    raise AssertionError("game did not finish")

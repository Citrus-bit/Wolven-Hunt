from __future__ import annotations

import asyncio
from time import sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings
from wolven_hunt.api.sse import sse_response

CONFIG_PATH = "configs/games/classic_10.yaml"


def test_sse_stream_replays_events_and_resume(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={"config_path": CONFIG_PATH, "seed": "sse-seed"},
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


def test_sse_paused_game_sends_stream_ready_without_cursor_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        game_id = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "sse-paused-ready",
                "start_paused": True,
            },
        ).json()["game_id"]

        session = get_registry().require(game_id)
        response = sse_response(session, last_event_id=None)
        first_frame = asyncio.run(response.body_iterator.__anext__())

        assert response.status_code == 200
        assert first_frame == "event: stream_ready\ndata: {}\n\n"
        assert "id:" not in first_frame


def test_sse_resume_replays_all_projection_types_for_same_raw_seq(monkeypatch, tmp_path) -> None:
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
                "seed": "sse-same-seq-projections",
                "agents": {str(seat): "llm:mock" for seat in range(1, 11)},
                "pacing": "off",
            },
        ).json()["game_id"]

        effect = _wait_for_non_death_effect(client, game_id)
        previous_seq = int(effect["seq"]) - 1

        with client.stream(
            "GET",
            f"/games/{game_id}/stream",
            headers={"Last-Event-ID": str(previous_seq)},
        ) as resumed:
            body = resumed.read().decode("utf-8")

        assert resumed.status_code == 200
        assert f"id: {effect['seq']}\n" in body
        assert "event: spectator_effect" in body
        assert str(effect["kind"]) in body


def _wait_for_non_death_effect(client: TestClient, game_id: str) -> dict[str, object]:
    for _ in range(100):
        for effect in client.get(f"/games/{game_id}/effects").json():
            if effect["kind"] != "death_reveal":
                return effect
        sleep(0.02)
    raise AssertionError("spectator effect was not published")

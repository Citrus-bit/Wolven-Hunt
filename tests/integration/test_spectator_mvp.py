from __future__ import annotations

from threading import Event as ThreadEvent, Thread
from time import monotonic, sleep

from fastapi.testclient import TestClient

from wolven_hunt.api.app import create_app
from wolven_hunt.api.deps import get_registry, get_settings
from wolven_hunt.core.events import EventType
from wolven_hunt.orchestration.pacing import spectator_effect_ack_event

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
        assert (
            client.get(f"/games/{game_id}/effects?after={effects[0]['seq']}").status_code
            == 200
        )

        reveal = client.get(f"/games/{game_id}/reveal")
        assert reveal.status_code == 200
        assert len(reveal.json()["seats"]) == 10

        with client.stream("GET", f"/games/{game_id}/stream") as response:
            body = response.read().decode("utf-8")
        assert "event: game_event" in body
        assert "event: narrative_row" in body
        assert "event: spectator_effect" in body
        assert "role_reveal" in body


def test_start_paused_game_waits_for_run_before_event_log_growth(
    monkeypatch, tmp_path
) -> None:
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
                "seed": "spectator-paused-start",
                "pacing": "off",
                "start_paused": True,
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]

        for _ in range(5):
            sleep(0.02)
            summary = client.get(f"/games/{game_id}").json()
            assert summary["status"] == "paused"
            assert summary["event_count"] == 0
            assert client.get(f"/games/{game_id}/events").json() == []

        run = client.post(f"/games/{game_id}/run")
        assert run.status_code == 200
        for _ in range(50):
            summary = client.get(f"/games/{game_id}").json()
            if summary["event_count"] > 0:
                break
            sleep(0.02)
        else:
            raise AssertionError("paused game did not start after /run")
        assert summary["status"] in {"running", "finished"}
        assert client.get(f"/games/{game_id}/events").json()[0]["type"] == "game_start"


def test_live_stream_waits_until_effect_projection_is_published(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_PACING_PROFILE", "live")
    monkeypatch.setenv("WH_PACING_PHASE_MS", "0")
    monkeypatch.setenv("WH_PACING_NIGHT_MS", "0")
    monkeypatch.setenv("WH_PACING_SPEECH_MS", "0")
    monkeypatch.setenv("WH_PACING_ACK_TIMEOUT_MS", "1000")
    get_settings.cache_clear()
    get_registry.cache_clear()
    started = ThreadEvent()
    release = ThreadEvent()

    import wolven_hunt.orchestration.runtime as runtime

    original_projector = runtime.event_to_spectator_effects

    def blocked_projector(event, events):
        if event.type is EventType.GUARD_PROTECT:
            started.set()
            release.wait(timeout=2)
        return original_projector(event, events)

    monkeypatch.setattr(runtime, "event_to_spectator_effects", blocked_projector)
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "spectator-projection-race",
                "pacing": "live",
                "start_paused": True,
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        client.post(f"/games/{game_id}/run")

        for _ in range(100):
            summary = client.get(f"/games/{game_id}").json()
            _ack_phase_audio(client, game_id, str(summary["phase"]))
            if started.is_set():
                break
            sleep(0.01)
        else:
            raise AssertionError("guard projection was not reached")

        registry = get_registry()
        session = registry.require(game_id)
        raw_types = [event.type for event in session.raw_events_after(0)]
        assert EventType.GUARD_PROTECT not in raw_types
        assert client.get(f"/games/{game_id}/effects").json() == []

        release.set()
        for _ in range(100):
            effects = client.get(f"/games/{game_id}/effects").json()
            if any(effect["kind"] == "guard_shield" for effect in effects):
                break
            sleep(0.01)
        else:
            raise AssertionError("guard effect was not published")

        raw_types = [event.type for event in session.raw_events_after(0)]
        assert EventType.GUARD_PROTECT in raw_types
        for effect in effects:
            if effect["kind"] != "death_reveal":
                client.post(
                    f"/games/{game_id}/ack",
                    json={
                        "phase": effect["phase"],
                        "event": spectator_effect_ack_event(int(effect["seq"])),
                    },
                )


def test_live_spectator_effects_gate_night_progression(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("WH_LLM_PROVIDER", "mock")
    monkeypatch.setenv("WH_PACING_PROFILE", "live")
    monkeypatch.setenv("WH_PACING_PHASE_MS", "0")
    monkeypatch.setenv("WH_PACING_NIGHT_MS", "0")
    monkeypatch.setenv("WH_PACING_SPEECH_MS", "0")
    monkeypatch.setenv("WH_PACING_ACK_TIMEOUT_MS", "1000")
    get_settings.cache_clear()
    get_registry.cache_clear()
    with TestClient(create_app()) as client:
        created = client.post(
            "/games",
            json={
                "config_path": CONFIG_PATH,
                "seed": "spectator-live-effects",
                "pacing": "live",
                "agents": {str(seat): "llm:mock" for seat in SEATS},
            },
        )
        assert created.status_code == 200
        game_id = created.json()["game_id"]
        expected = {"guard_shield", "wolf_attack", "seer_vision"}
        seen: dict[str, dict[str, object]] = {}
        acked_effects: set[int] = set()
        deadline = monotonic() + 8

        while expected - set(seen) and monotonic() < deadline:
            summary = client.get(f"/games/{game_id}").json()
            _ack_phase_audio(client, game_id, str(summary["phase"]))
            for effect in client.get(f"/games/{game_id}/effects").json():
                seq = int(effect["seq"])
                kind = str(effect["kind"])
                if kind in expected and kind not in seen:
                    gated_summary = client.get(f"/games/{game_id}").json()
                    assert gated_summary["phase"] == effect["phase"]
                    seen[kind] = effect
                if kind != "death_reveal" and seq not in acked_effects:
                    acked_effects.add(seq)
                    client.post(
                        f"/games/{game_id}/ack",
                        json={
                            "phase": effect["phase"],
                            "event": spectator_effect_ack_event(seq),
                        },
                    )
            sleep(0.01)

        assert expected <= set(seen)
        _drive_live_game_until_finished(client, game_id, acked_effects)


def _wait_until_finished(client: TestClient, game_id: str) -> None:
    for _ in range(150):
        summary = client.get(f"/games/{game_id}").json()
        if summary["status"] == "finished":
            return
        sleep(0.02)
    raise AssertionError("game did not finish")


def _drive_live_game_until_finished(
    client: TestClient,
    game_id: str,
    acked_effects: set[int],
) -> None:
    deadline = monotonic() + 8
    while monotonic() < deadline:
        summary = client.get(f"/games/{game_id}").json()
        if summary["status"] == "finished":
            return
        _ack_phase_audio(client, game_id, str(summary["phase"]))
        for effect in client.get(f"/games/{game_id}/effects").json():
            seq = int(effect["seq"])
            if effect["kind"] == "death_reveal" or seq in acked_effects:
                continue
            acked_effects.add(seq)
            client.post(
                f"/games/{game_id}/ack",
                json={
                    "phase": effect["phase"],
                    "event": spectator_effect_ack_event(seq),
                },
            )
        sleep(0.01)
    raise AssertionError("live game did not finish")


def _ack_phase_audio(client: TestClient, game_id: str, phase: str) -> None:
    ack_event = {
        "NIGHT_START": "night_intro_done",
        "NIGHT_WOLF_CHAT": "night_wolves_done",
        "NIGHT_WITCH": "night_witch_done",
        "NIGHT_SEER": "night_seer_done",
        "DAY_ANNOUNCE": "day_intro_done",
    }.get(phase)
    if ack_event is None:
        return
    client.post(f"/games/{game_id}/ack", json={"phase": phase, "event": ack_event})

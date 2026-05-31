from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from wolven_hunt.core.events import Event
from wolven_hunt.storage.jsonl import read_events_jsonl


def replay_deterministic(events: tuple[Event, ...]) -> tuple[Event, ...]:
    previous_seq = 0
    game_end_count = 0
    for event in events:
        if event.seq <= previous_seq:
            raise ValueError(f"event seq must be strictly increasing: {event.seq}")
        previous_seq = event.seq
        if event.type.value == "game_end":
            game_end_count += 1
    if game_end_count > 1:
        raise ValueError("event log contains more than one game_end")
    return events


@dataclass(frozen=True, slots=True)
class ResimulateDivergence(ValueError):
    seq: int
    field: str
    expected: object
    actual: object

    def __str__(self) -> str:
        return (
            f"resimulate divergence at seq={self.seq} field={self.field}: "
            f"expected={self.expected!r} actual={self.actual!r}"
        )


def replay_resimulate(
    events_path: str | Path,
    raw_responses_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> tuple[Event, ...]:
    events_path = Path(events_path)
    events = replay_deterministic(read_events_jsonl(events_path))
    manifest = _read_manifest(events_path)
    raw_path = (
        Path(raw_responses_path)
        if raw_responses_path is not None
        else events_path.with_name("raw_responses.jsonl")
    )
    raw_rows = _read_raw_response_rows(raw_path)
    _validate_raw_response_hashes(raw_rows)
    if not raw_rows:
        return events

    from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
    from wolven_hunt.agents.interface import PlayerInterface
    from wolven_hunt.agents.llm_agent import LLMAgent
    from wolven_hunt.config.loader import load_game_config
    from wolven_hunt.core.rng import DeterministicRNG
    from wolven_hunt.core.seat import Role, Seat
    from wolven_hunt.llm.gateway import LLMGateway
    from wolven_hunt.llm.prompts import PromptRenderer
    from wolven_hunt.llm.provider import ReplayLLMProvider
    from wolven_hunt.orchestration.fsm import run_game

    seed = str(events[0].payload["random_seed"])
    config_hash = str(events[0].payload["config_hash"])
    config = load_game_config(_resolve_config_path(config_path, manifest, events))
    if config.config_hash != config_hash:
        raise ResimulateDivergence(1, "config_hash", config_hash, config.config_hash)
    prompt_version = _prompt_version_from_manifest(manifest)

    llm_seats = {_int_value(row.get("seat")) for row in raw_rows if row.get("error") is None}
    provider = ReplayLLMProvider(raw_rows)
    gateway = LLMGateway(
        provider=provider,
        max_retries=config.rule_set.fallback.max_retries,
        phase_max_retries=config.rule_set.fallback.phase_max_retries,
        retry_backoff_delays_seconds=config.rule_set.fallback.retry_backoff_delays_seconds,
        sleep_fn=lambda _: None,
        prompt_version=prompt_version,
    )
    renderer = PromptRenderer(config.prompt_pack_root, version=prompt_version)
    rng = DeterministicRNG(seed)
    agents: dict[int, PlayerInterface] = {}
    for seat_number in range(config.seat_range.start, config.seat_range.end + 1):
        seat = Seat(seat_number)
        agents[seat_number] = (
            LLMAgent(seat=seat, gateway=gateway, prompt_renderer=renderer, rng=rng)
            if seat_number in llm_seats
            else DeterministicMockAgent(seat)
        )
    forced_seat_roles = _forced_seat_roles_from_manifest(manifest, Role)
    state, new_log = run_game(
        config=config,
        seed=seed,
        agents=agents,
        forced_seat_roles=forced_seat_roles,
    )
    if any(event.type.value == "role_reveal" for event in events):
        from wolven_hunt.referee.reveal import build_role_reveal

        reveal = build_role_reveal(state, new_log.events)
        if reveal is not None:
            new_log.append(reveal)
    actual = _strip_llm_calls(new_log.events)
    expected = _strip_llm_calls(events)
    _compare_event_sequence(expected, actual)
    return new_log.events


def canonical_payload(event: Event) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(json.dumps(event.payload, ensure_ascii=False, sort_keys=True)),
    )


def _compare_event_sequence(expected: tuple[Event, ...], actual: tuple[Event, ...]) -> None:
    if len(expected) != len(actual):
        raise ResimulateDivergence(0, "length", len(expected), len(actual))
    for expected_event, actual_event in zip(expected, actual, strict=True):
        for field in ("type", "actor", "day", "phase"):
            expected_value = getattr(expected_event, field)
            actual_value = getattr(actual_event, field)
            if expected_value != actual_value:
                raise ResimulateDivergence(expected_event.seq, field, expected_value, actual_value)
        expected_payload = canonical_payload(expected_event)
        actual_payload = canonical_payload(actual_event)
        if expected_payload != actual_payload:
            raise ResimulateDivergence(
                expected_event.seq,
                "canonical_payload",
                expected_payload,
                actual_payload,
            )


def _read_raw_response_rows(path: Path) -> tuple[dict[str, object], ...]:
    if not path.exists():
        return ()
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(cast(dict[str, object], json.loads(line)))
    return tuple(rows)


def _read_manifest(events_path: Path) -> dict[str, object]:
    manifest_path = events_path.with_name("manifest.json")
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(manifest, dict):
        return {}
    return cast(dict[str, object], manifest)


def _resolve_config_path(
    config_path: str | Path | None,
    manifest: dict[str, object],
    events: tuple[Event, ...],
) -> Path:
    if config_path is not None:
        return Path(config_path)
    value = manifest.get("config_path")
    if isinstance(value, str) and value:
        return Path(value)
    game_start = events[0] if events else None
    payload = {} if game_start is None else game_start.payload
    seat_range = payload.get("seat_range")
    if isinstance(seat_range, dict):
        start = _optional_int_value(seat_range.get("start"))
        end = _optional_int_value(seat_range.get("end"))
        if start == 1 and end == 8:
            return Path("configs/games/classic_8.yaml")
    raise ValueError(
        "manifest.json with config_path is required for resimulating non-legacy runs"
    )


def _prompt_version_from_manifest(manifest: dict[str, object]) -> str:
    value = manifest.get("prompt_pack_version")
    if isinstance(value, str) and value:
        return value
    return "v5"


def _forced_seat_roles_from_manifest(
    manifest: dict[str, object],
    role_type: type[Any],
) -> dict[int, Any]:
    raw = manifest.get("forced_seat_roles")
    if not isinstance(raw, dict):
        return {}
    forced: dict[int, Any] = {}
    for seat_key, role_value in raw.items():
        if not isinstance(role_value, str):
            continue
        seat = _optional_int_value(seat_key)
        if seat is None:
            continue
        forced[seat] = role_type(role_value)
    return forced


def _optional_int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _validate_raw_response_hashes(rows: tuple[dict[str, object], ...]) -> None:
    for line_number, row in enumerate(rows, start=1):
        raw_response = str(row.get("raw_response", ""))
        expected_hash = str(row.get("raw_response_hash", ""))
        actual_hash = hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
        if expected_hash and expected_hash != actual_hash:
            raise ResimulateDivergence(
                _int_value(row.get("seq") or row.get("event_seq") or line_number),
                "raw_response_hash",
                expected_hash,
                actual_hash,
            )


def _strip_llm_calls(events: tuple[Event, ...]) -> tuple[Event, ...]:
    return tuple(event for event in events if event.type.value != "llm_call")


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"expected int-like value, got {value!r}")

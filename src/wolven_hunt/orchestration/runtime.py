from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import cast

from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
from wolven_hunt.agents.interface import PlayerInterface
from wolven_hunt.agents.llm_agent import LLMAgent
from wolven_hunt.config.loader import load_game_config
from wolven_hunt.config.schema import GameConfig
from wolven_hunt.config.settings import Settings
from wolven_hunt.core.actions import (
    GuardProtect,
    LastWords,
    PkVote,
    SeerCheck,
    Speech,
    Vote,
    WitchAction,
    WolfChatMessage,
    WolfKillVote,
)
from wolven_hunt.core.events import Event
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.llm.cost import CostTracker
from wolven_hunt.llm.gateway import LLMGateway
from wolven_hunt.llm.prompts import PromptRenderer
from wolven_hunt.llm.provider import build_provider_from_config
from wolven_hunt.llm.provider_map import (
    ProviderConfig,
    load_provider_map,
    merge_provider_config,
)
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.orchestration.pacing import PacingController, PacingName, profile_from_settings
from wolven_hunt.referee.reveal import build_role_reveal
from wolven_hunt.referee.text_validate import validate_text_consistency
from wolven_hunt.referee.validate import Reject, validate_action
from wolven_hunt.referee.view import PlayerView, build_view
from wolven_hunt.storage.disk import GameRunStore
from wolven_hunt.storage.event_log import EventLog
from wolven_hunt.storage.narrative import event_to_narrative
from wolven_hunt.storage.spectator_effects import event_to_spectator_effects

MANUAL_ACTION_WAIT_SECONDS = 0.05


TextAction = Speech | WolfChatMessage
AgentSpecValue = object
SeatPresentationValue = Mapping[int, Mapping[str, str]]


class RuntimeControl:
    def __init__(self) -> None:
        self._resume = threading.Event()
        self._resume.set()

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def wait_if_paused(self, state: GameState) -> None:
        del state
        self._resume.wait()


class PendingTextActions:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._actions: dict[tuple[str, int], deque[TextAction]] = {}

    def submit(self, kind: str, action: TextAction) -> None:
        with self._condition:
            self._actions.setdefault((kind, action.actor.number), deque()).append(action)
            self._condition.notify_all()

    def pop(self, kind: str, seat: Seat, *, timeout_seconds: float) -> TextAction | None:
        deadline = monotonic() + timeout_seconds
        key = (kind, seat.number)
        with self._condition:
            while True:
                queue = self._actions.get(key)
                if queue:
                    return queue.popleft()
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)


class PendingActionAgent:
    def __init__(
        self,
        *,
        seat: Seat,
        base: PlayerInterface,
        pending: PendingTextActions,
        timeout_seconds: float = MANUAL_ACTION_WAIT_SECONDS,
    ) -> None:
        self._seat = seat
        self._base = base
        self._pending = pending
        self._timeout_seconds = timeout_seconds

    def decide_guard(self, view: PlayerView) -> GuardProtect:
        return self._base.decide_guard(view)

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        action = self._pending.pop(
            "wolf_chat",
            self._seat,
            timeout_seconds=self._timeout_seconds,
        )
        if isinstance(action, WolfChatMessage):
            return action
        return self._base.decide_wolf_chat(view)

    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote:
        return self._base.decide_wolf_vote(view)

    def decide_seer(self, view: PlayerView) -> SeerCheck:
        return self._base.decide_seer(view)

    def decide_speech(self, view: PlayerView) -> Speech:
        action = self._pending.pop(
            "speech",
            self._seat,
            timeout_seconds=self._timeout_seconds,
        )
        if isinstance(action, Speech):
            return action
        return self._base.decide_speech(view)

    def decide_witch(self, view: PlayerView) -> WitchAction:
        return self._base.decide_witch(view)

    def decide_vote(self, view: PlayerView) -> Vote:
        return self._base.decide_vote(view)

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        return self._base.decide_pk_vote(view)

    def decide_last_words(self, view: PlayerView) -> LastWords:
        return self._base.decide_last_words(view)

    def consume_last_call_result(self) -> object | None:
        consume = getattr(self._base, "consume_last_call_result", None)
        if not callable(consume):
            return None
        result = consume()
        if result is None:
            return None
        return cast(object, result)

    def set_retry_feedback(self, error_type: str, message: str) -> None:
        setter = getattr(self._base, "set_retry_feedback", None)
        if callable(setter):
            setter(error_type, message)


@dataclass(slots=True)
class GameSession:
    game_id: str
    config: GameConfig
    seed: str
    store: GameRunStore
    state: GameState
    event_log: EventLog
    status: str
    loop: asyncio.AbstractEventLoop
    condition: asyncio.Condition
    control: RuntimeControl
    pending: PendingTextActions
    pacing: PacingController
    started_at: str
    seat_presentation: dict[int, dict[str, str]]
    task: asyncio.Task[None] | None = None
    error: str | None = None
    final_reveal: dict[str, object] | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _narrative_rows: list[dict[str, object]] = field(default_factory=list)
    _effect_rows: list[dict[str, object]] = field(default_factory=list)
    _wake_tasks: set[asyncio.Task[None]] = field(default_factory=set)

    def set_state(self, state: GameState) -> None:
        with self._lock:
            self.state = state
        self.notify_event_loop()

    def set_status(self, status: str) -> None:
        with self._lock:
            self.status = status
        self.notify_event_loop()

    def publish_event(self, event: Event) -> None:
        self.store.append_event(event)
        row = event_to_narrative(event)
        if row is not None:
            row_dict = row.to_dict()
            with self._lock:
                self._narrative_rows.append(row_dict)
            self.store.append_narrative(row_dict)
        effects = event_to_spectator_effects(event, self.event_log.events)
        if effects:
            with self._lock:
                self._effect_rows.extend(effect.to_dict() for effect in effects)
        self.notify_event_loop()
        self.pacing.on_event(event)

    def ack(self, *, phase: str, event: str, client_event_id: str = "") -> None:
        self.pacing.ack(phase=phase, event=event, client_event_id=client_event_id)

    def notify_event_loop(self) -> None:
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self._wake_streams)

    def _wake_streams(self) -> None:
        async def notify() -> None:
            async with self.condition:
                self.condition.notify_all()

        task = asyncio.create_task(notify())
        self._wake_tasks.add(task)
        task.add_done_callback(self._wake_tasks.discard)

    async def wait_for_event(self, *, timeout_seconds: float) -> None:
        async with self.condition:
            await asyncio.wait_for(self.condition.wait(), timeout=timeout_seconds)

    def spectator_events(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            state = self.state
            events = self.event_log.events
        view = build_view(
            state,
            events,
            rule_set=self.config.rule_set,
            seat=None,
        )
        return tuple(event.model_dump(mode="json") for event in view.visible_events)

    def spectator_events_after(self, seq: int) -> tuple[dict[str, object], ...]:
        return tuple(event for event in self.spectator_events() if _event_seq(event) > seq)

    def raw_events_after(self, seq: int) -> tuple[Event, ...]:
        with self._lock:
            return tuple(event for event in self.event_log.events if event.seq > seq)

    def spectator_event_for_seq(self, seq: int) -> dict[str, object] | None:
        for event in self.spectator_events_after(seq - 1):
            if _event_seq(event) == seq:
                return event
        return None

    def narrative_rows(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return tuple(self._narrative_rows)

    def narrative_rows_after(self, seq: int) -> tuple[dict[str, object], ...]:
        return tuple(row for row in self.narrative_rows() if _row_seq(row) > seq)

    def effect_rows(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return tuple(self._effect_rows)

    def effect_rows_after(self, seq: int) -> tuple[dict[str, object], ...]:
        return tuple(row for row in self.effect_rows() if _row_seq(row) > seq)

    def effect_rows_for_seq(self, seq: int) -> tuple[dict[str, object], ...]:
        return tuple(row for row in self.effect_rows() if _row_seq(row) == seq)

    def latest_event_seq(self) -> int:
        events = self.event_log.events
        return 0 if not events else events[-1].seq

    def is_terminal(self) -> bool:
        return self.status in {"finished", "failed"}


class GameRegistry:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self._sessions: dict[str, GameSession] = {}
        self._lock = threading.RLock()

    async def create_game(
        self,
        *,
        config_path: Path,
        seed: str,
        agent_specs: Mapping[int, AgentSpecValue],
        pacing: PacingName | None = None,
        seat_presentation: SeatPresentationValue | None = None,
    ) -> GameSession:
        config = load_game_config(config_path)
        initial_state, _ = build_initial_state(config, seed)
        game_id = str(initial_state.game_id)
        store = GameRunStore(runs_dir=self.settings.runs_dir, game_id=game_id)
        started_at = _now()
        normalized_presentation = _normalize_seat_presentation(seat_presentation)
        store.write_manifest(
            _manifest_payload(
                config_hash=config.config_hash,
                config_path=str(config.path),
                seed=seed,
                started_at=started_at,
                ended_at=None,
                winner=None,
                seat_presentation=normalized_presentation,
            )
        )
        session_ref: dict[str, GameSession] = {}

        def on_append(event: Event) -> None:
            session_ref["session"].publish_event(event)

        session = GameSession(
            game_id=game_id,
            config=config,
            seed=seed,
            store=store,
            state=initial_state,
            event_log=EventLog(seed=seed, on_append=on_append),
            status="starting",
            loop=asyncio.get_running_loop(),
            condition=asyncio.Condition(),
            control=RuntimeControl(),
            pending=PendingTextActions(),
            pacing=PacingController(profile_from_settings(self.settings, override=pacing)),
            started_at=started_at,
            seat_presentation=normalized_presentation,
        )
        session_ref["session"] = session
        agents = self._build_agents(
            config=config,
            seed=seed,
            specs=agent_specs,
            store=store,
            pending=session.pending,
        )
        with self._lock:
            self._sessions[game_id] = session
        session.task = asyncio.create_task(self._run_game_task(session, agents))
        return session

    def get(self, game_id: str) -> GameSession | None:
        with self._lock:
            return self._sessions.get(game_id)

    def require(self, game_id: str) -> GameSession:
        session = self.get(game_id)
        if session is None:
            raise KeyError(game_id)
        return session

    def game_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._sessions)

    def sessions(self) -> tuple[GameSession, ...]:
        with self._lock:
            return tuple(self._sessions.values())

    def run(self, game_id: str) -> GameSession:
        session = self.require(game_id)
        if session.status == "paused":
            session.control.resume()
            session.set_status("running")
        return session

    def pause(self, game_id: str) -> GameSession:
        session = self.require(game_id)
        if not session.is_terminal():
            session.control.pause()
            session.set_status("paused")
        return session

    def resume(self, game_id: str) -> GameSession:
        session = self.require(game_id)
        if session.status == "paused":
            session.control.resume()
            session.set_status("running")
        return session

    def submit_speech(self, *, game_id: str, seat: Seat, text: str) -> Reject | None:
        session = self.require(game_id)
        if session.is_terminal():
            return Reject("game.finished", "game has already finished")
        action = Speech(actor=seat, text=text)
        rejection = validate_action(session.state, action, session.config.rule_set)
        if rejection is None:
            rejection = validate_text_consistency(
                session.state,
                action,
                session.config.rule_set,
                session.event_log.events,
            )
        if rejection is not None:
            return rejection
        session.pending.submit("speech", action)
        return None

    def submit_wolf_chat(self, *, game_id: str, seat: Seat, text: str) -> Reject | None:
        session = self.require(game_id)
        if session.is_terminal():
            return Reject("game.finished", "game has already finished")
        action = WolfChatMessage(actor=seat, text=text)
        rejection = validate_action(session.state, action, session.config.rule_set)
        if rejection is None:
            rejection = validate_text_consistency(
                session.state,
                action,
                session.config.rule_set,
                session.event_log.events,
            )
        if rejection is not None:
            return rejection
        session.pending.submit("wolf_chat", action)
        return None

    async def _run_game_task(
        self, session: GameSession, agents: dict[int, PlayerInterface]
    ) -> None:
        await asyncio.sleep(0.05)
        await asyncio.to_thread(self._run_game, session, agents)

    def _run_game(self, session: GameSession, agents: dict[int, PlayerInterface]) -> None:
        try:
            if not session.control.paused:
                session.set_status("running")
            state, _ = run_game(
                config=session.config,
                seed=session.seed,
                agents=agents,
                event_log=session.event_log,
                state_sink=session.set_state,
                control_hook=session.control.wait_if_paused,
            )
            session.set_state(state)
            if state.winner is not None and not _has_role_reveal(session.event_log.events):
                reveal = build_role_reveal(state, session.event_log.events)
                if reveal is not None:
                    stamped_reveal = session.event_log.append(reveal)
                    session.final_reveal = dict(stamped_reveal.payload)
                    session.store.write_final_reveal(dict(stamped_reveal.payload))
            session.store.write_manifest(
                _manifest_payload(
                    config_hash=session.config.config_hash,
                    config_path=str(session.config.path),
                    seed=session.seed,
                    started_at=session.started_at,
                    ended_at=_now(),
                    winner=None if state.winner is None else state.winner.value,
                    seat_presentation=session.seat_presentation,
                )
            )
            session.set_status("finished")
        except Exception as exc:  # pragma: no cover - preserved in session for API debugging.
            session.error = str(exc)
            session.set_status("failed")
        finally:
            session.notify_event_loop()

    def _build_agents(
        self,
        *,
        config: GameConfig,
        seed: str,
        specs: Mapping[int, AgentSpecValue],
        store: GameRunStore,
        pending: PendingTextActions,
    ) -> dict[int, PlayerInterface]:
        agents: dict[int, PlayerInterface] = {}
        provider_map = load_provider_map(self.settings)
        cost_tracker = CostTracker(budget_tokens=self.settings.llm_budget_per_game)
        renderer = PromptRenderer(config.prompt_pack_root, version="v3")
        llm_rng = DeterministicRNG(seed)
        use_default_provider = bool(specs) or bool(self.settings.llm_provider_map)
        for seat_number in range(config.seat_range.start, config.seat_range.end + 1):
            seat = Seat(seat_number)
            spec = specs.get(seat_number)
            provider_config = _provider_config_for_spec(
                spec,
                fallback=provider_map.for_seat(seat),
                default_to_provider=use_default_provider,
            )
            if provider_config is not None:
                gateway = LLMGateway(
                    provider=build_provider_from_config(
                        provider_config,
                        phase_timeout_seconds=config.rule_set.fallback.phase_timeout_seconds,
                    ),
                    max_retries=config.rule_set.fallback.max_retries,
                    phase_max_retries=config.rule_set.fallback.phase_max_retries,
                    retry_backoff_base_seconds=(
                        config.rule_set.fallback.retry_backoff_base_seconds
                    ),
                    retry_backoff_multiplier=config.rule_set.fallback.retry_backoff_multiplier,
                    retry_backoff_max_seconds=(
                        config.rule_set.fallback.retry_backoff_max_seconds
                    ),
                    retry_backoff_jitter=config.rule_set.fallback.retry_backoff_jitter,
                    cost_tracker=cost_tracker,
                    prompt_version="v3",
                    raw_response_sink=lambda row: _write_llm_rows(store, row),
                )
                base: PlayerInterface = LLMAgent(
                    seat=seat,
                    gateway=gateway,
                    prompt_renderer=renderer,
                    rng=llm_rng,
                )
            else:
                base = DeterministicMockAgent(seat)
            agents[seat_number] = PendingActionAgent(
                seat=seat,
                base=base,
                pending=pending,
            )
        return agents


def _provider_config_for_spec(
    spec: AgentSpecValue | None,
    *,
    fallback: ProviderConfig,
    default_to_provider: bool,
) -> ProviderConfig | None:
    if spec is None:
        return fallback if default_to_provider else None
    if isinstance(spec, str):
        if spec.startswith("llm"):
            if spec == "llm:mock":
                return ProviderConfig(provider="mock", model=fallback.model)
            return fallback
        return None
    data = _mapping_from_spec(spec)
    kind = str(data.get("kind", "mock"))
    if kind == "mock":
        return None
    if kind != "llm":
        raise ValueError(f"unsupported agent kind: {kind}")
    return merge_provider_config(fallback, data)


def _mapping_from_spec(spec: object) -> Mapping[str, object]:
    if isinstance(spec, Mapping):
        return cast(Mapping[str, object], spec)
    model_dump = getattr(spec, "model_dump", None)
    if callable(model_dump):
        return cast(Mapping[str, object], model_dump())
    raise ValueError(f"unsupported agent spec: {spec!r}")


def _write_llm_rows(store: GameRunStore, row: dict[str, object]) -> None:
    store.append_raw_response(row)
    store.append_cost(
        {
            "storage_ref": row["storage_ref"],
            "model": row["model"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "cost_usd": row["cost_usd"],
        }
    )


def _event_seq(event: dict[str, object]) -> int:
    seq = event.get("seq")
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str):
        return int(seq)
    return 0


def _row_seq(row: dict[str, object]) -> int:
    seq = row.get("seq")
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str):
        return int(seq)
    return 0


def _has_role_reveal(events: tuple[Event, ...]) -> bool:
    return any(event.type.value == "role_reveal" for event in events)


def _normalize_seat_presentation(
    seat_presentation: SeatPresentationValue | None,
) -> dict[int, dict[str, str]]:
    if not seat_presentation:
        return {}
    normalized: dict[int, dict[str, str]] = {}
    for seat, presentation in seat_presentation.items():
        normalized[int(seat)] = {
            "nickname": str(presentation.get("nickname", "")),
            "icon_path": str(presentation.get("icon_path", "")),
        }
    return normalized


def _manifest_payload(
    *,
    config_hash: str,
    config_path: str,
    seed: str,
    started_at: str,
    ended_at: str | None,
    winner: str | None,
    seat_presentation: dict[int, dict[str, str]],
) -> dict[str, object]:
    return {
        "config_hash": config_hash,
        "config_path": config_path,
        "seed": seed,
        "prompt_pack_version": "v3",
        "started_at": started_at,
        "ended_at": ended_at,
        "winner": winner,
        "seat_presentation": seat_presentation,
    }


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()

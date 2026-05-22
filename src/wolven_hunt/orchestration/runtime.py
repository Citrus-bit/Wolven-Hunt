from __future__ import annotations

import asyncio
import threading
from collections import deque
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
    KnightChallenge,
    LastWords,
    PkVote,
    SeerCheck,
    Speech,
    Vote,
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
from wolven_hunt.llm.provider import LiteLLMProvider, MockLLMProvider
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.referee.validate import Reject, validate_action
from wolven_hunt.referee.view import PlayerView, build_view
from wolven_hunt.storage.disk import GameRunStore
from wolven_hunt.storage.event_log import EventLog

MANUAL_ACTION_WAIT_SECONDS = 0.05


TextAction = Speech | WolfChatMessage


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

    def decide_knight_challenge(self, view: PlayerView) -> KnightChallenge:
        return self._base.decide_knight_challenge(view)

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
    started_at: str
    task: asyncio.Task[None] | None = None
    error: str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
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
        self.notify_event_loop()

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
        agent_specs: dict[int, str],
    ) -> GameSession:
        config = load_game_config(config_path)
        initial_state, _ = build_initial_state(config, seed)
        game_id = str(initial_state.game_id)
        store = GameRunStore(runs_dir=self.settings.runs_dir, game_id=game_id)
        started_at = _now()
        store.write_manifest(
            {
                "config_hash": config.config_hash,
                "seed": seed,
                "prompt_pack_version": "v1",
                "started_at": started_at,
                "ended_at": None,
                "winner": None,
            }
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
            started_at=started_at,
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
            session.store.write_manifest(
                {
                    "config_hash": session.config.config_hash,
                    "seed": session.seed,
                    "prompt_pack_version": "v1",
                    "started_at": session.started_at,
                    "ended_at": _now(),
                    "winner": None if state.winner is None else state.winner.value,
                }
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
        specs: dict[int, str],
        store: GameRunStore,
        pending: PendingTextActions,
    ) -> dict[int, PlayerInterface]:
        agents: dict[int, PlayerInterface] = {}
        provider = (
            LiteLLMProvider(
                model=self.settings.llm_model,
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )
            if self.settings.llm_provider == "litellm"
            else MockLLMProvider(model=self.settings.llm_model)
        )
        gateway = LLMGateway(
            provider=provider,
            max_retries=self.settings.llm_max_retries,
            cost_tracker=CostTracker(budget_tokens=self.settings.llm_budget_per_game),
            raw_response_sink=lambda row: _write_llm_rows(store, row),
        )
        renderer = PromptRenderer(config.prompt_pack_root, version="v1")
        llm_rng = DeterministicRNG(seed)
        for seat_number in range(config.seat_range.start, config.seat_range.end + 1):
            seat = Seat(seat_number)
            spec = specs.get(seat_number, "mock")
            if spec.startswith("llm:"):
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


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()

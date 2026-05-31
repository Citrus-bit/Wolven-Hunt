from __future__ import annotations

import asyncio
import secrets
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import cast

from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
from wolven_hunt.agents.human_input import HumanInputAgent
from wolven_hunt.agents.interface import PlayerInterface
from wolven_hunt.agents.llm_agent import LLMAgent
from wolven_hunt.config.loader import ensure_prompt_version, load_game_config
from wolven_hunt.config.schema import GameConfig
from wolven_hunt.config.settings import Settings
from wolven_hunt.core.actions import (
    Action,
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
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.evolution.engine import maybe_step_after_game
from wolven_hunt.evolution.state import active_prompt_version
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


class PendingActions:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._actions: dict[tuple[str, int], deque[Action]] = {}

    def submit(self, kind: str, action: Action) -> None:
        with self._condition:
            self._actions.setdefault((kind, action.actor.number), deque()).append(action)
            self._condition.notify_all()

    def pop(self, kind: str, seat: Seat, *, timeout_seconds: float) -> Action | None:
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
        pending: PendingActions,
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


@dataclass(frozen=True, slots=True)
class TurnRequest:
    seat: int
    kind: str
    deadline_ts: float
    timeout_seconds: float
    valid_targets: tuple[int, ...] | None
    constraints: dict[str, object]
    phase: str
    day: int

    def to_dict(self) -> dict[str, object]:
        return {
            "seat": self.seat,
            "kind": self.kind,
            "deadline_ts": self.deadline_ts,
            "timeout_seconds": self.timeout_seconds,
            "valid_targets": None
            if self.valid_targets is None
            else list(self.valid_targets),
            "constraints": self.constraints,
            "phase": self.phase,
            "day": self.day,
        }


class SessionTurnHooks:
    def __init__(self, session: GameSession) -> None:
        self._session = session

    def set_turn_request(
        self,
        *,
        seat: Seat,
        kind: str,
        deadline_ts: float,
        timeout_seconds: float,
        valid_targets: tuple[int, ...] | None,
        constraints: dict[str, object],
        phase: str,
        day: int,
    ) -> None:
        self._session.set_turn_request(
            TurnRequest(
                seat=seat.number,
                kind=kind,
                deadline_ts=deadline_ts,
                timeout_seconds=timeout_seconds,
                valid_targets=valid_targets,
                constraints=constraints,
                phase=phase,
                day=day,
            )
        )

    def clear_turn_request(self, *, seat: Seat, kind: str) -> None:
        self._session.clear_turn_request(seat=seat, kind=kind)


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
    pending: PendingActions
    pacing: PacingController
    started_at: str
    seat_presentation: dict[int, dict[str, str]]
    agents: dict[int, PlayerInterface]
    prompt_version: str
    evolution_enabled: bool
    human_seat: int | None = None
    player_tokens: dict[int, str] = field(default_factory=dict)
    seat_agent_kinds: dict[int, str] = field(default_factory=dict)
    forced_seat_roles: dict[int, Role] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    error: str | None = None
    final_reveal: dict[str, object] | None = None
    turn_request: TurnRequest | None = None
    turn_cleared: dict[str, object] | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _stream_events: list[Event] = field(default_factory=list)
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
        effects = event_to_spectator_effects(event, self.event_log.events)
        row_dict: dict[str, object] | None = None
        if row is not None:
            row_dict = row.to_dict()
            self.store.append_narrative(row_dict)
        with self._lock:
            if row_dict is not None:
                self._narrative_rows.append(row_dict)
            if effects:
                self._effect_rows.extend(effect.to_dict() for effect in effects)
            self._stream_events.append(event)
        self.notify_event_loop()
        self.pacing.on_event(event)

    def ack(self, *, phase: str, event: str, client_event_id: str = "") -> None:
        self.pacing.ack(phase=phase, event=event, client_event_id=client_event_id)

    def set_turn_request(self, turn_request: TurnRequest) -> None:
        with self._lock:
            self.turn_request = turn_request
            self.turn_cleared = None
        self.notify_event_loop()

    def clear_turn_request(self, *, seat: Seat, kind: str) -> None:
        with self._lock:
            if (
                self.turn_request is None
                or self.turn_request.seat != seat.number
                or self.turn_request.kind != kind
            ):
                return
            self.turn_request = None
            self.turn_cleared = {"seat": seat.number}
        self.notify_event_loop()

    def active_turn(self) -> TurnRequest | None:
        with self._lock:
            return self.turn_request

    def consume_turn_cleared(self, *, seat: Seat) -> dict[str, object] | None:
        with self._lock:
            if self.turn_cleared is None or self.turn_cleared.get("seat") != seat.number:
                return None
            return dict(self.turn_cleared)

    def validate_player_token(self, *, seat: Seat, token: str) -> bool:
        expected = self.player_tokens.get(seat.number)
        if expected is None:
            return False
        return secrets.compare_digest(expected, token)

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

    def player_events_after(self, seq: int, *, seat: Seat) -> tuple[dict[str, object], ...]:
        with self._lock:
            state = self.state
            events = self.event_log.events
        view = build_view(
            state,
            events,
            rule_set=self.config.rule_set,
            seat=seat,
        )
        return tuple(
            event.model_dump(mode="json")
            for event in view.visible_events
            if event.seq > seq
        )

    def player_event_for_seq(self, seq: int, *, seat: Seat) -> dict[str, object] | None:
        for event in self.player_events_after(seq - 1, seat=seat):
            if _event_seq(event) == seq:
                return event
        return None

    def raw_events_after(self, seq: int) -> tuple[Event, ...]:
        with self._lock:
            return tuple(event for event in self._stream_events if event.seq > seq)

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
        start_paused: bool = False,
        seat_presentation: SeatPresentationValue | None = None,
        evolution_enabled: bool | None = None,
        human_seat: int | None = None,
        human_seat_random: bool = False,
        human_role: Role | None = None,
    ) -> GameSession:
        config = load_game_config(config_path)
        selected_human_seat = _select_human_seat(
            config=config,
            seed=seed,
            human_seat=human_seat,
            human_seat_random=human_seat_random,
        )
        forced_seat_roles = (
            {selected_human_seat: human_role}
            if selected_human_seat is not None and human_role is not None
            else {}
        )
        game_evolution_enabled = (
            self.settings.evolution_enabled
            if evolution_enabled is None
            else evolution_enabled
        )
        prompt_version = active_prompt_version(
            self.settings.runs_dir,
            enabled=game_evolution_enabled,
        )
        ensure_prompt_version(config.prompt_pack_root, prompt_version)
        initial_state, _ = build_initial_state(
            config,
            seed,
            forced_seat_roles=forced_seat_roles,
        )
        game_id = str(initial_state.game_id)
        store = GameRunStore(runs_dir=self.settings.runs_dir, game_id=game_id)
        started_at = _now()
        normalized_presentation = _normalize_seat_presentation(seat_presentation)
        if selected_human_seat is not None and selected_human_seat not in normalized_presentation:
            normalized_presentation[selected_human_seat] = {
                "nickname": "你自己",
                "icon_path": "/assets/lobby/human_player.png",
            }
        player_tokens = (
            {selected_human_seat: secrets.token_urlsafe(32)}
            if selected_human_seat is not None
            else {}
        )
        seat_agent_kinds = _seat_agent_kinds(
            config=config,
            specs=agent_specs,
            human_seat=selected_human_seat,
            default_to_provider=bool(agent_specs) or bool(self.settings.llm_provider_map),
        )
        store.write_manifest(
            _manifest_payload(
                config_hash=config.config_hash,
                config_path=str(config.path),
                seed=seed,
                started_at=started_at,
                ended_at=None,
                winner=None,
                seat_presentation=normalized_presentation,
                prompt_version=prompt_version,
                human_seat=selected_human_seat,
                seat_agent_kinds=seat_agent_kinds,
                forced_seat_roles=forced_seat_roles,
            )
        )
        session_ref: dict[str, GameSession] = {}

        def on_append(event: Event) -> None:
            session_ref["session"].publish_event(event)

        pending = PendingActions()
        agents = self._build_agents(
            config=config,
            seed=seed,
            specs=agent_specs,
            store=store,
            pending=pending,
            prompt_version=prompt_version,
            human_seat=selected_human_seat,
        )
        session = GameSession(
            game_id=game_id,
            config=config,
            seed=seed,
            store=store,
            state=initial_state,
            event_log=EventLog(seed=seed, on_append=on_append),
            status="paused" if start_paused else "starting",
            loop=asyncio.get_running_loop(),
            condition=asyncio.Condition(),
            control=RuntimeControl(),
            pending=pending,
            pacing=PacingController(profile_from_settings(self.settings, override=pacing)),
            started_at=started_at,
            seat_presentation=normalized_presentation,
            agents=agents,
            prompt_version=prompt_version,
            evolution_enabled=game_evolution_enabled,
            human_seat=selected_human_seat,
            player_tokens=player_tokens,
            seat_agent_kinds=seat_agent_kinds,
            forced_seat_roles=forced_seat_roles,
        )
        if selected_human_seat is not None:
            agents[selected_human_seat] = HumanInputAgent(
                seat=Seat(selected_human_seat),
                base=agents[selected_human_seat],
                pending=pending,
                session_hooks=SessionTurnHooks(session),
                timeout_seconds=self.settings.human_turn_timeout_seconds,
            )
            session.agents = agents
        session_ref["session"] = session
        with self._lock:
            self._sessions[game_id] = session
        if not start_paused:
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
        if session.task is None and not session.is_terminal():
            session.loop.call_soon_threadsafe(self._start_session_task, session)
        if session.status == "paused":
            session.control.resume()
            session.set_status("running")
        return session

    def _start_session_task(self, session: GameSession) -> None:
        if session.task is None and not session.is_terminal():
            session.task = session.loop.create_task(
                self._run_game_task(session, session.agents)
            )

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

    def submit_action(
        self,
        *,
        game_id: str,
        seat: Seat,
        kind: str,
        action: Action,
    ) -> Reject | None:
        session = self.require(game_id)
        if session.is_terminal():
            return Reject("game.finished", "game has already finished")
        turn = session.active_turn()
        if turn is None:
            return Reject("turn.missing", "no active human turn")
        if turn.seat != seat.number or turn.kind != kind:
            return Reject("turn.mismatch", "action does not match active human turn")
        if action.actor != seat:
            return Reject("turn.actor", "action actor must match authenticated seat")
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
        session.pending.submit(kind, action)
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
                forced_seat_roles=session.forced_seat_roles,
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
                    prompt_version=session.prompt_version,
                    human_seat=session.human_seat,
                    seat_agent_kinds=session.seat_agent_kinds,
                    forced_seat_roles=session.forced_seat_roles,
                )
            )
            maybe_step_after_game(
                config_path=session.config.path,
                settings=self.settings.model_copy(
                    update={"evolution_enabled": session.evolution_enabled}
                ),
                game_id=session.game_id,
                prompt_version=session.prompt_version,
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
        pending: PendingActions,
        prompt_version: str,
        human_seat: int | None = None,
    ) -> dict[int, PlayerInterface]:
        agents: dict[int, PlayerInterface] = {}
        provider_map = load_provider_map(self.settings)
        cost_tracker = CostTracker(budget_tokens=self.settings.llm_budget_per_game)
        renderer = PromptRenderer(config.prompt_pack_root, version=prompt_version)
        llm_rng = DeterministicRNG(seed)
        use_default_provider = bool(specs) or bool(self.settings.llm_provider_map)
        _ = human_seat
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
                    retry_backoff_delays_seconds=(
                        config.rule_set.fallback.retry_backoff_delays_seconds
                    ),
                    retry_backoff_base_seconds=(
                        config.rule_set.fallback.retry_backoff_base_seconds
                    ),
                    retry_backoff_multiplier=config.rule_set.fallback.retry_backoff_multiplier,
                    retry_backoff_max_seconds=(
                        config.rule_set.fallback.retry_backoff_max_seconds
                    ),
                    retry_backoff_jitter=config.rule_set.fallback.retry_backoff_jitter,
                    cost_tracker=cost_tracker,
                    prompt_version=prompt_version,
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


def _select_human_seat(
    *,
    config: GameConfig,
    seed: str,
    human_seat: int | None,
    human_seat_random: bool,
) -> int | None:
    if human_seat is not None and human_seat_random:
        raise ValueError("human_seat and human_seat_random are mutually exclusive")
    if human_seat is None and not human_seat_random:
        return None
    if human_seat is not None:
        if human_seat < config.seat_range.start or human_seat > config.seat_range.end:
            raise ValueError("human_seat is outside configured seat range")
        return human_seat
    seats = tuple(range(config.seat_range.start, config.seat_range.end + 1))
    return DeterministicRNG(seed).choice("human_seat", seats)


def _seat_agent_kinds(
    *,
    config: GameConfig,
    specs: Mapping[int, AgentSpecValue],
    human_seat: int | None,
    default_to_provider: bool,
) -> dict[int, str]:
    kinds: dict[int, str] = {}
    for seat_number in range(config.seat_range.start, config.seat_range.end + 1):
        if human_seat == seat_number:
            kinds[seat_number] = "human"
            continue
        spec = specs.get(seat_number)
        if spec is None:
            kinds[seat_number] = "llm" if default_to_provider else "mock"
            continue
        if isinstance(spec, str):
            kinds[seat_number] = "llm" if spec.startswith("llm") else "mock"
            continue
        data = _mapping_from_spec(spec)
        kinds[seat_number] = "llm" if str(data.get("kind", "mock")) == "llm" else "mock"
    return kinds


def _manifest_payload(
    *,
    config_hash: str,
    config_path: str,
    seed: str,
    started_at: str,
    ended_at: str | None,
    winner: str | None,
    seat_presentation: dict[int, dict[str, str]],
    prompt_version: str,
    human_seat: int | None = None,
    seat_agent_kinds: dict[int, str] | None = None,
    forced_seat_roles: dict[int, Role] | None = None,
) -> dict[str, object]:
    return {
        "config_hash": config_hash,
        "config_path": config_path,
        "seed": seed,
        "prompt_pack_version": prompt_version,
        "started_at": started_at,
        "ended_at": ended_at,
        "winner": winner,
        "seat_presentation": seat_presentation,
        "human_seat": human_seat,
        "seat_agent_kinds": {
            str(seat): kind for seat, kind in sorted((seat_agent_kinds or {}).items())
        },
        "forced_seat_roles": {
            str(seat): role.value for seat, role in sorted((forced_seat_roles or {}).items())
        },
    }


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()

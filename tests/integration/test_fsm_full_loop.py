from __future__ import annotations

import time

from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import LastWords, PkVote, Speech, Vote, WolfChatMessage
from wolven_hunt.core.events import Event, EventType
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.orchestration.fsm import (
    _apply_collected_actions,
    _apply_and_log,
    _collect_actions_from_snapshot,
    _decide_with_fallback,
    _run_day,
)
from wolven_hunt.orchestration.phases import Phase
from wolven_hunt.referee.view import PlayerView
from wolven_hunt.storage.event_log import EventLog
from wolven_hunt.storage.jsonl import events_to_jsonl
from wolven_hunt.storage.replay import replay_deterministic

_DEFAULT_PK_TARGET = object()


def test_fsm_runs_100_seeded_games(game_config: GameConfig) -> None:
    for index in range(100):
        state, event_log = simulate(game_config, f"integration-seed-{index:03d}")
        events = event_log.events
        assert state.winner is not None
        assert events[-1].type is EventType.GAME_END
        assert events[-1].payload["winner"] in {"wolf", "good"}
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        assert sum(1 for event in events if event.type is EventType.GAME_END) == 1
        for event in events:
            if event.type is EventType.PHASE_EXIT:
                assert (
                    event.payload["alive_wolves"] + event.payload["alive_good"]
                    == event.payload["alive_total"]
                )
        assert replay_deterministic(events) == events


def test_same_seed_is_byte_identical(game_config: GameConfig) -> None:
    _, first = simulate(game_config, "same-seed")
    _, second = simulate(game_config, "same-seed")
    assert events_to_jsonl(first.events) == events_to_jsonl(second.events)


def test_day_exile_gets_last_words_before_win_check(game_config: GameConfig) -> None:
    vote_targets = {seat: 1 for seat in range(1, 11)}
    vote_targets[1] = 2
    _, event_log = _run_scripted_day(game_config, vote_targets=vote_targets)

    exile = next(event for event in event_log.events if event.type is EventType.EXILE)
    assert exile.payload["seat"] == 1
    assert _last_words_between_exile_and_day_win(event_log.events, 1)


def test_pk_exile_gets_last_words_before_win_check(game_config: GameConfig) -> None:
    vote_targets = {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 2,
        7: 2,
        8: 2,
        9: 2,
        10: 2,
    }
    pk_targets = {seat: 1 for seat in range(3, 11)}
    _, event_log = _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        pk_targets=pk_targets,
        seed="scripted-pk-exile",
    )

    exile = next(event for event in event_log.events if event.type is EventType.EXILE)
    assert exile.payload["seat"] == 1
    assert _last_words_between_exile_and_day_win(event_log.events, 1)


def test_peaceful_pk_day_does_not_trigger_last_words(game_config: GameConfig) -> None:
    vote_targets = {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 2,
        7: 2,
        8: 2,
        9: 2,
        10: 2,
    }
    pk_targets = {3: 1, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 2}
    _, event_log = _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        pk_targets=pk_targets,
        seed="scripted-peaceful-pk",
    )

    assert any(event.type is EventType.PEACEFUL_DAY for event in event_log.events)
    assert not any(event.type is EventType.EXILE for event in event_log.events)
    assert not any(event.type is EventType.LAST_WORDS for event in event_log.events)


def test_day_vote_uses_single_snapshot_and_reveals_casts_after_finish(
    game_config: GameConfig,
) -> None:
    vote_targets = {seat: 2 for seat in range(1, 11)}
    vote_targets[2] = 3
    _, event_log, agents = _run_scripted_day_with_agents(
        game_config,
        vote_targets=vote_targets,
        seed="scripted-day-vote-snapshot",
    )

    for agent in agents.values():
        assert agent.vote_seen_vote_casts == [()]

    vote_casts = [
        event
        for event in event_log.events
        if event.type is EventType.VOTE_CAST and event.phase == "DAY_VOTE"
    ]
    assert [event.actor for event in vote_casts] == list(range(1, 11))
    assert all(event.visibility.public for event in vote_casts)
    result = next(
        event
        for event in event_log.events
        if event.type is EventType.VOTE_RESULT and event.phase == "DAY_VOTE"
    )
    assert result.payload["counts"] == {"2": 9, "3": 1}
    assert max(event.seq for event in vote_casts) < result.seq


def test_day_vote_collects_snapshot_actions_concurrently(game_config: GameConfig) -> None:
    vote_targets = {seat: 2 for seat in range(1, 11)}
    vote_targets[2] = 3
    started_at = time.perf_counter()

    _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        seed="scripted-day-vote-concurrent",
        agent_delay_seconds=0.08,
    )

    assert time.perf_counter() - started_at < 0.45


def test_night_wolf_chat_collects_and_publishes_in_seat_order(
    game_config: GameConfig,
) -> None:
    seed = "scripted-wolf-chat-seat-order"
    state, start_events = build_initial_state(game_config, seed)
    state = state.with_phase(Phase.NIGHT_WOLF_CHAT.value)
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)
    wolf_seats = state.wolf_seats(alive_only=True)
    agents = {
        seat.number: ScriptedWolfChatAgent(seat.number)
        for seat in wolf_seats
    }
    rng = DeterministicRNG(seed)
    expected_seen: list[tuple[int, tuple[int | None, ...]]] = []
    sorted_wolves = tuple(sorted(wolf_seats, key=lambda seat: seat.number))

    for wolf in sorted_wolves:
        action = _decide_with_fallback(
            state,
            game_config,
            agents[wolf.number],
            event_log,
            wolf,
            lambda agent, view: agent.decide_wolf_chat(view),
            rng,
        )
        state = _apply_and_log(
            state,
            action,
            game_config,
            rng,
            event_log,
            state_sink=None,
            control_hook=None,
        )
        expected_seen.append(
            (
                wolf.number,
                tuple(seat.number for seat in sorted_wolves if seat.number < wolf.number),
            )
        )

    del state
    chat_events = [
        event
        for event in event_log.events
        if event.type is EventType.WOLF_CHAT_MESSAGE
    ]
    assert [event.actor for event in chat_events] == sorted(
        seat.number for seat in wolf_seats
    )
    assert [
        (seat_number, agents[seat_number].seen_chat_actors[0])
        for seat_number in sorted(agents)
    ] == expected_seen


def test_day_vote_all_abstain_is_peaceful_without_last_words(
    game_config: GameConfig,
) -> None:
    vote_targets = {seat: None for seat in range(1, 11)}
    _, event_log = _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        seed="scripted-day-all-abstain",
    )

    vote_casts = [
        event
        for event in event_log.events
        if event.type is EventType.VOTE_CAST and event.phase == "DAY_VOTE"
    ]
    assert [event.actor for event in vote_casts] == list(range(1, 11))
    assert all(event.payload["target"] is None for event in vote_casts)
    result = next(
        event
        for event in event_log.events
        if event.type is EventType.VOTE_RESULT and event.phase == "DAY_VOTE"
    )
    assert result.payload["counts"] == {}
    assert result.payload["abstain_count"] == 10
    assert any(
        event.type is EventType.PEACEFUL_DAY and event.phase == "DAY_VOTE"
        for event in event_log.events
    )
    assert not any(event.type is EventType.EXILE for event in event_log.events)
    assert not any(event.type is EventType.LAST_WORDS for event in event_log.events)


def test_day_vote_mixed_abstentions_ignore_abstain_for_exile(
    game_config: GameConfig,
) -> None:
    vote_targets: dict[int, int | None] = {seat: None for seat in range(1, 11)}
    vote_targets.update({1: 2, 2: 2, 3: 4})
    _, event_log = _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        seed="scripted-day-mixed-abstain",
    )

    result = next(
        event
        for event in event_log.events
        if event.type is EventType.VOTE_RESULT and event.phase == "DAY_VOTE"
    )
    assert result.payload["counts"] == {"2": 2, "4": 1}
    assert result.payload["abstain_count"] == 7
    exile = next(event for event in event_log.events if event.type is EventType.EXILE)
    assert exile.payload["seat"] == 2


def test_pk_vote_uses_single_snapshot_and_reveals_casts_after_finish(
    game_config: GameConfig,
) -> None:
    vote_targets = {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 2,
        7: 2,
        8: 2,
        9: 2,
        10: 2,
    }
    pk_targets = {seat: 1 for seat in range(3, 11)}
    _, event_log, agents = _run_scripted_day_with_agents(
        game_config,
        vote_targets=vote_targets,
        pk_targets=pk_targets,
        seed="scripted-pk-vote-snapshot",
    )

    for seat, agent in agents.items():
        if seat in {1, 2}:
            assert agent.pk_seen_vote_casts == []
        else:
            assert agent.pk_seen_vote_casts == [()]

    pk_vote_casts = [
        event
        for event in event_log.events
        if event.type is EventType.VOTE_CAST and event.phase == "DAY_VOTE_PK"
    ]
    assert [event.actor for event in pk_vote_casts] == list(range(3, 11))
    assert all(event.visibility.public for event in pk_vote_casts)
    result = next(
        event
        for event in event_log.events
        if event.type is EventType.VOTE_RESULT and event.phase == "DAY_VOTE_PK"
    )
    assert result.payload["counts"] == {"1": 8}
    assert max(event.seq for event in pk_vote_casts) < result.seq


def test_pk_vote_all_abstain_is_peaceful_without_last_words(
    game_config: GameConfig,
) -> None:
    vote_targets = {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 2,
        7: 2,
        8: 2,
        9: 2,
        10: 2,
    }
    pk_targets = {seat: None for seat in range(3, 11)}
    _, event_log = _run_scripted_day(
        game_config,
        vote_targets=vote_targets,
        pk_targets=pk_targets,
        seed="scripted-pk-all-abstain",
    )

    pk_vote_casts = [
        event
        for event in event_log.events
        if event.type is EventType.VOTE_CAST and event.phase == "DAY_VOTE_PK"
    ]
    assert [event.actor for event in pk_vote_casts] == list(range(3, 11))
    assert all(event.payload["target"] is None for event in pk_vote_casts)
    result = next(
        event
        for event in event_log.events
        if event.type is EventType.VOTE_RESULT and event.phase == "DAY_VOTE_PK"
    )
    assert result.payload["counts"] == {}
    assert result.payload["abstain_count"] == 8
    assert any(
        event.type is EventType.PEACEFUL_DAY and event.phase == "DAY_VOTE_PK"
        for event in event_log.events
    )
    assert not any(event.type is EventType.EXILE for event in event_log.events)
    assert not any(event.type is EventType.LAST_WORDS for event in event_log.events)


class ScriptedDayAgent:
    def __init__(
        self,
        seat: int,
        *,
        vote_target: int | None,
        pk_target: int | None | object = _DEFAULT_PK_TARGET,
        delay_seconds: float = 0.0,
    ) -> None:
        self.seat = Seat(seat)
        self.vote_target = None if vote_target is None else Seat(vote_target)
        self.pk_target = (
            _DEFAULT_PK_TARGET
            if pk_target is _DEFAULT_PK_TARGET
            else None
            if pk_target is None
            else Seat(pk_target)
        )
        self.delay_seconds = delay_seconds
        self.vote_seen_vote_casts: list[tuple[int | None, ...]] = []
        self.pk_seen_vote_casts: list[tuple[int | None, ...]] = []

    def decide_speech(self, view: PlayerView) -> Speech:
        del view
        return Speech(actor=self.seat, text=f"{self.seat.number}号发言")

    def decide_vote(self, view: PlayerView) -> Vote:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.vote_seen_vote_casts.append(_visible_vote_cast_actors(view, "DAY_VOTE"))
        return Vote(actor=self.seat, target=self.vote_target)

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.pk_seen_vote_casts.append(_visible_vote_cast_actors(view, "DAY_VOTE_PK"))
        target = self.pk_target
        if target is _DEFAULT_PK_TARGET:
            target = Seat(int(view.rule_set_summary["pk_seats"][0]))
        return PkVote(actor=self.seat, target=target)

    def decide_last_words(self, view: PlayerView) -> LastWords:
        del view
        return LastWords(actor=self.seat, text=f"{self.seat.number}号遗言")


class ScriptedWolfChatAgent:
    def __init__(self, seat: int, *, delay_seconds: float = 0.0) -> None:
        self.seat = Seat(seat)
        self.delay_seconds = delay_seconds
        self.seen_chat_actors: list[tuple[int | None, ...]] = []

    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.seen_chat_actors.append(_visible_wolf_chat_actors(view))
        return WolfChatMessage(actor=self.seat, text=f"{self.seat.number}号狼聊")


def _run_scripted_day(
    game_config: GameConfig,
    *,
    vote_targets: dict[int, int | None],
    pk_targets: dict[int, int | None] | None = None,
    seed: str = "scripted-day-exile",
    agent_delay_seconds: float = 0.0,
) -> tuple[GameState, EventLog]:
    state, event_log, _ = _run_scripted_day_with_agents(
        game_config,
        vote_targets=vote_targets,
        pk_targets=pk_targets,
        seed=seed,
        agent_delay_seconds=agent_delay_seconds,
    )
    return state, event_log


def _run_scripted_day_with_agents(
    game_config: GameConfig,
    *,
    vote_targets: dict[int, int | None],
    pk_targets: dict[int, int | None] | None = None,
    seed: str = "scripted-day-exile",
    agent_delay_seconds: float = 0.0,
) -> tuple[GameState, EventLog, dict[int, ScriptedDayAgent]]:
    state, start_events = build_initial_state(game_config, seed)
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)
    agents = {
        seat: ScriptedDayAgent(
            seat,
            vote_target=vote_targets[seat],
            pk_target=(
                _DEFAULT_PK_TARGET
                if pk_targets is None or seat not in pk_targets
                else pk_targets[seat]
            ),
            delay_seconds=agent_delay_seconds,
        )
        for seat in range(game_config.seat_range.start, game_config.seat_range.end + 1)
    }
    state = _run_day(
        state,
        game_config,
        agents,
        DeterministicRNG(seed),
        event_log,
        state_sink=None,
        control_hook=None,
    )
    return state, event_log, agents


def _visible_vote_cast_actors(view: PlayerView, phase: str) -> tuple[int | None, ...]:
    current_day = view.rule_set_summary["day"]
    return tuple(
        event.actor
        for event in view.visible_events
        if event.type is EventType.VOTE_CAST
        and event.phase == phase
        and event.day == current_day
    )


def _visible_wolf_chat_actors(view: PlayerView) -> tuple[int | None, ...]:
    current_day = view.rule_set_summary["day"]
    return tuple(
        event.actor
        for event in view.visible_events
        if event.type is EventType.WOLF_CHAT_MESSAGE
        and event.phase == Phase.NIGHT_WOLF_CHAT.value
        and event.day == current_day
    )


def _last_words_between_exile_and_day_win(events: tuple[Event, ...], seat: int) -> bool:
    exile_index = next(
        index for index, event in enumerate(events) if event.type is EventType.EXILE
    )
    win_index = next(
        index
        for index, event in enumerate(events[exile_index + 1 :], exile_index + 1)
        if event.type is EventType.WIN_CHECK and event.phase == "CHECK_WIN_DAY"
    )
    return any(
        event.type is EventType.LAST_WORDS and event.actor == seat
        for event in events[exile_index + 1 : win_index]
    )

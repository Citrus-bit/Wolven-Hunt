from __future__ import annotations

from tests.conftest import simulate

from wolven_hunt.config.schema import GameConfig
from wolven_hunt.core.actions import LastWords, PkVote, Speech, Vote
from wolven_hunt.core.events import Event, EventType
from wolven_hunt.core.rng import DeterministicRNG
from wolven_hunt.core.rule_engine import build_initial_state
from wolven_hunt.core.seat import Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.orchestration.fsm import _run_day
from wolven_hunt.referee.view import PlayerView
from wolven_hunt.storage.event_log import EventLog
from wolven_hunt.storage.jsonl import events_to_jsonl
from wolven_hunt.storage.replay import replay_deterministic


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


class ScriptedDayAgent:
    def __init__(
        self,
        seat: int,
        *,
        vote_target: int,
        pk_target: int | None = None,
    ) -> None:
        self.seat = Seat(seat)
        self.vote_target = Seat(vote_target)
        self.pk_target = None if pk_target is None else Seat(pk_target)

    def decide_speech(self, view: PlayerView) -> Speech:
        del view
        return Speech(actor=self.seat, text=f"{self.seat.number}号发言")

    def decide_vote(self, view: PlayerView) -> Vote:
        del view
        return Vote(actor=self.seat, target=self.vote_target)

    def decide_pk_vote(self, view: PlayerView) -> PkVote:
        target = self.pk_target
        if target is None:
            target = Seat(int(view.rule_set_summary["pk_seats"][0]))
        return PkVote(actor=self.seat, target=target)

    def decide_last_words(self, view: PlayerView) -> LastWords:
        del view
        return LastWords(actor=self.seat, text=f"{self.seat.number}号遗言")


def _run_scripted_day(
    game_config: GameConfig,
    *,
    vote_targets: dict[int, int],
    pk_targets: dict[int, int] | None = None,
    seed: str = "scripted-day-exile",
) -> tuple[GameState, EventLog]:
    state, start_events = build_initial_state(game_config, seed)
    event_log = EventLog(seed=seed)
    event_log.append_all(start_events)
    agents = {
        seat: ScriptedDayAgent(
            seat,
            vote_target=vote_targets[seat],
            pk_target=None if pk_targets is None else pk_targets.get(seat),
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
    return state, event_log


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

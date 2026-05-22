from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wolven_hunt.agents.deterministic_mock import DeterministicMockAgent
from wolven_hunt.config.loader import load_game_config
from wolven_hunt.config.settings import load_settings
from wolven_hunt.core.ids import GameId
from wolven_hunt.core.seat import Seat
from wolven_hunt.orchestration.fsm import run_game
from wolven_hunt.referee.view import build_view
from wolven_hunt.storage.disk import GameRunStore
from wolven_hunt.storage.jsonl import events_from_jsonl, events_to_jsonl, read_events_jsonl
from wolven_hunt.storage.replay import replay_deterministic, replay_resimulate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wolven-hunt")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    simulate = subparsers.add_parser("simulate", help="run a deterministic simulation")
    simulate.add_argument("--config", required=True)
    simulate.add_argument("--seed", required=True)
    simulate.add_argument("--out", default="-", help="path to write JSONL events; '-' for stdout")
    simulate.add_argument("--out-dir", default=None, help="directory for STEP-06 run artifacts")
    simulate.add_argument(
        "--perspective",
        default="spectator",
        choices=["spectator", *[f"seat:{seat}" for seat in range(1, 9)]],
    )

    replay = subparsers.add_parser("replay", help="render a deterministic timeline from events")
    replay.add_argument("--events", required=True)
    replay.add_argument("--raw", default=None)
    replay.add_argument("--mode", default="deterministic", choices=["deterministic", "resimulate"])

    resimulate = subparsers.add_parser("resimulate", help="resimulate a run from events/raw JSONL")
    resimulate.add_argument("--events", required=True)
    resimulate.add_argument("--raw", default=None)

    serve = subparsers.add_parser("serve", help="start the FastAPI server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)
    if args.cmd == "simulate":
        return _run_simulate(args)
    if args.cmd == "replay":
        return _run_replay(args)
    if args.cmd == "resimulate":
        return _run_resimulate(args)
    if args.cmd == "serve":
        return _run_serve(args)
    return 2


def _run_simulate(args: argparse.Namespace) -> int:
    config = load_game_config(Path(args.config))
    agents = {seat: DeterministicMockAgent(Seat(seat)) for seat in range(1, 9)}
    store: GameRunStore | None = None
    if args.out_dir is not None:
        store = GameRunStore(
            runs_dir=Path(args.out_dir),
            game_id=str(GameId.deterministic(str(args.seed))),
        )
    state, event_log = run_game(
        config=config,
        seed=str(args.seed),
        agents=agents,
        event_sink=None if store is None else store.append_event,
    )
    if store is not None:
        store.write_manifest(
            {
                "config_hash": config.config_hash,
                "seed": str(args.seed),
                "prompt_pack_version": "v1",
                "started_at": None,
                "ended_at": None,
                "winner": None if state.winner is None else state.winner.value,
            }
        )
    perspective = str(args.perspective)
    seat = None if perspective == "spectator" else Seat(int(perspective.split(":", 1)[1]))
    visible = build_view(
        state, event_log.events, rule_set=config.rule_set, seat=seat
    ).visible_events
    output = events_to_jsonl(visible)
    if args.out == "-":
        sys.stdout.write(output)
    else:
        Path(args.out).write_text(output, encoding="utf-8")
    return 0


def _run_replay(args: argparse.Namespace) -> int:
    if args.mode == "resimulate":
        events = replay_resimulate(Path(args.events), None if args.raw is None else Path(args.raw))
    else:
        events = replay_deterministic(read_events_jsonl(Path(args.events)))
    sys.stdout.write(events_to_jsonl(events))
    reparsed = events_from_jsonl(events_to_jsonl(events))
    if tuple(event.type for event in reparsed) != tuple(event.type for event in events):
        raise ValueError("replay serialization mismatch")
    return 0


def _run_resimulate(args: argparse.Namespace) -> int:
    events = replay_resimulate(Path(args.events), None if args.raw is None else Path(args.raw))
    sys.stdout.write(events_to_jsonl(events))
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    settings = load_settings()
    import uvicorn

    uvicorn.run(
        "wolven_hunt.api.app:app",
        host=args.host or settings.api_host,
        port=args.port or settings.api_port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

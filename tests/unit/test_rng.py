from __future__ import annotations

from wolven_hunt.core.rng import DeterministicRNG


def test_same_seed_and_stream_are_stable() -> None:
    assert DeterministicRNG("a").stream("x").randint(0, 99) == DeterministicRNG("a").stream(
        "x"
    ).randint(0, 99)


def test_streams_are_independent() -> None:
    rng1 = DeterministicRNG("a")
    rng2 = DeterministicRNG("a")
    first_x = rng1.stream("x").randint(0, 99)
    _ = rng1.stream("y").randint(0, 99)
    assert first_x == rng2.stream("x").randint(0, 99)

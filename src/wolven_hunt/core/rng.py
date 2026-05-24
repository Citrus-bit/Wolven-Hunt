from __future__ import annotations

import hashlib
import random
import threading
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class DeterministicRNG:
    """Derive independent random streams from a stable seed."""

    def __init__(self, seed: str) -> None:
        self.seed = seed
        self._streams: dict[str, random.Random] = {}
        self._lock = threading.RLock()

    def stream(self, name: str) -> random.Random:
        with self._lock:
            if name not in self._streams:
                digest = hashlib.sha256(f"{self.seed}::{name}".encode()).digest()
                self._streams[name] = random.Random(int.from_bytes(digest[:8], "big"))
            return self._streams[name]

    def choice(self, stream_name: str, candidates: Sequence[T]) -> T:
        if not candidates:
            raise ValueError("cannot choose from empty candidates")
        with self._lock:
            return self.stream(stream_name).choice(list(candidates))

    def randint(self, stream_name: str, start: int, stop: int) -> int:
        with self._lock:
            return self.stream(stream_name).randint(start, stop)

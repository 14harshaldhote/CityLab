"""Seeded randomness.

Every random draw in the simulation comes from a named stream derived from one city
seed. Streams are independent, so adding draws to one subsystem (say, crime) never
shifts the numbers another subsystem (say, births) sees. Same seed, same city.
"""

from __future__ import annotations

import hashlib

import numpy as np


class Streams:
    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self._streams: dict[str, np.random.Generator] = {}

    def __call__(self, name: str) -> np.random.Generator:
        gen = self._streams.get(name)
        if gen is None:
            digest = hashlib.sha256(f"{self.seed}:{name}".encode()).digest()
            gen = np.random.default_rng(int.from_bytes(digest[:8], "little"))
            self._streams[name] = gen
        return gen

    def state(self) -> dict[str, dict]:
        return {name: gen.bit_generator.state for name, gen in self._streams.items()}

    def restore(self, state: dict[str, dict]) -> None:
        for name, s in state.items():
            self(name).bit_generator.state = s


def stable_hash(*parts: object) -> int:
    """A small deterministic hash (Python's ``hash`` is salted per process)."""
    digest = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little")

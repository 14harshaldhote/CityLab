"""How fast does the city run? ``python -m benchmarks.bench``"""

from __future__ import annotations

import time

from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.world import World


def main(population: int = 2000, days: int = 3) -> None:
    t0 = time.perf_counter()
    w = World(seed=1, population=population)
    build = time.perf_counter() - t0
    t0 = time.perf_counter()
    w.advance(days * MINUTES_PER_DAY)
    run = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(20):
        w.frame()
    frame = (time.perf_counter() - t0) / 20
    print(f"population {len(w.alive())}: build {build:.2f} s, {run / days:.2f} s per simulated day "
          f"({days * 1440 / run:.0f} sim-minutes per second), frame {frame * 1000:.1f} ms")


if __name__ == "__main__":
    main()

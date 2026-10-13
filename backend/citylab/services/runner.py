"""Runs the world in the background at a chosen speed and fans frames out to viewers.

The simulation itself is plain synchronous Python. The runner advances it in a
worker thread in small real-time slices (``speed`` simulated minutes per real
second), so the API stays responsive, and pushes a compact frame of every
person's position to each connected WebSocket viewer after every slice.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from ..config import Settings
from ..core.world import World
from ..storage.memory import MemoryStore

log = logging.getLogger("citylab.runner")

TICK_S = 0.2
MAX_SPEED = 24 * 60  # one simulated day per real second


class Runner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.RLock()
        self.playing = settings.start_playing
        self.speed = float(settings.speed)
        self.viewers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._carry = 0.0
        self.last_step_s = 0.0
        self.reset(settings.seed, settings.population)

    def reset(self, seed: int, population: int) -> None:
        with self.lock:
            self.world = World(seed=seed, population=population)
            self.store = MemoryStore()
            self.world.bus.subscribe("*", self.store)
            self.pg = None
            if self.settings.database_url:
                try:
                    from ..storage.postgres import PostgresStore

                    self.pg = PostgresStore(self.settings.database_url, seed, population)
                    self.world.bus.subscribe("*", self.pg)
                except Exception as exc:  # the city still runs without a database
                    log.warning("Postgres unavailable, running in memory only: %s", exc)
            # the founding event was published before the stores subscribed
            self.world.emit("reset", f"A new city was generated from seed {seed} with {len(self.world.alive())} people.",
                            data={"seed": seed, "population": population})

    def set(self, playing: bool | None = None, speed: float | None = None) -> None:
        if playing is not None:
            self.playing = playing
        if speed is not None:
            self.speed = max(0.0, min(MAX_SPEED, float(speed)))

    def step(self, minutes: int) -> None:
        with self.lock:
            hour_before = self.world.t // 60
            t0 = time.perf_counter()
            self.world.advance(minutes)
            self.last_step_s = time.perf_counter() - t0
            if self.pg is not None and self.world.t // 60 != hour_before:
                self.pg.flush()

    def frame(self) -> dict[str, Any]:
        with self.lock:
            f = self.world.frame()
        f["playing"] = self.playing
        f["speed"] = self.speed
        return f

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self.pg is not None:
            self.pg.close()

    async def _loop(self) -> None:
        while True:
            started = time.perf_counter()
            try:
                if self.playing and self.speed > 0:
                    self._carry += self.speed * TICK_S
                    whole = int(self._carry)
                    if whole:
                        self._carry -= whole
                        await asyncio.to_thread(self.step, whole)
                if self.viewers:
                    frame = await asyncio.to_thread(self.frame)
                    for q in list(self.viewers):
                        if q.full():
                            q.get_nowait()  # a slow viewer skips frames rather than lagging
                        q.put_nowait(frame)
            except asyncio.CancelledError:
                raise
            except Exception:  # keep the city alive whatever happens
                log.exception("runner tick failed")
            await asyncio.sleep(max(0.01, TICK_S - (time.perf_counter() - started)))

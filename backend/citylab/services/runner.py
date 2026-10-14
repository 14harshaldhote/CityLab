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
from ..core import policy
from ..core.clock import MINUTES_PER_DAY, SimTime
from ..core.world import World
from ..ask.asker import Asker
from ..ask.llm import LocalAI
from ..storage.memory import MemoryStore
from .history import History
from .whatif import WhatIfs

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
        self.whatifs = WhatIfs()
        self.reset(settings.seed, settings.population)
        try:
            ai = LocalAI(settings.ollama_url, settings.chat_model, settings.embed_model)
        except ValueError as exc:  # a bad address switches the AI off rather than stopping the city
            log.warning("%s; answering from the records only", exc)
            ai = LocalAI("", settings.chat_model, settings.embed_model)
        self.asker = Asker(self, ai)

    def reset(self, seed: int, population: int) -> None:
        with self.lock:
            self.world = World(seed=seed, population=population, town=self.settings.town)
            self.store = MemoryStore()
            self.store.on_diverge = self._diverged
            self.history = History()
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
            self.history.capture(self.world)

    def _attach(self, world: World) -> None:
        world.bus.subscribe("*", self.store)
        if self.pg is not None:
            world.bus.subscribe("*", self.pg)
        self.world = world

    def _diverged(self, n: int) -> None:
        """Replaying the past told a different story from event ``n`` on: the old future is gone."""
        self.history.truncate_after(self.world.t)
        if self.pg is not None:
            self.pg.truncate(n, SimTime(self.world.t).day)
        log.info("timeline changed at %s", SimTime(self.world.t).label())

    def _advance(self, minutes: int) -> None:
        """Move the city forward, keeping a snapshot at every midnight it passes."""
        w = self.world
        end = w.t + int(minutes)
        while w.t < end:
            w.advance(min(end, (w.t // MINUTES_PER_DAY + 1) * MINUTES_PER_DAY) - w.t)
            if w.t % MINUTES_PER_DAY == 0:
                self.history.capture(w)
        self.history.horizon = max(self.history.horizon, w.t)

    def travel(self, t: int) -> dict[str, Any]:
        """Show the city exactly as it was (or will be, on this timeline) at minute ``t``."""
        with self.lock:
            t = max(0, min(int(t), self.history.horizon))
            t0 = time.perf_counter()
            world = self.history.restore(t)
            self._attach(world)
            self._advance(t - world.t)  # events re-told on the way are already in the records
            self._carry = 0.0
            return {"t": self.world.t, "label": SimTime(self.world.t).label(), "seconds": round(time.perf_counter() - t0, 2)}

    def change(self, lever: str, value: float) -> dict[str, Any]:
        """Change one of the city's rules from now on. Any future recorded after this moment no longer holds."""
        with self.lock:
            w = self.world
            was = policy.current(w)[lever]
            policy.apply(w, lever, value)
            self.store.truncate(w.bus.count)
            if self.pg is not None:
                self.pg.truncate(w.bus.count, SimTime(w.t).day)
            self.history.truncate_after(w.t)
            info = policy.LEVERS[lever]
            w.emit("policy", f"The city council changed the {info['name'].lower()} from {policy.describe(lever, was)} to {policy.describe(lever, value)}.",
                   data={"lever": lever, "was": was, "value": value})
            return policy.current(w)

    def set(self, playing: bool | None = None, speed: float | None = None) -> None:
        if playing is not None:
            self.playing = playing
        if speed is not None:
            self.speed = max(0.0, min(MAX_SPEED, float(speed)))

    def step(self, minutes: int) -> None:
        with self.lock:
            hour_before = self.world.t // 60
            t0 = time.perf_counter()
            self._advance(minutes)
            self.last_step_s = time.perf_counter() - t0
            if self.pg is not None and self.world.t // 60 != hour_before:
                self.pg.flush()

    def frame(self) -> dict[str, Any]:
        with self.lock:
            f = self.world.frame()
        f["horizon"] = self.history.horizon
        f["playing"] = self.playing
        f["speed"] = self.speed
        return f

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        self.asker.start()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self.whatifs.cancel_running()
        self.asker.stop()
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

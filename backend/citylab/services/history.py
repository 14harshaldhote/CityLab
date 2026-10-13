"""The time machine: a snapshot of the whole city every midnight.

The simulation is deterministic: the same city at the same moment always plays
out the same way. So to show any past moment, load the last snapshot before it
and replay the minutes in between. The replay is exact, and a day of it takes a
couple of seconds.

A snapshot is the whole ``World`` pickled and compressed, about half a megabyte
for 2,000 people. Recent days are all kept; further back, one a week, so a year
of history fits in a few tens of megabytes.
"""

from __future__ import annotations

import pickle
import threading
import zlib
from dataclasses import dataclass

from ..core.clock import MINUTES_PER_DAY, SimTime
from ..core.events import EventBus
from ..core.world import World

KEEP_EVERY_DAY = 30  # the last month: a snapshot for every midnight
KEEP_WEEKLY = 7  # before that, every seventh day


@dataclass
class Snapshot:
    t: int
    events: int  # how many events had been told by then
    blob: bytes


def freeze(world: World) -> bytes:
    bus, world.bus = world.bus, None  # subscribers belong to the viewer, not the city
    try:
        return zlib.compress(pickle.dumps(world, protocol=pickle.HIGHEST_PROTOCOL), 3)
    finally:
        world.bus = bus


def thaw(blob: bytes, events: int) -> World:
    world: World = pickle.loads(zlib.decompress(blob))
    world.bus = EventBus()
    world.bus._next_id = events
    return world


class History:
    def __init__(self) -> None:
        self.snaps: dict[int, Snapshot] = {}
        self.horizon = 0  # the latest moment this timeline has reached
        self.lock = threading.Lock()

    def capture(self, world: World) -> bool:
        """Keep a snapshot of the city as it is now, unless this moment is already kept."""
        with self.lock:
            self.horizon = max(self.horizon, world.t)
            if world.t in self.snaps:
                return False
        snap = Snapshot(world.t, world.bus.count, freeze(world))
        with self.lock:
            self.snaps[world.t] = snap
            self._thin()
        return True

    def _thin(self) -> None:
        newest = max(self.snaps) // MINUTES_PER_DAY
        for t in list(self.snaps):
            day = t // MINUTES_PER_DAY
            if t and newest - day >= KEEP_EVERY_DAY and day % KEEP_WEEKLY:
                del self.snaps[t]

    def nearest(self, t: int) -> Snapshot:
        with self.lock:
            best = max((s for s in self.snaps if s <= t), default=None)
            if best is None:
                raise LookupError("no snapshot that early")
            return self.snaps[best]

    def restore(self, t: int) -> World:
        """The city exactly as it was at minute ``t``: the last snapshot before it, replayed forward."""
        snap = self.nearest(t)
        return thaw(snap.blob, snap.events)

    def truncate_after(self, t: int) -> None:
        """The past changed at minute ``t``: snapshots of the old future are no longer true."""
        with self.lock:
            for k in [k for k in self.snaps if k > t]:
                del self.snaps[k]
            self.horizon = t

    def view(self) -> dict:
        with self.lock:
            snaps = sorted(self.snaps.values(), key=lambda s: s.t)
            return {
                "horizon": self.horizon,
                "horizon_label": SimTime(self.horizon).label(),
                "snapshots": len(snaps),
                "megabytes": round(sum(len(s.blob) for s in snaps) / 1e6, 1),
                "days": [s.t // MINUTES_PER_DAY for s in snaps],
            }

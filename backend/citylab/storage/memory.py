"""In-memory event store: always on, used by the API for fast lookups.

The store is the timeline's diary. When the city is rewound and plays forward
again, it re-tells events the store already has (same id, same words), and those
are skipped. If the replay ever tells a different story, because someone changed
the city's rules in the past, the old future is cut off from that event on.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from ..core.events import Event


class MemoryStore:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.by_person: dict[int, list[int]] = defaultdict(list)
        self.counts: dict[str, int] = defaultdict(int)
        self.on_diverge: Callable[[int], None] | None = None
        self.base = 0  # id of the first event kept (the city may have spoken before the store was listening)

    def __call__(self, event: Event) -> None:
        if not self.events:
            self.base = max(0, event.id)
        if self.base <= event.id < self.base + len(self.events):
            old = self.events[event.id - self.base]
            if old.kind == event.kind and old.text == event.text:
                return  # replaying history we already have
            self.truncate(event.id)
            if self.on_diverge is not None:
                self.on_diverge(event.id)
        idx = len(self.events)
        self.events.append(event)
        self.counts[event.kind] += 1
        for pid in event.people:
            self.by_person[pid].append(idx)

    def truncate(self, n: int) -> None:
        """Forget every event from id ``n`` on."""
        if n >= self.base + len(self.events):
            return
        self.events = self.events[: max(0, n - self.base)]
        self.by_person = defaultdict(list)
        self.counts = defaultdict(int)
        for idx, e in enumerate(self.events):
            self.counts[e.kind] += 1
            for pid in e.people:
                self.by_person[pid].append(idx)

    def query(
        self, *, kind: str | None = None, person: int | None = None, before: int | None = None, limit: int = 50, upto: int | None = None,
    ) -> list[Event]:
        """Newest first. ``upto`` hides events from later than the moment being shown (after a rewind)."""
        source = (self.events[i] for i in reversed(self.by_person.get(person, []))) if person is not None else reversed(self.events)
        out = []
        for e in source:
            if upto is not None and e.id >= upto:
                continue
            if kind is not None and e.kind != kind:
                continue
            if before is not None and e.id >= before:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

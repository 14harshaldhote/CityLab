"""In-memory event store: always on, used by the API for fast lookups."""

from __future__ import annotations

from collections import defaultdict

from ..core.events import Event


class MemoryStore:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.by_person: dict[int, list[int]] = defaultdict(list)
        self.counts: dict[str, int] = defaultdict(int)

    def __call__(self, event: Event) -> None:
        idx = len(self.events)
        self.events.append(event)
        self.counts[event.kind] += 1
        for pid in event.people:
            self.by_person[pid].append(idx)

    def query(self, *, kind: str | None = None, person: int | None = None, before: int | None = None, limit: int = 50) -> list[Event]:
        """Newest first."""
        source = (self.events[i] for i in reversed(self.by_person.get(person, []))) if person is not None else reversed(self.events)
        out = []
        for e in source:
            if kind is not None and e.kind != kind:
                continue
            if before is not None and e.id >= before:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

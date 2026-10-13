"""Events: the only way parts of the city talk to each other, and the city's memory.

Every birth, death, hire or move is an ``Event``. Subsystems publish events on the
``EventBus``; anything that cares (the registry, statistics, storage, later the bank
and the RAG index) subscribes. Each event carries a plain-English ``text`` so the
log reads like a diary and can be searched by meaning later.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

Handler = Callable[["Event"], None]


@dataclass(slots=True)
class Event:
    t: int
    kind: str
    text: str
    people: tuple[int, ...] = ()
    place: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    id: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "t": self.t,
            "kind": self.kind,
            "text": self.text,
            "people": list(self.people),
            "place": self.place,
            "data": self.data,
        }


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._next_id = 0

    def subscribe(self, kind: str, handler: Handler) -> None:
        """``kind="*"`` receives every event."""
        self._handlers[kind].append(handler)

    def publish(self, event: Event) -> Event:
        event.id = self._next_id
        self._next_id += 1
        for handler in self._handlers.get(event.kind, ()):
            handler(event)
        for handler in self._handlers.get("*", ()):
            handler(event)
        return event

    @property
    def count(self) -> int:
        return self._next_id

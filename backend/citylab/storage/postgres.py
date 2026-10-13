"""PostgreSQL event store (optional).

Enabled when ``CITYLAB_DATABASE_URL`` is set. Events are buffered in memory and
written in batches (``flush``), so the simulation never waits on the database.
The pgvector extension is enabled up front for the RAG stage.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from ..core.events import Event


class PostgresStore:
    def __init__(self, url: str, seed: int, population: int) -> None:
        import psycopg  # optional dependency

        self._conn = psycopg.connect(url, autocommit=True)
        schema = resources.files("citylab.storage").joinpath("schema.sql").read_text()
        with self._conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:  # plain Postgres without pgvector still works for now
                pass
            cur.execute(schema)
            cur.execute("INSERT INTO runs (seed, population) VALUES (%s, %s) RETURNING id", (seed, population))
            self.run_id = int(cur.fetchone()[0])
        self._buffer: list[Event] = []
        self._days: list[dict[str, Any]] = []

    def __call__(self, event: Event) -> None:
        self._buffer.append(event)
        if event.kind == "day_summary" and "day" in event.data:
            self._days.append(event.data)

    def add_day(self, row: dict[str, Any]) -> None:
        self._days.append(row)

    def flush(self) -> int:
        events, self._buffer = self._buffer, []
        days, self._days = self._days, []
        if not events and not days:
            return 0
        with self._conn.cursor() as cur:
            if events:
                cur.executemany(
                    "INSERT INTO events (run_id, id, t, kind, text, people, place, data) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(self.run_id, e.id, e.t, e.kind, e.text, list(e.people), e.place, json.dumps(e.data)) for e in events],
                )
            if days:
                cur.executemany(
                    "INSERT INTO daily_stats (run_id, day, row) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(self.run_id, d["day"], json.dumps(d)) for d in days],
                )
        return len(events)

    def count(self, kind: str | None = None) -> int:
        with self._conn.cursor() as cur:
            if kind is None:
                cur.execute("SELECT count(*) FROM events WHERE run_id=%s", (self.run_id,))
            else:
                cur.execute("SELECT count(*) FROM events WHERE run_id=%s AND kind=%s", (self.run_id, kind))
            return int(cur.fetchone()[0])

    def close(self) -> None:
        self.flush()
        self._conn.close()

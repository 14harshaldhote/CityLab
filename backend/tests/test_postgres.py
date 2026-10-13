"""Runs only when CITYLAB_TEST_DATABASE_URL points at a Postgres database."""

import os

import pytest

from citylab.core.events import Event

URL = os.environ.get("CITYLAB_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set CITYLAB_TEST_DATABASE_URL to run Postgres tests")


def test_events_are_written_in_batches():
    from citylab.storage.postgres import PostgresStore

    store = PostgresStore(URL, seed=1, population=10)
    for i in range(3):
        e = Event(t=i, kind="birth", text=f"baby {i}", people=(i,), data={"n": i})
        e.id = i
        store(e)
    assert store.count() == 0  # nothing hits the database until flush
    assert store.flush() == 3
    assert store.count("birth") == 3
    day = Event(t=1440, kind="day_summary", text="day", data={"day": 1, "population": 10})
    day.id = 3
    store(day)
    store.close()
